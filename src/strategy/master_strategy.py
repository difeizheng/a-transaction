"""
综合策略管理器 - 整合所有优化模块

功能:
1. 策略切换（趋势/震荡）
2. 信号融合（多策略共振）
3. 风险控制（多层保护）
4. 参数自适应
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import numpy as np

from src.utils.logger import get_logger
from src.strategy.v4_strategy import V4Strategy
from src.strategy.grid_strategy import GridStrategy, GridConfig
from src.strategy.enhanced_stoploss import EnhancedStopLoss, StopLossConfig
from src.strategy.dynamic_position import DynamicPositionManager, PositionConfig

logger = get_logger(__name__)


@dataclass
class MasterSignal:
    """综合信号"""
    stock_code: str
    action: str  # buy/sell/hold
    strength: str  # strong/normal/weak
    price: float
    stop_loss: float
    take_profit: float
    position_ratio: float
    strategy_source: str  # trend/grid
    confidence: float
    timestamp: datetime


class MasterStrategy:
    """
    综合策略管理器

    核心逻辑:
    1. 市场状态判断 → 选择策略
    2. 多策略共振 → 提高胜率
    3. 动态止损 → 保护利润
    4. 仓位管理 → 风险分散
    """

    def __init__(self, config: Optional[Dict] = None):
        # 初始化子策略
        self.v4_strategy = V4Strategy()
        self.grid_strategy = GridStrategy(GridConfig(
            grid_num=5,
            adx_threshold=25,
            min_grid_profit=0.02,
        ))
        self.stoploss = EnhancedStopLoss(StopLossConfig(
            trailing_stop_enabled=True,
            time_stop_enabled=True,
            time_stop_days=5,
        ))
        self.position_mgr = DynamicPositionManager(PositionConfig(
            max_position_per_stock=0.25,
            max_industry_exposure=0.30,
        ))

        # 配置
        self.config = config or {}

        # 市场状态
        self.market_regime = "oscillating"  # bull/bear/oscillating

        # 信号历史（用于共振判断）
        self.signal_history: Dict[str, List] = {}

    def set_market_regime(self, regime: str, adx: float = None):
        """
        设置市场状态

        Args:
            regime: bull/bear/oscillating
            adx: ADX 值
        """
        self.market_regime = regime
        self.position_mgr.set_market_regime(regime)

        # 根据市场状态调整策略参数
        if regime == "oscillating":
            # 震荡市：降低网格阈值
            self.grid_strategy.config.adx_threshold = 20
        else:
            # 趋势市：提高网格阈值，避免频繁交易
            self.grid_strategy.config.adx_threshold = 30

        logger.info(f"市场状态更新：{regime} (ADX={adx})")

    def generate_master_signal(
        self,
        df: dict,
        stock_code: str,
        stock_name: str,
        current_price: float,
        timestamp: datetime,
        adx: float,
        industry: str = "unknown",
    ) -> Optional[MasterSignal]:
        """
        生成综合信号

        Args:
            df: K 线数据
            stock_code: 股票代码
            stock_name: 股票名称
            current_price: 当前价
            timestamp: 时间戳
            adx: ADX 值
            industry: 行业

        Returns:
            综合信号或 None
        """
        # 1. 市场状态判断
        if adx >= 30:
            regime = "bull" if current_price > df['close'].rolling(20).mean().iloc[-1] else "bear"
        else:
            regime = "oscillating"

        self.set_market_regime(regime, adx)

        # 2. 根据市场状态选择主策略
        if regime == "oscillating":
            # 震荡市：使用网格策略
            signal = self._generate_grid_signal(
                df, stock_code, current_price, timestamp
            )
        else:
            # 趋势市：使用 V4 策略
            signal = self._generate_v4_signal(
                df, stock_code, stock_name, current_price, timestamp, industry
            )

        # 3. 信号共振检查（可选）
        # 如果 V4 和网格都发出同向信号，提高置信度
        if signal:
            signal = self._check_resonance(signal)

        return signal

    def _generate_v4_signal(
        self,
        df: dict,
        stock_code: str,
        stock_name: str,
        current_price: float,
        timestamp: datetime,
        industry: str,
    ) -> Optional[MasterSignal]:
        """生成 V4 趋势策略信号"""
        signals = self.v4_strategy.generate_signals(df, stock_code)

        if not signals:
            return None

        # 获取最新信号
        latest = signals[-1]
        action = latest.get("signal", "hold")

        if action == "hold":
            return None

        # 转换为 MasterSignal
        strength = "strong" if action == "strong_buy" else "normal"
        stop_distance = latest.get("stop_distance", 0.08)
        stop_loss = current_price * (1 - stop_distance)
        take_profit = current_price * (1 + stop_distance * 2.5)

        position_ratio = latest.get("position_ratio", 0.15)

        return MasterSignal(
            stock_code=stock_code,
            stock_name=stock_name,
            action=action,
            strength=strength,
            price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_ratio=position_ratio,
            strategy_source="v4_trend",
            confidence=latest.get("score", 0.5),
            timestamp=timestamp,
        )

    def _generate_grid_signal(
        self,
        df: dict,
        stock_code: str,
        current_price: float,
        timestamp: datetime,
    ) -> Optional[MasterSignal]:
        """生成网格策略信号"""
        # 识别箱体
        box = self.grid_strategy.identify_range_box(df, lookback_days=30)

        if not box or box.confidence < 0.5:
            return None

        self.grid_strategy.current_box = box

        # 设置网格
        grids = self.grid_strategy.setup_grids(current_price, 100000, box)

        # 检查触发
        actions = self.grid_strategy.check_grid_trigger(current_price, timestamp)

        if not actions:
            return None

        action = actions[0]
        grid_action = action.get("action")

        if grid_action == "buy":
            stop_loss = box.lower * 0.95  # 箱底下 5%
            take_profit = box.middle * 1.1  # 中轴上 10%
            position_ratio = 0.08  # 网格仓位较小
        else:
            stop_loss = current_price
            take_profit = current_price
            position_ratio = 0

        return MasterSignal(
            stock_code=stock_code,
            stock_name="",
            action=grid_action,
            strength="normal",
            price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_ratio=position_ratio,
            strategy_source="grid",
            confidence=box.confidence,
            timestamp=timestamp,
        )

    def _check_resonance(self, signal: MasterSignal) -> MasterSignal:
        """
        检查信号共振

        如果多个策略发出同向信号，提高置信度
        """
        code = signal.stock_code

        if code not in self.signal_history:
            self.signal_history[code] = []

        # 添加当前信号
        self.signal_history[code].append({
            "action": signal.action,
            "source": signal.strategy_source,
            "timestamp": signal.timestamp,
        })

        # 保留最近 5 个信号
        if len(self.signal_history[code]) > 5:
            self.signal_history[code] = self.signal_history[code][-5:]

        # 检查共振
        recent = self.signal_history[code]
        same_action_count = sum(1 for s in recent if s["action"] == signal.action)

        # 共振提高置信度
        if same_action_count >= 3:
            signal.confidence = min(1.0, signal.confidence + 0.2)
            signal.strength = "strong"

        return signal

    def update_position(
        self,
        position: Dict,
        current_price: float,
        current_time: datetime,
        atr: float = None,
    ) -> Tuple[bool, str, Optional[float]]:
        """
        更新持仓（动态止损）

        Returns:
            (是否退出，原因，退出价格)
        """
        # 更新最高价
        if current_price > position.get("highest_price", 0):
            position["highest_price"] = current_price

        # 更新止损位
        stop_info = self.stoploss.update_stop_price(
            position, current_price, current_time, atr
        )

        position["stop_price"] = stop_info["stop_price"]

        # 检查是否触发止损
        should_exit, reason, exit_price = self.stoploss.should_exit(
            position, current_price, current_time, atr
        )

        if should_exit:
            # 记录卖出时间（用于冷却期）
            self.v4_strategy.record_sell(position["code"], current_time)
            return True, reason, exit_price

        return False, "", None

    def get_position_suggestion(
        self,
        signal: MasterSignal,
        total_capital: float,
        current_positions: Dict[str, Dict],
    ) -> float:
        """
        获取仓位建议

        综合考虑：
        1. 信号强度
        2. 市场状态
        3. 行业集中度
        4. 总仓位限制

        Returns:
            建议仓位比例
        """
        # 基础仓位
        base_position = signal.position_ratio

        # 市场状态调整
        regime_adj = self.position_mgr.calculate_market_regime_adjustment()
        adjusted = base_position * regime_adj

        # 信号强度调整
        if signal.strength == "strong":
            adjusted *= 1.2
        elif signal.strength == "weak":
            adjusted *= 0.7

        # 置信度调整
        adjusted *= signal.confidence

        # 限制在合理范围
        adjusted = max(0.02, min(adjusted, self.position_mgr.config.max_position_per_stock))

        return round(adjusted, 3)

    def get_status(self) -> Dict:
        """获取策略状态"""
        return {
            "market_regime": self.market_regime,
            "v4_params": self.v4_strategy.get_strategy_status(),
            "grid_status": self.grid_strategy.get_grid_status(),
            "position_summary": self.position_mgr.get_position_summary(),
        }


# 工厂函数：创建策略实例
def create_master_strategy(
    trend_following: bool = True,
    grid_enabled: bool = True,
    dynamic_position: bool = True,
) -> MasterStrategy:
    """
    创建综合策略

    Args:
        trend_following: 启用趋势跟随
        grid_enabled: 启用网格
        dynamic_position: 启用动态仓位

    Returns:
        MasterStrategy 实例
    """
    config = {
        "trend_following": trend_following,
        "grid_enabled": grid_enabled,
        "dynamic_position": dynamic_position,
    }

    return MasterStrategy(config)
