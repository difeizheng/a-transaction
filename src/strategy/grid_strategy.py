"""
震荡市网格交易策略

适用场景：
- ADX < 30 的震荡市场
- 箱体震荡行情
- 无明确趋势的横盘阶段

策略逻辑：
1. 识别震荡区间（箱体上下沿）
2. 在区间内设置网格
3. 低买高卖，赚取波动差价
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import numpy as np
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class GridConfig:
    """网格配置"""
    # 网格参数
    grid_num: int = 5  # 网格数量
    min_grid_profit: float = 0.02  # 最小网格利润 2%
    max_grid_profit: float = 0.05  # 最大网格利润 5%

    # 仓位管理
    base_position: float = 0.1  # 基础仓位 10%
    max_position: float = 0.3   # 最大仓位 30%
    min_position: float = 0.05  # 最小仓位 5%

    # 震荡判断
    adx_threshold: float = 30  # ADX 阈值
    range_threshold: float = 0.15  # 箱体振幅阈值 15%

    # 止损止盈
    stop_loss: float = 0.08  # 止损 8%
    take_profit: float = 0.20  # 止盈 20%

    # 突破处理
    breakout_stop: bool = True  # 突破箱体时止损
    breakout_follow: bool = True  # 突破后是否跟随趋势


@dataclass
class GridLevel:
    """网格档位"""
    price: float  # 价格位
    type: str  # buy/sell
    quantity: int  # 数量
    triggered: bool = False  # 是否已触发


@dataclass
class RangeBox:
    """箱体区间"""
    upper: float  # 箱顶
    lower: float  # 箱底
    middle: float  # 中轴
    range_pct: float  # 振幅百分比
    confidence: float  # 置信度


class GridStrategy:
    """
    网格交易策略

    核心逻辑：
    1. 识别震荡区间
    2. 设置买入/卖出网格
    3. 自动低买高卖
    4. 突破时止损或跟随
    """

    def __init__(self, config: Optional[GridConfig] = None):
        self.config = config or GridConfig()
        self.grid_levels: List[GridLevel] = []
        self.current_box: Optional[RangeBox] = None
        self.position = 0  # 当前持仓数量
        self.avg_cost = 0  # 持仓成本

    def identify_range_box(
        self,
        df: pd.DataFrame,
        lookback_days: int = 30,
    ) -> Optional[RangeBox]:
        """
        识别箱体区间

        Args:
            df: K 线数据
            lookback_days: 回看天数

        Returns:
            箱体区间（None 表示未形成箱体）
        """
        if len(df) < lookback_days:
            return None

        # 获取最近 N 天数据
        recent = df.iloc[-lookback_days:].copy()

        # 箱顶：阻力位（多个高点）
        # 箱底：支撑位（多个低点）
        highs = recent["high"].values
        lows = recent["low"].values
        closes = recent["close"].values

        # 寻找阻力位（上影线高点）
        upper_candidates = []
        for i in range(1, len(highs) - 1):
            if highs[i] >= highs[i-1] and highs[i] >= highs[i+1]:
                if highs[i] >= closes[i]:  # 上影线
                    upper_candidates.append(highs[i])

        # 寻找支撑位（下影线低点）
        lower_candidates = []
        for i in range(1, len(lows) - 1):
            if lows[i] <= lows[i-1] and lows[i] <= lows[i+1]:
                if lows[i] <= closes[i]:  # 下影线
                    lower_candidates.append(lows[i])

        # 如果没有明确的支撑阻力，使用高低点
        if not upper_candidates:
            upper_candidates = [highs.max()]
        if not lower_candidates:
            lower_candidates = [lows.min()]

        # 箱顶：阻力位区域的上限
        upper = max(upper_candidates) * 0.99  # 稍微留点空间
        lower = min(lower_candidates) * 1.01

        # 计算振幅
        range_pct = (upper - lower) / lower

        # 如果振幅太小，不适合网格
        if range_pct < 0.05:
            return None

        # 计算中轴
        middle = (upper + lower) / 2

        # 计算置信度（触及次数越多，置信度越高）
        touch_upper = sum(1 for h in highs if abs(h - upper) / upper < 0.02)
        touch_lower = sum(1 for l in lows if abs(l - lower) / lower < 0.02)
        confidence = min(1.0, (touch_upper + touch_lower) / 10)

        return RangeBox(
            upper=upper,
            lower=lower,
            middle=middle,
            range_pct=range_pct,
            confidence=confidence,
        )

    def setup_grids(
        self,
        current_price: float,
        total_capital: float,
        box: RangeBox,
    ) -> List[GridLevel]:
        """
        设置网格

        Args:
            current_price: 当前价
            total_capital: 总资金
            box: 箱体区间

        Returns:
            网格档位列表
        """
        grids = []

        # 计算网格间距
        grid_range = box.upper - box.lower
        grid_step = grid_range / self.config.grid_num

        # 确保最小利润
        min_step = current_price * self.config.min_grid_profit
        if grid_step < min_step:
            grid_step = min_step
            grid_range = grid_step * self.config.grid_num

        # 买入网格（在箱底到中轴之间）
        buy_zones = int(self.config.grid_num / 2)
        for i in range(1, buy_zones + 1):
            buy_price = box.lower + (box.middle - box.lower) / buy_zones * i
            if buy_price < current_price * 1.05:  # 在当前价下方 5% 内
                # 计算买入数量（总资金的 base_position / grid_num）
                buy_qty = int(
                    total_capital * self.config.base_position / self.config.grid_num
                    / buy_price / 100
                ) * 100

                if buy_qty > 0:
                    grids.append(GridLevel(
                        price=round(buy_price, 2),
                        type="buy",
                        quantity=buy_qty,
                        triggered=False,
                    ))

        # 卖出网格（在中轴到箱顶之间）
        sell_zones = int(self.config.grid_num / 2)
        for i in range(1, sell_zones + 1):
            sell_price = box.middle + (box.upper - box.middle) / sell_zones * i
            if sell_price > current_price * 0.95:  # 在当前价上方 5% 内
                # 卖出数量为持仓的一部分
                sell_qty = int(self.position / sell_zones / 100) * 100

                if sell_qty > 0:
                    grids.append(GridLevel(
                        price=round(sell_price, 2),
                        type="sell",
                        quantity=sell_qty,
                        triggered=False,
                    ))

        self.grid_levels = grids
        return grids

    def check_grid_trigger(
        self,
        current_price: float,
        timestamp: datetime,
    ) -> List[Dict]:
        """
        检查网格触发

        Args:
            current_price: 当前价
            timestamp: 当前时间

        Returns:
            触发的操作列表
        """
        actions = []

        for grid in self.grid_levels:
            if grid.triggered:
                continue

            # 买入网格触发
            if grid.type == "buy" and current_price <= grid.price:
                actions.append({
                    "action": "buy",
                    "quantity": grid.quantity,
                    "price": grid.price,
                    "reason": f"网格买入 @{grid.price:.2f}",
                    "grid_type": "buy",
                })
                grid.triggered = True

            # 卖出网格触发
            elif grid.type == "sell" and current_price >= grid.price:
                actions.append({
                    "action": "sell",
                    "quantity": grid.quantity,
                    "price": grid.price,
                    "reason": f"网格卖出 @{grid.price:.2f}",
                    "grid_type": "sell",
                })
                grid.triggered = True

            # 重置网格（价格回到中间）
            elif grid.triggered:
                if grid.type == "buy" and current_price >= grid.price * 1.02:
                    grid.triggered = False
                elif grid.type == "sell" and current_price <= grid.price * 0.98:
                    grid.triggered = False

        return actions

    def check_breakout(
        self,
        current_price: float,
        box: RangeBox,
    ) -> Tuple[bool, str, str]:
        """
        检查突破

        Args:
            current_price: 当前价
            box: 箱体区间

        Returns:
            (是否突破，突破方向，突破价格)
        """
        # 向上突破
        if current_price > box.upper * 1.03:
            return True, "up", box.upper

        # 向下跌破
        if current_price < box.lower * 0.97:
            return True, "down", box.lower

        return False, "", ""

    def handle_breakout(
        self,
        breakout_direction: str,
        current_price: float,
        position: Dict,
    ) -> Tuple[bool, str]:
        """
        处理突破

        Args:
            breakout_direction: 突破方向 (up/down)
            current_price: 当前价
            position: 持仓信息

        Returns:
            (是否卖出，原因)
        """
        if breakout_direction == "up":
            if self.config.breakout_follow:
                # 向上突破，跟随趋势（不卖出，可能加仓）
                return False, "向上突破，持有"
            else:
                # 向上突破，止盈
                return True, "向上突破止盈"

        elif breakout_direction == "down":
            if self.config.breakout_stop:
                # 向下跌破，止损
                return True, "向下跌破止损"
            else:
                # 向下跌破，加仓（逆势）
                return False, "向下跌破，考虑加仓"

        return False, ""

    def should_use_grid(
        self,
        adx: float,
        df: pd.DataFrame,
    ) -> Tuple[bool, str]:
        """
        判断是否应该使用网格策略

        Args:
            adx: ADX 值
            df: K 线数据

        Returns:
            (是否使用，原因)
        """
        # 1. 检查 ADX
        if adx >= self.config.adx_threshold:
            return False, f"ADX={adx:.1f} >= {self.config.adx_threshold}，趋势市"

        # 2. 检查箱体
        box = self.identify_range_box(df)
        if not box:
            return False, "未形成明显箱体"

        if box.confidence < 0.5:
            return False, f"箱体置信度低 ({box.confidence:.2f})"

        self.current_box = box
        return True, f"震荡市 (ADX={adx:.1f}, 箱体置信度={box.confidence:.2f})"

    def get_grid_status(self) -> Dict:
        """获取网格状态"""
        if not self.grid_levels:
            return {"status": "no_grids"}

        buy_grids = [g for g in self.grid_levels if g.type == "buy"]
        sell_grids = [g for g in self.grid_levels if g.type == "sell"]

        triggered_buy = sum(1 for g in buy_grids if g.triggered)
        triggered_sell = sum(1 for g in sell_grids if g.triggered)

        return {
            "status": "active",
            "box_upper": self.current_box.upper if self.current_box else None,
            "box_lower": self.current_box.lower if self.current_box else None,
            "box_middle": self.current_box.middle if self.current_box else None,
            "buy_grids": len(buy_grids),
            "sell_grids": len(sell_grids),
            "triggered_buy": triggered_buy,
            "triggered_sell": triggered_sell,
            "position": self.position,
        }


# 集成到回测系统的辅助函数
def create_grid_position(
    code: str,
    entry_price: float,
    quantity: int,
    entry_time: datetime,
    grid_config: Optional[GridConfig] = None,
) -> Dict:
    """
    创建网格持仓

    Args:
        code: 股票代码
        entry_price: 入场价
        quantity: 数量
        entry_time: 入场时间
        grid_config: 网格配置

    Returns:
        持仓字典
    """
    config = grid_config or GridConfig()

    return {
        "code": code,
        "quantity": quantity,
        "avg_cost": entry_price,
        "entry_time": entry_time,
        "stop_price": entry_price * (1 - config.stop_loss),
        "take_profit": entry_price * (1 + config.take_profit),
        "highest_price": entry_price,
        "grid_type": True,
        "grid_triggered": [],
    }
