"""
动态仓位管理模块

功能：
1. 根据信号强度动态分配仓位
2. 根据市场状态调整总仓位
3. 行业集中度控制
4. 风险平价模型
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import numpy as np

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PositionConfig:
    """仓位配置"""
    # 基础仓位
    base_position: float = 0.10  # 基础仓位 10%
    max_position_per_stock: float = 0.25  # 单只股票最大 25%
    max_total_position: float = 0.95  # 最大总仓位 95%
    min_cash_reserve: float = 0.05  # 最小现金储备 5%

    # 信号强度仓位映射
    signal_position_map: Dict[str, float] = field(default_factory=lambda: {
        "strong_buy": 0.25,  # 强烈买入：25% 仓位
        "buy": 0.15,         # 买入：15% 仓位
        "weak_buy": 0.08,    # 轻微买入：8% 仓位
        "hold": 0.0,         # 持有：0% 仓位
        "sell": -0.5,        # 卖出：减仓 50%
        "strong_sell": -1.0, # 强烈卖出：清仓
    })

    # 市场状态仓位调整
    market_regime_position: Dict[str, float] = field(default_factory=lambda: {
        "bull": 0.90,        # 牛市：90% 仓位
        "bear": 0.30,        # 熊市：30% 仓位
        "oscillating": 0.60, # 震荡市：60% 仓位
    })

    # 行业配置
    max_industry_exposure: float = 0.30  # 单行业最大 30%
    min_industries: int = 3              # 最少覆盖 3 个行业

    # 风险调整
    risk_adjustment_enabled: bool = True
    max_drawdown_limit: float = 0.15   # 最大回撤 15%
    volatility_target: float = 0.02    # 目标波动率 2%


@dataclass
class StockPosition:
    """股票持仓"""
    code: str
    name: str
    quantity: int
    avg_cost: float
    current_price: float
    market_value: float
    weight: float  # 当前权重
    signal: str    # 当前信号
    industry: str  # 所属行业


class DynamicPositionManager:
    """
    动态仓位管理器

    核心功能：
    1. 信号强度仓位映射
    2. 市场状态动态调整
    3. 行业集中度控制
    4. 风险平价分配
    """

    def __init__(self, config: Optional[PositionConfig] = None):
        self.config = config or PositionConfig()
        self.positions: Dict[str, StockPosition] = {}
        self.total_capital = 0
        self.current_regime = "oscillating"  # 当前市场状态

    def set_market_regime(self, regime: str):
        """设置市场状态"""
        self.current_regime = regime
        logger.info(f"市场状态更新为：{regime}")

    def calculate_signal_position(
        self,
        signal: str,
        score: float,
        confidence: float,
    ) -> float:
        """
        根据信号计算目标仓位

        Args:
            signal: 信号类型 (strong_buy/buy/hold/sell/strong_sell)
            score: 综合得分 (-1 到 1)
            confidence: 置信度 (0 到 1)

        Returns:
            目标仓位比例
        """
        # 基础信号仓位
        base = self.config.signal_position_map.get(signal, 0)

        # 根据得分微调
        score_adjustment = score * 0.1  # 得分影响 10%

        # 根据置信度调整
        confidence_multiplier = 0.5 + confidence * 0.5  # 0.5 到 1.0

        # 计算最终仓位
        position = (base + score_adjustment) * confidence_multiplier

        # 限制在合理范围
        position = max(0, min(position, self.config.max_position_per_stock))

        return position

    def calculate_market_regime_adjustment(self) -> float:
        """
        计算市场状态调整系数

        Returns:
            调整系数 (0 到 1)
        """
        regime_map = self.config.market_regime_position
        return regime_map.get(self.current_regime, 0.6)

    def check_industry_concentration(
        self,
        positions: Dict[str, StockPosition],
        new_code: str,
        new_industry: str,
        new_weight: float,
    ) -> Tuple[bool, str]:
        """
        检查行业集中度

        Args:
            positions: 当前持仓
            new_code: 新股票代码
            new_industry: 新股票行业
            new_weight: 新股票权重

        Returns:
            (是否合规，原因)
        """
        # 计算当前行业暴露
        industry_exposure: Dict[str, float] = {}

        for pos in positions.values():
            industry = pos.industry
            industry_exposure[industry] = industry_exposure.get(industry, 0) + pos.weight

        # 加上新股票
        industry_exposure[new_industry] = industry_exposure.get(new_industry, 0) + new_weight

        # 检查是否超限
        for industry, exposure in industry_exposure.items():
            if exposure > self.config.max_industry_exposure:
                return False, f"行业 {industry} 暴露 {exposure:.1%} > {self.config.max_industry_exposure:.0%}"

        return True, "行业集中度合规"

    def risk_parity_allocation(
        self,
        stocks: List[Dict],
        total_capital: float,
    ) -> Dict[str, float]:
        """
        风险平价分配

        根据波动率倒数分配权重，波动率越低，权重越高

        Args:
            stocks: 股票列表，包含 code, volatility
            total_capital: 总资金

        Returns:
            权重分配 {code: weight}
        """
        if not stocks:
            return {}

        # 计算波动率倒数
        inv_vol = {}
        for stock in stocks:
            vol = stock.get("volatility", 0.02)
            if vol <= 0:
                vol = 0.02
            inv_vol[stock["code"]] = 1 / vol

        # 归一化
        total_inv_vol = sum(inv_vol.values())
        weights = {code: inv / total_inv_vol for code, inv in inv_vol.items()}

        # 限制单只股票最大权重
        max_weight = 1 / len(stocks) * 2  # 平均权重的 2 倍
        for code in weights:
            weights[code] = min(weights[code], max_weight)

        # 重新归一化
        total_weight = sum(weights.values())
        weights = {code: w / total_weight for code, w in weights.items()}

        return weights

    def calculate_dynamic_position(
        self,
        stock_code: str,
        signal: str,
        score: float,
        confidence: float,
        industry: str,
        volatility: float,
        total_capital: float,
        positions: Dict[str, StockPosition],
    ) -> Tuple[float, str]:
        """
        综合计算动态仓位

        Args:
            stock_code: 股票代码
            signal: 信号类型
            score: 综合得分
            confidence: 置信度
            industry: 行业
            volatility: 波动率
            total_capital: 总资金
            positions: 当前持仓

        Returns:
            (目标仓位，原因)
        """
        # 1. 信号仓位
        signal_position = self.calculate_signal_position(signal, score, confidence)

        # 2. 市场状态调整
        regime_adjustment = self.calculate_market_regime_adjustment()
        adjusted_position = signal_position * regime_adjustment

        # 3. 波动率调整（波动率越高，仓位越低）
        vol_ratio = self.config.volatility_target / volatility if volatility > 0 else 1
        vol_ratio = max(0.5, min(1.5, vol_ratio))  # 限制在 0.5-1.5
        adjusted_position *= vol_ratio

        # 4. 行业集中度检查
        is_ok, reason = self.check_industry_concentration(
            positions, stock_code, industry, adjusted_position
        )
        if not is_ok:
            # 行业集中度过高，降低仓位
            adjusted_position *= 0.5
            reason += "，降低仓位"

        # 5. 总仓位检查
        current_total = sum(pos.weight for pos in positions.values())
        if current_total + adjusted_position > self.config.max_total_position:
            adjusted_position = self.config.max_total_position - current_total
            reason = "总仓位限制"

        # 6. 最小仓位检查
        min_position = total_capital * 0.02  # 最小 2%
        if adjusted_position * total_capital < min_position:
            adjusted_position = 0.02
            reason = "最小仓位调整"

        return adjusted_position, reason

    def get_available_cash(
        self,
        total_capital: float,
        positions: Dict[str, StockPosition],
    ) -> float:
        """
        计算可用资金

        Args:
            total_capital: 总资金
            positions: 当前持仓

        Returns:
            可用资金
        """
        # 当前持仓市值
        position_value = sum(pos.market_value for pos in positions.values())

        # 可用资金 = 总资金 - 持仓市值 - 最小现金储备
        available = total_capital - position_value - (total_capital * self.config.min_cash_reserve)

        return max(0, available)

    def rebalance(
        self,
        signals: Dict[str, Dict],  # {code: {signal, score, confidence, industry, volatility}}
        total_capital: float,
        current_positions: Dict[str, StockPosition],
        prices: Dict[str, float],
    ) -> List[Dict]:
        """
        再平衡持仓

        Args:
            signals: 信号字典
            total_capital: 总资金
            current_positions: 当前持仓
            prices: 当前价格

        Returns:
            调仓操作列表
        """
        actions = []

        # 1. 计算目标仓位
        target_positions: Dict[str, float] = {}

        for code, sig in signals.items():
            target, reason = self.calculate_dynamic_position(
                stock_code=code,
                signal=sig.get("signal", "hold"),
                score=sig.get("score", 0),
                confidence=sig.get("confidence", 0.5),
                industry=sig.get("industry", "unknown"),
                volatility=sig.get("volatility", 0.02),
                total_capital=total_capital,
                positions=current_positions,
            )
            target_positions[code] = target

        # 2. 生成调仓指令
        for code, target_weight in target_positions.items():
            current_pos = current_positions.get(code)
            current_weight = current_pos.weight if current_pos else 0
            target_value = total_capital * target_weight
            current_value = current_pos.market_value if current_pos else 0

            diff_value = target_value - current_value

            if abs(diff_value) / total_capital > 0.01:  # 差异超过 1%
                price = prices.get(code, 0)
                if price > 0:
                    quantity = int(abs(diff_value) / price / 100) * 100

                    if quantity > 0:
                        actions.append({
                            "code": code,
                            "action": "buy" if diff_value > 0 else "sell",
                            "quantity": quantity,
                            "target_weight": target_weight,
                            "reason": f"再平衡：{current_weight:.1%} -> {target_weight:.1%}",
                        })

        return actions

    def get_position_summary(self) -> Dict:
        """获取仓位摘要"""
        if not self.positions:
            return {
                "total_weight": 0,
                "position_count": 0,
                "industries": [],
                "top_holdings": [],
            }

        total_weight = sum(pos.weight for pos in self.positions.values())
        industries = list(set(pos.industry for pos in self.positions.values()))

        # 按市值排序
        sorted_positions = sorted(
            self.positions.values(),
            key=lambda x: x.market_value,
            reverse=True,
        )

        top_holdings = [
            {"code": pos.code, "weight": pos.weight, "industry": pos.industry}
            for pos in sorted_positions[:5]
        ]

        return {
            "total_weight": round(total_weight, 4),
            "position_count": len(self.positions),
            "industries": industries,
            "top_holdings": top_holdings,
            "market_regime": self.current_regime,
        }
