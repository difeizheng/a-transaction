"""
改进版交易策略模块 - 多条件确认 + ATR 动态止损

策略核心：
1. 趋势过滤 - 只在上升趋势中买入
2. 多条件确认 - MA+MACD+RSI 共振
3. ATR 动态止损 - 根据波动率调整
4. 分级止盈止损 - 不同信号强度不同策略
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
    signal: str              # buy/strong_buy/sell/strong_sell/hold
    price: float             # 当前价格
    timestamp: datetime      # 时间戳
    tech_score: float        # 技术得分
    buy_score: float         # 买入评分
    sell_score: float        # 卖出评分
    atr: float               # ATR 值
    stop_distance: float     # 止损距离
    take_profit_distance: float  # 止盈距离
    rsi: float               # RSI 值
    volume_ratio: float      # 成交量比率
    conditions: Dict         # 条件满足情况


@dataclass
class Position:
    """持仓信息"""
    stock_code: str
    stock_name: str
    quantity: int
    avg_cost: float
    entry_time: datetime
    stop_price: float        # 动态止损价
    take_profit: float       # 止盈价
    highest_price: float     # 持仓期最高价
    entry_signal: str        # 入场信号类型


class ImprovedStrategy:
    """
    优化版交易策略 V2

    买入条件（需同时满足至少 4 个）：
    1. 价格在 MA20 之上（趋势向上）+0.25 分
    2. MA20 向上（趋势确认）+0.25 分
    3. MA5 > MA10（短期强势）+0.15 分
    4. MACD 金叉或 DIF>0 +0.25 分
    5. RSI 35-65 且上升 +0.2 分
    6. 技术得分正面 +0.15 分
    7. 成交量放大 +0.15 分
    8. 价格创新高 +0.15 分

    买入阈值：>= 4 个条件且买分 >= 0.6
    强烈买入：>= 6 个条件且买分 >= 0.9

    卖出条件（需同时满足至少 3 个）：
    1. 价格在 MA20 之下 +0.35 分
    2. MA20 向下 +0.25 分
    3. MA5 < MA10 +0.15 分
    4. MACD 死叉或 DIF<0 +0.25 分
    5. RSI 超买或下降 +0.25 分

    卖出阈值：>= 3 个条件且卖分 >= 0.5
    强烈卖出：>= 5 个条件
    """

    def __init__(
        self,
        buy_threshold: float = 0.6,
        sell_threshold: float = 0.5,
        min_buy_conditions: int = 4,
        min_sell_conditions: int = 3,
        atr_multiplier: float = 2.5,
        min_stop_distance: float = 0.05,
        max_stop_distance: float = 0.15,
        profit_ratio: float = 3.0,
    ):
        """
        初始化策略

        Args:
            buy_threshold: 买入分数阈值
            sell_threshold: 卖出分数阈值
            min_buy_conditions: 最小买入条件数
            min_sell_conditions: 最小卖出条件数
            atr_multiplier: ATR 止损倍数
            min_stop_distance: 最小止损距离
            max_stop_distance: 最大止损距离
            profit_ratio: 止盈/止损比率
        """
        self.technical_analyzer = TechnicalAnalyzer()
        self.volatility_analyzer = VolatilityAnalyzer()

        # 策略参数
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.min_buy_conditions = min_buy_conditions
        self.min_sell_conditions = min_sell_conditions
        self.atr_multiplier = atr_multiplier
        self.min_stop_distance = min_stop_distance
        self.max_stop_distance = max_stop_distance
        self.profit_ratio = profit_ratio

        # 持仓管理
        self.positions: Dict[str, Position] = {}

        logger.info(f"改进策略初始化完成 - 买入阈值：{buy_threshold}, "
                   f"止损倍数：{atr_multiplier}, 止盈比：{profit_ratio}")

    def calculate_indicators(self, df: pd.DataFrame) -> Dict:
        """
        计算技术指标

        Returns:
            包含所有指标的字典
        """
        indicators = {}

        # 均线
        indicators['ma5'] = df['close'].rolling(5).mean()
        indicators['ma10'] = df['close'].rolling(10).mean()
        indicators['ma20'] = df['close'].rolling(20).mean()

        # MACD
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        indicators['macd_dif'] = exp1 - exp2
        indicators['macd_dea'] = indicators['macd_dif'].ewm(span=9, adjust=False).mean()

        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss
        indicators['rsi'] = 100 - (100 / (1 + rs))

        # ATR
        indicators['atr'] = self.volatility_analyzer.calculate_atr(df)

        # 成交量均线
        indicators['volume_ma20'] = df['volume'].rolling(20).mean()

        # N 日最高/最低
        indicators['high_n'] = df['high'].rolling(20).max()
        indicators['low_n'] = df['low'].rolling(20).min()

        return indicators

    def generate_signal(
        self,
        df: pd.DataFrame,
        stock_code: str,
        stock_name: str = "",
        timestamp: Optional[datetime] = None,
    ) -> StrategySignal:
        """
        生成策略信号

        Args:
            df: K 线数据（包含最新数据）
            stock_code: 股票代码
            stock_name: 股票名称
            timestamp: 时间戳

        Returns:
            StrategySignal 对象
        """
        if len(df) < 30:
            # 数据不足，返回 hold
            return StrategySignal(
                stock_code=stock_code,
                stock_name=stock_name,
                signal="hold",
                price=float(df['close'].iloc[-1]) if not df.empty else 0,
                timestamp=timestamp or datetime.now(),
                tech_score=0,
                buy_score=0,
                sell_score=0,
                atr=0,
                stop_distance=0.08,
                take_profit_distance=0.20,
                rsi=50,
                volume_ratio=1,
                conditions={},
            )

        # 计算指标
        ind = self.calculate_indicators(df)
        i = len(df) - 1  # 最新数据索引

        # 获取当前值
        current_price = float(df['close'].iloc[i])
        prev_price = float(df['close'].iloc[i-1]) if i > 0 else current_price

        curr_ma5 = float(ind['ma5'].iloc[i])
        curr_ma10 = float(ind['ma10'].iloc[i])
        curr_ma20 = float(ind['ma20'].iloc[i]) if i >= 20 else current_price

        curr_macd = float(ind['macd_dif'].iloc[i])
        prev_macd = float(ind['macd_dif'].iloc[i-1]) if i > 0 else 0

        curr_rsi = float(ind['rsi'].iloc[i]) if not pd.isna(ind['rsi'].iloc[i]) else 50
        prev_rsi = float(ind['rsi'].iloc[i-3]) if i >= 3 else curr_rsi  # 3 日前 RSI

        curr_volume = float(df['volume'].iloc[i])
        avg_volume = float(ind['volume_ma20'].iloc[i]) if i >= 20 else curr_volume
        volume_ratio = curr_volume / avg_volume if avg_volume > 0 else 1

        curr_high = float(df['high'].iloc[i])
        high_n = float(ind['high_n'].iloc[i])

        atr = float(ind['atr'].iloc[i]) if not pd.isna(ind['atr'].iloc[i]) else 0

        # 计算 MA20 趋势（5 日前 MA20）
        prev_ma20 = float(ind['ma20'].iloc[i-5]) if i >= 5 else curr_ma20

        # 技术分析得分
        tech_signal = self.technical_analyzer.analyze(df)
        tech_score = tech_signal.score

        # === 买入条件评分 ===
        buy_conditions = 0
        buy_score = 0
        buy_details = {}

        # 条件 1: 价格在 MA20 之上（趋势向上）
        cond1 = current_price > curr_ma20
        if cond1:
            buy_conditions += 1
            buy_score += 0.25
        buy_details['above_ma20'] = cond1

        # 条件 2: MA20 向上（趋势确认）
        cond2 = curr_ma20 > prev_ma20
        if cond2:
            buy_conditions += 1
            buy_score += 0.25
        buy_details['ma20_up'] = cond2

        # 条件 3: MA5 > MA10（短期强势）
        cond3 = curr_ma5 > curr_ma10
        if cond3:
            buy_conditions += 1
            buy_score += 0.15
        buy_details['ma5_above_ma10'] = cond3

        # 条件 4: MACD 金叉或 DIF>0
        cond4 = (curr_macd > 0) or (curr_macd > prev_macd and prev_macd <= 0)
        if cond4:
            buy_conditions += 1
            buy_score += 0.25
        buy_details['macd_bullish'] = cond4

        # 条件 5: RSI 未超买且上升 (35-65 区间且上升)
        cond5 = 35 < curr_rsi < 65 and curr_rsi > prev_rsi
        if cond5:
            buy_conditions += 1
            buy_score += 0.2
        buy_details['rsi_ok'] = cond5

        # 条件 6: 技术得分正面
        cond6 = tech_score > 0.1
        if cond6:
            buy_score += 0.15
        buy_details['tech_positive'] = cond6

        # 条件 7: 成交量放大
        cond7 = volume_ratio > 1.5
        if cond7:
            buy_score += 0.15
        buy_details['volume_up'] = cond7

        # 条件 8: 价格创新高
        cond8 = current_price >= high_n
        if cond8:
            buy_score += 0.15
        buy_details['new_high'] = cond8

        # === 卖出条件评分 ===
        sell_conditions = 0
        sell_score = 0
        sell_details = {}

        # 条件 1: 价格在 MA20 之下
        cond1_sell = current_price < curr_ma20
        if cond1_sell:
            sell_conditions += 1
            sell_score += 0.35
        sell_details['below_ma20'] = cond1_sell

        # 条件 2: MA20 向下
        cond2_sell = curr_ma20 < prev_ma20
        if cond2_sell:
            sell_conditions += 1
            sell_score += 0.25
        sell_details['ma20_down'] = cond2_sell

        # 条件 3: MA5 < MA10（短期走弱）
        cond3_sell = curr_ma5 < curr_ma10
        if cond3_sell:
            sell_conditions += 1
            sell_score += 0.15
        sell_details['ma5_below_ma10'] = cond3_sell

        # 条件 4: MACD 死叉或 DIF<0
        cond4_sell = (curr_macd < 0) or (curr_macd < prev_macd and prev_macd >= 0)
        if cond4_sell:
            sell_conditions += 1
            sell_score += 0.25
        sell_details['macd_bearish'] = cond4_sell

        # 条件 5: RSI 超买或下降
        cond5_sell = curr_rsi > 75 or (curr_rsi < prev_rsi and curr_rsi > 70)
        if cond5_sell:
            sell_conditions += 1
            sell_score += 0.25
        sell_details['rsi_overbought'] = cond5_sell

        # 条件 6: 技术得分负面
        cond6_sell = tech_score < -0.1
        if cond6_sell:
            sell_score += 0.15
        sell_details['tech_negative'] = cond6_sell

        # === 确定信号 ===
        if buy_conditions >= self.min_buy_conditions and buy_score >= self.buy_threshold:
            if buy_conditions >= 6 and buy_score >= 0.9:
                signal = "strong_buy"
            else:
                signal = "buy"
        elif sell_conditions >= self.min_sell_conditions and sell_score >= self.sell_threshold:
            if sell_conditions >= 5:
                signal = "strong_sell"
            else:
                signal = "sell"
        else:
            signal = "hold"

        # 计算止损距离（ATR 动态）
        if atr > 0:
            stop_distance = (atr * self.atr_multiplier) / current_price
            stop_distance = max(self.min_stop_distance, min(self.max_stop_distance, stop_distance))
        else:
            stop_distance = 0.08

        take_profit_distance = stop_distance * self.profit_ratio

        # 时间戳
        if timestamp is None:
            trade_date = df.iloc[i].get("trade_date", str(i))
            if isinstance(trade_date, str):
                try:
                    timestamp = datetime.strptime(trade_date, "%Y%m%d")
                except:
                    timestamp = datetime.now()
            else:
                timestamp = datetime.now()

        return StrategySignal(
            stock_code=stock_code,
            stock_name=stock_name,
            signal=signal,
            price=current_price,
            timestamp=timestamp,
            tech_score=tech_score,
            buy_score=buy_score,
            sell_score=sell_score,
            atr=round(atr, 4),
            stop_distance=round(stop_distance, 4),
            take_profit_distance=round(take_profit_distance, 4),
            rsi=round(curr_rsi, 2),
            volume_ratio=round(volume_ratio, 2),
            conditions={
                "buy_conditions": buy_conditions,
                "buy_score": buy_score,
                "sell_conditions": sell_conditions,
                "sell_score": sell_score,
                "buy_details": buy_details,
                "sell_details": sell_details,
            }
        )

    def update_position(
        self,
        signal: StrategySignal,
        quantity: int,
    ) -> Optional[Position]:
        """
        更新/创建持仓

        Args:
            signal: 买入信号
            quantity: 买入数量

        Returns:
            新建的持仓，如果已存在则返回 None
        """
        if signal.stock_code in self.positions:
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
        )

        self.positions[signal.stock_code] = position
        logger.info(f"新建持仓 {signal.stock_code}: 入场价={signal.price:.2f}, "
                   f"止损={stop_price:.2f}, 止盈={take_profit:.2f}")

        return position

    def check_exit(
        self,
        stock_code: str,
        current_price: float,
        timestamp: datetime,
    ) -> Optional[Tuple[Position, str, float]]:
        """
        检查是否应该退出持仓

        Args:
            stock_code: 股票代码
            current_price: 当前价格
            timestamp: 当前时间

        Returns:
            (持仓，退出原因，退出价格) 或 None
        """
        if stock_code not in self.positions:
            return None

        position = self.positions[stock_code]

        # 检查止损
        if current_price <= position.stop_price:
            return (position, "止损", position.stop_price)

        # 检查止盈
        if current_price >= position.take_profit:
            return (position, "止盈", position.take_profit)

        return None

    def update_trailing_stop(
        self,
        stock_code: str,
        current_price: float,
        stop_distance: float,
    ) -> float:
        """
        更新跟踪止损

        Args:
            stock_code: 股票代码
            current_price: 当前价格
            stop_distance: 止损距离

        Returns:
            新的止损价
        """
        if stock_code not in self.positions:
            return 0

        position = self.positions[stock_code]

        # 更新最高价
        if current_price > position.highest_price:
            position.highest_price = current_price
            # 上移止损
            new_stop = current_price * (1 - stop_distance)
            if new_stop > position.stop_price:
                position.stop_price = new_stop
                logger.debug(f"{stock_code}: 上移止损至 {new_stop:.2f}")

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
        }

    def get_all_positions(self) -> List[Dict]:
        """获取所有持仓"""
        return [self.get_position_info(code) for code in self.positions]

    def get_portfolio_value(self, current_prices: Dict[str, float]) -> Tuple[float, float]:
        """
        计算组合总价值

        Args:
            current_prices: 各股票当前价格

        Returns:
            (持仓市值，现金占用)
        """
        position_value = 0
        cost_basis = 0

        for code, pos in self.positions.items():
            if code in current_prices:
                price = current_prices[code]
                position_value += pos.quantity * price
                cost_basis += pos.quantity * pos.avg_cost

        return position_value, cost_basis


__all__ = [
    "ImprovedStrategy",
    "StrategySignal",
    "Position",
]
