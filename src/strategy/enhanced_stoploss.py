"""
增强止损策略模块

支持：
1. 移动止损（跟踪止损）
2. 时间止损
3. ATR 动态止损
4. 分级止盈
5. 条件止损
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import numpy as np


@dataclass
class StopLossConfig:
    """止损配置"""
    # 基础止损
    base_stop_loss: float = 0.08  # 基础止损比例 8%

    # ATR 动态止损
    atr_multiplier: float = 2.0  # ATR 倍数
    min_atr_stop: float = 0.03   # 最小 ATR 止损 3%
    max_atr_stop: float = 0.15   # 最大 ATR 止损 15%

    # 移动止损
    trailing_stop_enabled: bool = True
    trailing_stop_threshold: float = 0.05  # 盈利 5% 后启动移动止损
    trailing_stop_distance: float = 0.03   # 移动止损距离 3%

    # 时间止损
    time_stop_enabled: bool = True
    time_stop_days: int = 5  # 5 天不涨自动卖出

    # 分级止盈
    tiered_take_profit_enabled: bool = True
    take_profit_levels: List[Tuple[float, float]] = None  # [(触发条件，卖出比例)]

    def __post_init__(self):
        if self.take_profit_levels is None:
            # 默认三级止盈：涨 10% 卖 1/3，涨 20% 卖 1/3，涨 30% 清仓
            self.take_profit_levels = [
                (0.10, 0.33),  # 涨 10% 卖出 33%
                (0.20, 0.33),  # 涨 20% 卖出 33%
                (0.30, 0.34),  # 涨 30% 卖出 34%（清仓）
            ]


class EnhancedStopLoss:
    """
    增强止损管理器

    功能：
    - 移动止损：价格创新高后自动上移止损位
    - 时间止损：持仓 X 天不涨自动卖出
    - ATR 动态止损：根据波动率调整止损距离
    - 分级止盈：分批止盈锁定利润
    - 条件止损：技术面破位触发止损
    """

    def __init__(self, config: Optional[StopLossConfig] = None):
        self.config = config or StopLossConfig()

    def calculate_atr_stop(self, atr: float, current_price: float) -> float:
        """
        计算 ATR 动态止损距离

        Args:
            atr: ATR 值
            current_price: 当前价格

        Returns:
            止损距离比例
        """
        if atr <= 0 or current_price <= 0:
            return self.config.base_stop_loss

        # ATR 止损距离 = ATR * 倍数 / 价格
        atr_distance = self.config.atr_multiplier * atr / current_price

        # 限制在合理范围内
        atr_distance = max(
            self.config.min_atr_stop,
            min(self.config.max_atr_stop, atr_distance)
        )

        return atr_distance

    def calculate_trailing_stop(
        self,
        entry_price: float,
        current_price: float,
        highest_price: float,
    ) -> Optional[float]:
        """
        计算移动止损位

        Args:
            entry_price: 入场价
            current_price: 当前价
            highest_price: 持仓期最高价

        Returns:
            移动止损位（None 表示未触发）
        """
        if not self.config.trailing_stop_enabled:
            return None

        # 计算当前盈利
        profit_pct = (current_price - entry_price) / entry_price

        # 未达到启动阈值，不启用移动止损
        if profit_pct < self.config.trailing_stop_threshold:
            return None

        # 移动止损位 = 最高价 * (1 - 止损距离)
        trailing_stop = highest_price * (1 - self.config.trailing_stop_distance)

        # 确保不低于成本价（保护本金）
        if profit_pct > 0.10:  # 盈利超过 10%，可以放宽
            trailing_stop = max(trailing_stop, entry_price * 1.02)  # 至少赚 2%
        else:
            trailing_stop = max(trailing_stop, entry_price)  # 至少不亏

        return trailing_stop

    def check_time_stop(
        self,
        entry_time: datetime,
        current_time: datetime,
        entry_price: float,
        current_price: float,
        min_improvement: float = 0.02,
    ) -> Tuple[bool, str]:
        """
        检查时间止损

        Args:
            entry_time: 入场时间
            current_time: 当前时间
            entry_price: 入场价
            current_price: 当前价
            min_improvement: 最小盈利要求

        Returns:
            (是否触发，原因)
        """
        if not self.config.time_stop_enabled:
            return False, ""

        # 计算持仓天数（交易日）
        holding_days = (current_time - entry_time).days

        # 未达到时间止损天数
        if holding_days < self.config.time_stop_days:
            return False, ""

        # 计算当前盈利
        profit_pct = (current_price - entry_price) / entry_price

        # 盈利未达到要求
        if profit_pct < min_improvement:
            return True, f"时间止损 ({holding_days}天，盈利{profit_pct:.1%}<{min_improvement:.0%})"

        return False, ""

    def check_tiered_take_profit(
        self,
        entry_price: float,
        current_price: float,
        position_quantity: int,
        sold_quantity: int = 0,
    ) -> List[Dict]:
        """
        检查分级止盈

        Args:
            entry_price: 入场价
            current_price: 当前价
            position_quantity: 总持仓数量
            sold_quantity: 已卖出数量

        Returns:
            止盈操作列表
        """
        if not self.config.tiered_take_profit_enabled:
            return []

        actions = []
        remaining_qty = position_quantity - sold_quantity

        if remaining_qty <= 0:
            return actions

        # 计算当前盈利比例
        profit_pct = (current_price - entry_price) / entry_price

        # 检查每个止盈级别
        for trigger_pct, sell_ratio in self.config.take_profit_levels:
            if profit_pct >= trigger_pct:
                # 计算应卖出数量
                sell_qty = int(position_quantity * sell_ratio)

                # 确保不超过剩余持仓
                sell_qty = min(sell_qty, remaining_qty)

                if sell_qty > 0:
                    actions.append({
                        "action": "sell_partial",
                        "quantity": sell_qty,
                        "reason": f"止盈 {trigger_pct:.0%}",
                        "profit_pct": profit_pct,
                    })
                    remaining_qty -= sell_qty

        return actions

    def check_technical_stop(
        self,
        current_price: float,
        support_levels: List[float],
        ma20: Optional[float] = None,
        ma60: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """
        检查技术面止损

        Args:
            current_price: 当前价
            support_levels: 支撑位列表
            ma20: 20 日均线
            ma60: 60 日均线

        Returns:
            (是否触发，原因)
        """
        # 检查支撑位破位
        for support in support_levels:
            if current_price < support * 0.97:  # 破位 3%
                return True, f"支撑位破位 ({support:.2f})"

        # 检查均线破位（可选）
        if ma60 and current_price < ma60 * 0.95:
            return True, f"60 日均线破位 ({ma60:.2f})"

        return False, ""

    def update_stop_price(
        self,
        position: Dict,
        current_price: float,
        current_time: datetime,
        atr: Optional[float] = None,
        support_levels: Optional[List[float]] = None,
        ma20: Optional[float] = None,
        ma60: Optional[float] = None,
    ) -> Dict:
        """
        更新止损位（综合所有止损方法）

        Args:
            position: 持仓信息
            current_price: 当前价
            current_time: 当前时间
            atr: ATR 值
            support_levels: 支撑位
            ma20: 20 日均线
            ma60: 60 日均线

        Returns:
            更新后的止损信息
        """
        entry_price = position["avg_cost"]
        highest_price = position.get("highest_price", entry_price)
        entry_time = position.get("entry_time")

        # 1. 基础止损位
        if atr:
            base_stop_distance = self.calculate_atr_stop(atr, current_price)
        else:
            base_stop_distance = self.config.base_stop_loss

        base_stop_price = entry_price * (1 - base_stop_distance)

        # 2. 移动止损位
        trailing_stop = self.calculate_trailing_stop(
            entry_price, current_price, highest_price
        )

        # 3. 取较高的止损位（更严格）
        if trailing_stop:
            final_stop = max(base_stop_price, trailing_stop)
        else:
            final_stop = base_stop_price

        # 4. 技术面止损（如果破位，直接设置为止损位）
        if support_levels or ma60:
            tech_triggered, tech_reason = self.check_technical_stop(
                current_price,
                support_levels or [],
                ma20,
                ma60,
            )
            if tech_triggered:
                # 技术面破位，立即止损
                final_stop = min(final_stop, current_price * 0.97)

        return {
            "stop_price": final_stop,
            "trailing_stop": trailing_stop,
            "base_stop": base_stop_price,
            "is_trailing": trailing_stop is not None and trailing_stop > base_stop_price,
        }

    def should_exit(
        self,
        position: Dict,
        current_price: float,
        current_time: datetime,
        atr: Optional[float] = None,
        support_levels: Optional[List[float]] = None,
    ) -> Tuple[bool, str, str]:
        """
        综合判断是否应该退出

        Args:
            position: 持仓信息
            current_price: 当前价
            current_time: 当前时间
            atr: ATR 值
            support_levels: 支撑位

        Returns:
            (是否退出，退出原因，退出价格)
        """
        stop_price = position.get("stop_price")
        take_profit = position.get("take_profit")
        entry_price = position["avg_cost"]
        entry_time = position.get("entry_time")

        # 1. 检查止盈
        if take_profit and current_price >= take_profit:
            return True, "止盈", take_profit

        # 2. 检查止损
        if stop_price and current_price <= stop_price:
            return True, "止损", stop_price

        # 3. 检查时间止损
        if entry_time:
            time_triggered, time_reason = self.check_time_stop(
                entry_time, current_time, entry_price, current_price
            )
            if time_triggered:
                return True, time_reason, current_price

        # 4. 检查分级止盈
        partial_actions = self.check_tiered_take_profit(
            entry_price,
            current_price,
            position.get("quantity", 0),
            position.get("sold_quantity", 0),
        )
        if partial_actions:
            action = partial_actions[0]
            return True, action["reason"], current_price

        return False, "", None


# 辅助函数：在回测中使用
def create_position_with_enhanced_stoploss(
    code: str,
    entry_price: float,
    quantity: int,
    entry_time: datetime,
    atr: Optional[float] = None,
    config: Optional[StopLossConfig] = None,
) -> Dict:
    """
    创建带有增强止损的持仓

    Args:
        code: 股票代码
        entry_price: 入场价
        quantity: 数量
        entry_time: 入场时间
        atr: ATR 值
        config: 止损配置

    Returns:
        持仓字典
    """
    stoploss = EnhancedStopLoss(config)

    # 计算初始止损
    if atr:
        stop_distance = stoploss.calculate_atr_stop(atr, entry_price)
    else:
        stop_distance = config.base_stop_loss if config else 0.08

    stop_price = entry_price * (1 - stop_distance)

    # 计算止盈（盈亏比 2.5:1）
    take_profit = entry_price * (1 + stop_distance * 2.5)

    return {
        "code": code,
        "quantity": quantity,
        "avg_cost": entry_price,
        "entry_time": entry_time,
        "stop_price": stop_price,
        "take_profit": take_profit,
        "highest_price": entry_price,
        "sold_quantity": 0,
        "stop_loss_type": "ATR" if atr else "fixed",
    }
