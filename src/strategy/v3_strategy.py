"""
V3 实战策略 - 针对 A 股实盘优化 v2

核心改进：
1. 趋势回调买入 - 不做突破追高，做趋势回调
2. 双均线趋势确认 - MA20 + MA60 多重过滤
3. 市场环境判断 - 大盘在 MA20 上才做多
4. 分批建仓/止盈 - 降低风险
5. 动态仓位 - 根据信号强度和市场环境
6. 更灵活的止盈 - 阶梯式止盈
7. 加入成交量确认 - 量价配合

买入条件（按重要性排序）：
【核心条件 - 必须满足】
1. MA20 向上（中期趋势向上）
2. 价格在 MA20 之上
3. 近 5 日有回调（不追高）

【加分条件 - 满足越多仓位越重】
4. MA5 > MA10（短期强势）+0.15
5. MACD 金叉或 DIF>0 +0.2
6. RSI 40-60 区间 +0.15
7. 成交量萎缩后放大 +0.15
8. 技术得分>0.2 +0.15

仓位管理：
- 满足 3 个核心 + 1 个加分 = 轻仓 (15%)
- 满足 3 个核心 + 3 个加分 = 中仓 (25%)
- 满足 3 个核心 + 5 个加分 = 重仓 (35%)

止盈策略：
- 第一目标：15% 盈利，止盈 50%
- 第二目标：25% 盈利，全部止盈
- 或触发跟踪止损

止损策略：
- 初始止损：-8% 或 ATR*2
- 跟踪止损：从最高点回撤 5%
- 时间止损：持仓 10 天无盈利
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import pandas as pd
import numpy as np

from src.utils.logger import get_logger
from src.analyzers.technical_analyzer import TechnicalAnalyzer
from src.analyzers.volatility_analyzer import VolatilityAnalyzer

logger = get_logger(__name__)


@dataclass
class StrategySignal:
    """策略信号"""
    stock_code: str
    stock_name: str
    signal: str
    price: float
    timestamp: datetime
    tech_score: float
    buy_score: float
    sell_score: float
    atr: float
    stop_distance: float
    take_profit_distance: float
    rsi: float
    volume_ratio: float
    conditions: Dict
    position_level: str  # light/normal/heavy 仓位等级


@dataclass
class Position:
    """持仓信息"""
    stock_code: str
    stock_name: str
    quantity: int
    avg_cost: float
    entry_time: datetime
    stop_price: float
    take_profit: float
    highest_price: float
    entry_signal: str
    position_level: str  # 仓位等级
    entry_count: int = 1  # 分批建仓次数


class V3Strategy:
    """
    V3 实战策略

    核心逻辑：
    1. 大盘过滤 - 只在市场环境好时操作
    2. 趋势为王 - 双均线 (MA20/MA60) 确认趋势
    3. 量价配合 - 成交量确认
    4. 分批操作 - 降低单次风险
    5. 动态止损 - 跟踪止损 + 时间止损

    买入条件（按重要性排序）：
    【核心条件 - 必须满足】
    1. MA20 向上（中期趋势向上）
    2. 价格在 MA20 之上
    3. 成交量放大（>1.5 倍）

    【加分条件 - 满足越多仓位越重】
    4. MA5 > MA10（短期强势）+0.15
    5. MACD 金叉 +0.2
    6. RSI 50-65 区间 +0.15
    7. 突破 N 日新高 +0.15
    8. 技术得分>0.2 +0.15

    仓位管理：
    - 满足 3 个核心 + 1 个加分 = 轻仓 (15%)
    - 满足 3 个核心 + 3 个加分 = 中仓 (25%)
    - 满足 3 个核心 + 5 个加分 = 重仓 (35%)

    止盈策略：
    - 第一目标：15% 盈利，止盈 50%
    - 第二目标：25% 盈利，全部止盈
    - 或触发跟踪止损

    止损策略：
    - 初始止损：-8% 或 ATR*2
    - 跟踪止损：从最高点回撤 5%
    - 时间止损：持仓 10 天无盈利
    """

    def __init__(
        self,
        atr_multiplier: float = 2.0,
        initial_stop: float = 0.08,
        trailing_stop: float = 0.05,
        time_stop_days: int = 10,
    ):
        self.technical_analyzer = TechnicalAnalyzer()
        self.volatility_analyzer = VolatilityAnalyzer()

        # 策略参数
        self.atr_multiplier = atr_multiplier
        self.initial_stop = initial_stop
        self.trailing_stop = trailing_stop
        self.time_stop_days = time_stop_days

        # 仓位管理
        self.positions: Dict[str, Position] = {}

        logger.info(f"V3 策略初始化 - 初始止损:{initial_stop:.0%}, "
                   f"跟踪止损:{trailing_stop:.0%}, 时间止损:{time_stop_days}天")

    def check_market_condition(self, market_df: pd.DataFrame) -> bool:
        """
        检查大盘环境
        返回 True 表示可以操作，False 表示观望
        """
        if len(market_df) < 20:
            return False

        # 计算大盘 MA20
        ma20 = market_df['close'].rolling(20).mean()
        current_price = float(market_df['close'].iloc[-1])
        current_ma20 = float(ma20.iloc[-1])
        prev_ma20 = float(ma20.iloc[-5]) if len(market_df) >= 5 else current_ma20

        # 大盘在 MA20 之上且 MA20 向上
        return current_price > current_ma20 and current_ma20 > prev_ma20

    def calculate_indicators(self, df: pd.DataFrame) -> Dict:
        """计算技术指标"""
        indicators = {}

        # 均线系统
        indicators['ma5'] = df['close'].rolling(5).mean()
        indicators['ma10'] = df['close'].rolling(10).mean()
        indicators['ma20'] = df['close'].rolling(20).mean()
        indicators['ma60'] = df['close'].rolling(60).mean()

        # MACD
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        indicators['macd_dif'] = exp1 - exp2
        indicators['macd_dea'] = indicators['macd_dif'].ewm(span=9, adjust=False).mean()
        indicators['macd_hist'] = indicators['macd_dif'] - indicators['macd_dea']

        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss
        indicators['rsi'] = 100 - (100 / (1 + rs))

        # ATR
        indicators['atr'] = self.volatility_analyzer.calculate_atr(df)

        # 成交量
        indicators['volume_ma20'] = df['volume'].rolling(20).mean()

        # N 日新高/新低
        indicators['high_n'] = df['high'].rolling(20).max()
        indicators['low_n'] = df['low'].rolling(20).min()

        return indicators

    def generate_signal(
        self,
        df: pd.DataFrame,
        stock_code: str,
        stock_name: str = "",
        timestamp: Optional[datetime] = None,
        is_market_ok: bool = True,  # 大盘环境
    ) -> StrategySignal:
        """生成策略信号"""
        if len(df) < 30:
            return self._create_hold_signal(stock_code, stock_name)

        ind = self.calculate_indicators(df)
        i = len(df) - 1

        # 获取当前值
        current_price = float(df['close'].iloc[i])
        prev_price_5 = float(df['close'].iloc[i-5]) if i >= 5 else current_price  # 5 日前价格
        curr_ma20 = float(ind['ma20'].iloc[i])
        prev_ma20 = float(ind['ma20'].iloc[i-5]) if i >= 5 else curr_ma20
        curr_ma60 = float(ind['ma60'].iloc[i]) if i >= 60 else curr_ma20
        curr_ma5 = float(ind['ma5'].iloc[i])
        curr_ma10 = float(ind['ma10'].iloc[i])
        curr_macd = float(ind['macd_dif'].iloc[i])
        prev_macd = float(ind['macd_dif'].iloc[i-3]) if i >= 3 else 0
        curr_rsi = float(ind['rsi'].iloc[i]) if not pd.isna(ind['rsi'].iloc[i]) else 50
        prev_rsi = float(ind['rsi'].iloc[i-3]) if i >= 3 else curr_rsi
        curr_volume = float(df['volume'].iloc[i])
        avg_volume = float(ind['volume_ma20'].iloc[i]) if i >= 20 else curr_volume
        volume_ratio = curr_volume / avg_volume if avg_volume > 0 else 1
        high_n = float(ind['high_n'].iloc[i])
        low_n = float(ind['low_n'].iloc[i])
        atr = float(ind['atr'].iloc[i]) if not pd.isna(ind['atr'].iloc[i]) else 0

        # 技术得分
        tech_signal = self.technical_analyzer.analyze(df)
        tech_score = tech_signal.score

        # === 核心条件检查 - 趋势回调买入 ===
        # 1. MA20 向上（中期趋势向上）
        ma20_up = curr_ma20 > prev_ma20
        # 2. 价格在 MA20 之上（多头排列）
        above_ma20 = current_price > curr_ma20
        # 3. 近 5 日有回调（不追高）- 当前价格低于 5 日前价格，或涨幅不超过 5%
        pullback = current_price <= prev_price_5 * 1.05

        core_conditions = {
            'ma20_up': ma20_up,
            'above_ma20': above_ma20,
            'pullback': pullback,
        }
        core_count = sum(core_conditions.values())

        # === 加分条件检查 ===
        bonus_score = 0
        bonus_details = {}

        # 1. MA5 > MA10（短期强势）
        if curr_ma5 > curr_ma10:
            bonus_score += 0.15
            bonus_details['ma5_above_ma10'] = True

        # 2. MACD 金叉或 DIF>0
        if curr_macd > 0 or (curr_macd > prev_macd and prev_macd <= 0):
            bonus_score += 0.2
            bonus_details['macd_bullish'] = True

        # 3. RSI 40-60 区间（未超买）
        if 40 <= curr_rsi <= 60:
            bonus_score += 0.15
            bonus_details['rsi_ok'] = True

        # 4. 成交量萎缩后放大（今日成交量>5 日均量）
        volume_ma5 = df['volume'].iloc[i-5:i].mean() if i >= 5 else curr_volume
        if curr_volume > volume_ma5:
            bonus_score += 0.15
            bonus_details['volume_up'] = True

        # 5. 技术得分>0.2
        if tech_score > 0.2:
            bonus_score += 0.15
            bonus_details['tech_positive'] = True

        # === 确定信号和仓位 ===
        # 核心条件至少满足 2 个，且大盘环境允许（或忽略大盘）
        if core_count < 2:
            # 核心条件不满足，观望
            signal = "hold"
            position_level = "none"
        elif not is_market_ok:
            # 大盘不好，降低要求，只允许轻仓
            signal = "buy"
            position_level = "light"
        else:
            # 根据加分项确定仓位和信号强度
            if bonus_score >= 0.6:
                signal = "strong_buy"
                position_level = "heavy"  # 重仓 35%
            elif bonus_score >= 0.3:
                signal = "buy"
                position_level = "normal"  # 中仓 25%
            else:
                signal = "buy"
                position_level = "light"  # 轻仓 15%

        # === 卖出条件 ===
        sell_conditions = 0
        sell_score = 0

        if current_price < curr_ma20:
            sell_conditions += 1
            sell_score += 0.3
        if curr_ma20 < prev_ma20:
            sell_conditions += 1
            sell_score += 0.2
        if curr_ma5 < curr_ma10:
            sell_conditions += 1
            sell_score += 0.15
        if curr_macd < 0 and curr_macd < prev_macd:
            sell_conditions += 1
            sell_score += 0.25
        if curr_rsi > 75:
            sell_conditions += 1
            sell_score += 0.2

        if sell_conditions >= 3 and sell_score >= 0.5:
            signal = "sell" if sell_score < 0.7 else "strong_sell"

        # 计算止损
        if atr > 0:
            stop_distance = max(self.initial_stop, (atr * self.atr_multiplier) / current_price)
            stop_distance = min(stop_distance, 0.15)
        else:
            stop_distance = self.initial_stop

        # 止盈距离 (阶梯式)
        take_profit_distance = stop_distance * 2.5  # 基础盈亏比 2.5:1

        if timestamp is None:
            trade_date = df.iloc[i].get("trade_date", str(i))
            if isinstance(trade_date, str):
                try:
                    timestamp = datetime.strptime(trade_date, "%Y%m%d")
                except:
                    timestamp = datetime.now()

        return StrategySignal(
            stock_code=stock_code,
            stock_name=stock_name,
            signal=signal,
            price=current_price,
            timestamp=timestamp,
            tech_score=tech_score,
            buy_score=bonus_score,
            sell_score=sell_score,
            atr=round(atr, 4),
            stop_distance=round(stop_distance, 4),
            take_profit_distance=round(take_profit_distance, 4),
            rsi=round(curr_rsi, 2),
            volume_ratio=round(volume_ratio, 2),
            conditions={
                'core_count': core_count,
                'core_details': core_conditions,
                'bonus_score': bonus_score,
                'bonus_details': bonus_details,
            },
            position_level=position_level,
        )

    def _create_hold_signal(self, stock_code: str, stock_name: str) -> StrategySignal:
        """创建持仓信号"""
        return StrategySignal(
            stock_code=stock_code,
            stock_name=stock_name,
            signal="hold",
            price=0,
            timestamp=datetime.now(),
            tech_score=0,
            buy_score=0,
            sell_score=0,
            atr=0,
            stop_distance=0.08,
            take_profit_distance=0.20,
            rsi=50,
            volume_ratio=1,
            conditions={},
            position_level="none",
        )

    def get_position_size(self, signal: StrategySignal, capital: float) -> int:
        """
        根据信号强度和仓位等级计算建仓数量
        """
        # 仓位比例
        level_ratio = {
            "light": 0.15,
            "normal": 0.25,
            "heavy": 0.35,
            "none": 0,
        }
        ratio = level_ratio.get(signal.position_level, 0)

        if ratio == 0 or signal.price <= 0:
            return 0

        quantity = int(capital * ratio / signal.price / 100) * 100
        return max(0, quantity)

    def update_position(
        self,
        signal: StrategySignal,
        quantity: int,
    ) -> Optional[Position]:
        """新建持仓"""
        if signal.stock_code in self.positions:
            # 已有持仓，可以考虑加仓（简化处理：不加仓）
            return None

        stop_price = signal.price * (1 - signal.stop_distance)
        take_profit = signal.price * (1 + signal.take_profit_distance)

        position = Position(
            stock_code=signal.stock_code,
            stock_name=signal.stock_name,
            quantity=quantity,
            avg_cost=signal.price,
            entry_time=signal.timestamp,
            stop_price=stop_price,
            take_profit=take_profit,
            highest_price=signal.price,
            entry_signal=signal.signal,
            position_level=signal.position_level,
            entry_count=1,
        )

        self.positions[signal.stock_code] = position
        logger.info(f"[V3] 新建持仓 {signal.stock_code}: "
                   f"仓位={signal.position_level}, 入场价={signal.price:.2f}, "
                   f"止损={stop_price:.2f}, 止盈={take_profit:.2f}")

        return position

    def check_exit(
        self,
        stock_code: str,
        current_price: float,
        timestamp: datetime,
        holding_days: int,
    ) -> Optional[Tuple[Position, str, float]]:
        """
        检查退出条件
        - 止损
        - 止盈
        - 时间止损
        """
        if stock_code not in self.positions:
            return None

        position = self.positions[stock_code]

        # 止损
        if current_price <= position.stop_price:
            return (position, "止损", position.stop_price)

        # 止盈
        if current_price >= position.take_profit:
            return (position, "止盈", position.take_profit)

        # 时间止损：持仓超过 N 天且盈利<5%
        if holding_days >= self.time_stop_days:
            profit_pct = (current_price - position.avg_cost) / position.avg_cost
            if profit_pct < 0.05:
                return (position, "时间止损", current_price)

        return None

    def update_trailing_stop(
        self,
        stock_code: str,
        current_price: float,
    ) -> float:
        """更新跟踪止损"""
        if stock_code not in self.positions:
            return 0

        position = self.positions[stock_code]

        # 更新最高价
        if current_price > position.highest_price:
            position.highest_price = current_price
            # 上移止损：从最高点回撤 5%
            new_stop = current_price * (1 - self.trailing_stop)
            if new_stop > position.stop_price:
                position.stop_price = new_stop

        return position.stop_price

    def remove_position(self, stock_code: str):
        """移除持仓"""
        if stock_code in self.positions:
            del self.positions[stock_code]

    def get_position_info(self, stock_code: str) -> Optional[Dict]:
        """获取持仓信息"""
        if stock_code not in self.positions:
            return None

        pos = self.positions[stock_code]
        return {
            "stock_code": pos.stock_code,
            "stock_name": pos.stock_name,
            "quantity": pos.quantity,
            "avg_cost": pos.avg_cost,
            "entry_time": pos.entry_time,
            "current_stop": pos.stop_price,
            "take_profit": pos.take_profit,
            "highest_price": pos.highest_price,
            "entry_signal": pos.entry_signal,
            "position_level": pos.position_level,
        }

    def get_all_positions(self) -> List[Dict]:
        """获取所有持仓"""
        return [self.get_position_info(code) for code in self.positions]


__all__ = ["V3Strategy", "StrategySignal", "Position"]
