"""
风险管理模块 - 交易风险控制
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


# 导入 Tuple 用于类型注解
from typing import Tuple

__all__ = ["RiskManager", "RiskMetrics"]
