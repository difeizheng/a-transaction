"""
风险管理模块 - 交易风险控制

组合级风控功能：
- 组合最大回撤控制 (>15% 强制降仓)
- 行业集中度限制 (单一行业≤30%)
- 相关性检查 (避免持有高相关股票)
"""
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RiskMetrics:
    """风险指标"""
    max_drawdown: float      # 最大回撤
    current_drawdown: float  # 当前回撤
    position_rate: float     # 仓位比例
    concentration: float     # 持仓集中度
    var_95: float           # 95% VaR
    risk_level: str         # 风险等级


class RiskManager:
    """
    风险管理器

    功能：
    - 仓位控制
    - 止损止盈
    - 最大回撤限制
    - 黑名单管理
    - 风险预警
    """

    def __init__(
        self,
        max_drawdown: float = 0.15,
        max_position_per_stock: float = 0.2,
        max_total_position: float = 0.95,
        max_industry_exposure: float = 0.3,
        stop_loss: float = 0.08,
        take_profit: float = 0.20,
        blacklist: Optional[List[str]] = None,
        exclude_st: bool = True,
        exclude_kcb: bool = False,
    ):
        """
        初始化风险管理器

        Args:
            max_drawdown: 最大回撤限制
            max_position_per_stock: 单只股票最大仓位
            max_total_position: 最大总仓位
            max_industry_exposure: 单行业最大暴露
            stop_loss: 止损比例
            take_profit: 止盈比例
            blacklist: 黑名单股票列表
            exclude_st: 是否排除 ST 股票
            exclude_kcb: 是否排除科创板
        """
        self.max_drawdown = max_drawdown
        self.max_position_per_stock = max_position_per_stock
        self.max_total_position = max_total_position
        self.max_industry_exposure = max_industry_exposure
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.blacklist: Set[str] = set(blacklist or [])
        self.exclude_st = exclude_st
        self.exclude_kcb = exclude_kcb

        # 状态跟踪
        self.peak_value: float = 0.0
        self.current_value: float = 0.0
        self.positions: Dict[str, Dict] = {}
        self.trade_history: List[Dict] = []

        # 风险事件记录
        self.risk_events: List[Dict] = []

    def check_stock(
        self,
        stock_code: str,
        stock_info: Optional[Dict] = None,
    ) -> Tuple[bool, str]:
        """
        检查股票是否可交易

        Args:
            stock_code: 股票代码
            stock_info: 股票信息（包含 is_st, is_kcb 等）

        Returns:
            (是否可交易，原因)
        """
        # 检查黑名单
        if stock_code in self.blacklist:
            return (False, "股票在黑名单中")

        if stock_info:
            # 检查 ST
            if self.exclude_st and stock_info.get("is_st", False):
                return (False, "ST 股票已排除")

            # 检查科创板
            if self.exclude_kcb and stock_info.get("is_kcb", False):
                return (False, "科创板股票已排除")

        return (True, "通过检查")

    def check_position(
        self,
        stock_code: str,
        buy_amount: float,
        current_positions: Dict[str, Dict],
        total_assets: float,
    ) -> Tuple[bool, str]:
        """
        检查仓位限制

        Args:
            stock_code: 股票代码
            buy_amount: 拟买入金额
            current_positions: 当前持仓
            total_assets: 总资产

        Returns:
            (是否可买入，原因)
        """
        # 计算当前仓位
        current_position_value = sum(
            pos.get("market_value", 0) for pos in current_positions.values()
        )

        # 检查总仓位
        new_position_value = current_position_value + buy_amount
        new_position_rate = new_position_value / total_assets

        if new_position_rate > self.max_total_position:
            return (
                False,
                f"超过最大总仓位限制 ({self.max_total_position:.1%})"
            )

        # 检查单只股票仓位
        if stock_code in current_positions:
            current_stock_value = current_positions[stock_code].get("market_value", 0)
            new_stock_value = current_stock_value + buy_amount
            new_stock_rate = new_stock_value / total_assets

            if new_stock_rate > self.max_position_per_stock:
                return (
                    False,
                    f"超过单只股票最大仓位限制 ({self.max_position_per_stock:.1%})"
                )

        return (True, "通过仓位检查")

    def check_stop_loss(
        self,
        stock_code: str,
        current_price: float,
        cost_price: float,
    ) -> Tuple[bool, str]:
        """
        检查止损条件

        Args:
            stock_code: 股票代码
            current_price: 当前价格
            cost_price: 成本价

        Returns:
            (是否触发止损，原因)
        """
        if cost_price <= 0:
            return (False, "无效成本价")

        loss_rate = (current_price - cost_price) / cost_price

        if loss_rate <= -self.stop_loss:
            return (
                True,
                f"触发止损线 (亏损 {loss_rate:.1%}, 止损线 {-self.stop_loss:.1%})"
            )

        return (False, "未触发止损")

    def check_take_profit(
        self,
        stock_code: str,
        current_price: float,
        cost_price: float,
    ) -> Tuple[bool, str]:
        """
        检查止盈条件

        Args:
            stock_code: 股票代码
            current_price: 当前价格
            cost_price: 成本价

        Returns:
            (是否触发止盈，原因)
        """
        if cost_price <= 0:
            return (False, "无效成本价")

        profit_rate = (current_price - cost_price) / cost_price

        if profit_rate >= self.take_profit:
            return (
                True,
                f"触发止盈线 (盈利 {profit_rate:.1%}, 止盈线 {self.take_profit:.1%})"
            )

        return (False, "未触发止盈")

    def update_portfolio_value(self, current_value: float) -> RiskMetrics:
        """
        更新投资组合价值并计算风险指标

        Args:
            current_value: 当前投资组合价值

        Returns:
            风险指标
        """
        self.current_value = current_value

        # 更新峰值
        if current_value > self.peak_value:
            self.peak_value = current_value

        # 计算回撤
        if self.peak_value > 0:
            current_drawdown = (self.peak_value - current_value) / self.peak_value
        else:
            current_drawdown = 0.0

        # 计算最大回撤（历史）
        max_drawdown = max(
            getattr(self, "_max_drawdown_recorded", 0),
            current_drawdown
        )
        self._max_drawdown_recorded = max_drawdown

        # 计算仓位
        position_rate = 0.0  # 需要外部传入持仓数据

        # 计算集中度
        concentration = self._calculate_concentration()

        # 确定风险等级
        risk_level = self._determine_risk_level(current_drawdown, max_drawdown)

        # 风险预警
        if max_drawdown >= self.max_drawdown * 0.8:
            self._add_risk_event("WARNING", f"回撤接近限制：{max_drawdown:.1%}")

        return RiskMetrics(
            max_drawdown=max_drawdown,
            current_drawdown=current_drawdown,
            position_rate=position_rate,
            concentration=concentration,
            var_95=0.0,  # 简化实现
            risk_level=risk_level,
        )

    def _calculate_concentration(self) -> float:
        """计算持仓集中度"""
        if not self.positions:
            return 0.0

        total_value = sum(
            pos.get("market_value", 0) for pos in self.positions.values()
        )

        if total_value == 0:
            return 0.0

        # 最大持仓占比
        max_position = max(
            pos.get("market_value", 0) for pos in self.positions.values()
        )

        return max_position / total_value

    def _determine_risk_level(
        self,
        current_drawdown: float,
        max_drawdown: float,
    ) -> str:
        """确定风险等级"""
        if max_drawdown >= self.max_drawdown:
            return "CRITICAL"  # 已达最大回撤限制
        elif max_drawdown >= self.max_drawdown * 0.8:
            return "HIGH"      # 高风险
        elif max_drawdown >= self.max_drawdown * 0.5:
            return "MEDIUM"    # 中等风险
        else:
            return "LOW"       # 低风险

    def _add_risk_event(self, level: str, message: str):
        """添加风险事件"""
        event = {
            "timestamp": datetime.now(),
            "level": level,
            "message": message,
        }
        self.risk_events.append(event)
        logger.warning(f"[{level}] {message}")

    def add_to_blacklist(self, stock_code: str):
        """添加到黑名单"""
        self.blacklist.add(stock_code)
        logger.info(f"已将 {stock_code} 加入黑名单")

    def remove_from_blacklist(self, stock_code: str):
        """从黑名单移除"""
        self.blacklist.discard(stock_code)
        logger.info(f"已将 {stock_code} 从黑名单移除")

    def get_risk_report(self) -> Dict:
        """生成风险报告"""
        return {
            "max_drawdown_limit": self.max_drawdown,
            "current_drawdown": getattr(self, "_max_drawdown_recorded", 0),
            "position_limit": self.max_total_position,
            "single_stock_limit": self.max_position_per_stock,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "blacklist_count": len(self.blacklist),
            "risk_events_count": len(self.risk_events),
            "risk_level": self._determine_risk_level(
                getattr(self, "_current_drawdown", 0),
                getattr(self, "_max_drawdown_recorded", 0)
            ),
        }

    def should_reduce_position(self) -> Tuple[bool, str]:
        """
        判断是否应该减仓

        Returns:
            (是否应该减仓，原因)
        """
        current_drawdown = getattr(self, "_current_drawdown", 0)
        max_drawdown = getattr(self, "_max_drawdown_recorded", 0)

        # 回撤接近限制时减仓
        if max_drawdown >= self.max_drawdown * 0.8:
            return (True, f"回撤已达 {max_drawdown:.1%}，接近限制 {self.max_drawdown:.1%}")

        return (False, "风险可控")

    def check_industry_concentration(
        self,
        positions: Dict[str, Dict],
        total_assets: float,
    ) -> Tuple[bool, str, Dict[str, float]]:
        """
        检查行业集中度

        Args:
            positions: 当前持仓 {stock_code: {market_value, industry, ...}}
            total_assets: 总资产

        Returns:
            (是否超过限制，原因，行业集中度字典)
        """
        industry_exposure: Dict[str, float] = {}

        # 计算各行业持仓占比
        for stock_code, pos in positions.items():
            industry = pos.get("industry", "未知行业")
            market_value = pos.get("market_value", 0)

            if industry not in industry_exposure:
                industry_exposure[industry] = 0
            industry_exposure[industry] += market_value

        # 转换为占比
        for industry in industry_exposure:
            industry_exposure[industry] /= total_assets

        # 检查是否超过限制
        for industry, exposure in industry_exposure.items():
            if exposure > self.max_industry_exposure:
                return (
                    False,
                    f"行业 {industry} 集中度过高 ({exposure:.1%} > {self.max_industry_exposure:.1%})",
                    industry_exposure
                )

        return (True, "行业集中度符合要求", industry_exposure)

    def check_correlation(
        self,
        positions: Dict[str, Dict],
        correlation_matrix: Optional[Dict[str, Dict[str, float]]] = None,
        correlation_threshold: float = 0.8,
    ) -> Tuple[bool, str, List[Tuple[str, str]]]:
        """
        检查持仓股票相关性

        Args:
            positions: 当前持仓 {stock_code: {...}}
            correlation_matrix: 相关性矩阵 {stock1: {stock2: corr, ...}}
            correlation_threshold: 高相关阈值

        Returns:
            (是否安全，原因，高相关股票对列表)
        """
        if not positions or correlation_matrix is None:
            return (True, "无法检查相关性（数据不足）", [])

        stock_codes = list(positions.keys())
        high_corr_pairs: List[Tuple[str, str]] = []

        # 检查所有股票对的相关性
        for i, code1 in enumerate(stock_codes):
            for code2 in stock_codes[i + 1:]:
                corr = correlation_matrix.get(code1, {}).get(code2, 0)
                if abs(corr) >= correlation_threshold:
                    high_corr_pairs.append((code1, code2))

        if high_corr_pairs:
            pairs_str = ", ".join([f"{p[0]}-{p[1]}" for p in high_corr_pairs])
            return (
                False,
                f"发现高相关股票对：{pairs_str} (相关系数≥{correlation_threshold})",
                high_corr_pairs
            )

        return (True, "持仓股票相关性正常", high_corr_pairs)

    def should_force_reduce_position(
        self,
        current_drawdown: float,
    ) -> Tuple[bool, float, str]:
        """
        判断是否应该强制减仓（组合最大回撤控制）

        Args:
            current_drawdown: 当前回撤

        Returns:
            (是否强制减仓，建议减仓比例，原因)
        """
        # 回撤超过 80% 限制时，开始强制减仓
        if current_drawdown >= self.max_drawdown * 0.8:
            # 计算减仓比例（回撤越大，减仓越多）
            excess_drawdown = current_drawdown - self.max_drawdown * 0.8
            remaining_buffer = self.max_drawdown * 0.2
            reduce_ratio = min(0.5, excess_drawdown / remaining_buffer)

            return (
                True,
                round(reduce_ratio, 2),
                f"组合回撤 {current_drawdown:.1%} 接近限制 {self.max_drawdown:.1%}，建议减仓 {reduce_ratio:.0%}"
            )

        return (False, 0.0, "组合风险可控")

    def get_position_limit_by_drawdown(self) -> float:
        """
        根据当前回撤动态获取仓位上限

        Returns:
            仓位上限 [0, 1]
        """
        current_drawdown = getattr(self, "_current_drawdown", 0)
        max_drawdown = getattr(self, "_max_drawdown_recorded", 0)

        # 回撤越大，仓位上限越低
        if max_drawdown >= self.max_drawdown:
            return 0.3  # 已达最大回撤，强制降至 30% 仓位
        elif max_drawdown >= self.max_drawdown * 0.8:
            return 0.5  # 回撤接近限制，仓位上限 50%
        elif max_drawdown >= self.max_drawdown * 0.5:
            return 0.7  # 回撤中等，仓位上限 70%
        else:
            return self.max_total_position  # 正常情况，使用默认上限


__all__ = ["RiskManager", "RiskMetrics"]
