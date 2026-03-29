"""
V4 深度优化策略

核心问题诊断与解决：
1. 同一股票连续止损 → 添加股票强弱筛选，只做强势股
2. 震荡市频繁止损 → 震荡市使用网格策略或空仓
3. 止损距离固定 → 根据 ATR 和支撑位动态设置
4. 信号过于频繁 → 添加信号冷却期
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class V4Signal:
    """V4 信号"""
    stock_code: str
    signal: str  # buy/sell/hold
    price: float
    timestamp: datetime
    score: float
    reason: str
    stop_price: float
    take_profit: float
    position_ratio: float


class V4Strategy:
    """
    V4 深度优化策略

    优化点：
    1. 股票强弱排名 - 只做强势股
    2. 信号冷却期 - 避免频繁交易
    3. 支撑位止损 - 技术位止损而非固定比例
    4. 市场状态切换 - 趋势/震荡策略切换
    5. 成交量确认 - 放量买入，缩量观望
    """

    def __init__(self):
        # 策略参数
        self.adx_threshold = 25           # ADX 趋势阈值（从 30 降到 25）
        self.ma20_threshold = 0.02        # MA20 阈值（价格>MA20*1.02）
        self.rsi_buy_max = 65             # RSI 买入上限（从 70 降到 65）
        self.rsi_sell_max = 75            # RSI 卖出上限
        self.volume_ratio_buy = 1.5       # 买入成交量倍数（从 1.2 升到 1.5）
        self.cooling_period = 3           # 冷却期 3 天（同一股票卖出后 3 天内不买）
        self.min_stock_score = 0.3        # 最小股票得分

        # 股票强弱评分周期
        self.strength_lookback = 20       # 20 日强弱

        # 止损止盈
        self.base_stop_loss = 0.08        # 基础止损 8%
        self.base_take_profit = 0.20      # 基础止盈 20%
        self.atr_stop_mult = 2.5          # ATR 止损倍数（从 2.0 升到 2.5）

        # 冷却期记录
        self.last_sell_time: Dict[str, datetime] = {}

    def calculate_stock_strength(self, df: pd.DataFrame) -> float:
        """
        计算股票强弱得分

        维度：
        1. 20 日涨幅排名
        2. 相对强度（vs 大盘）
        3. 创新高能力
        4. 均线多头排列

        Returns:
            强弱得分 0-1
        """
        if len(df) < self.strength_lookback:
            return 0.5

        close = df['close'].values[-self.strength_lookback:]

        # 1. 20 日涨幅
        returns_20d = (close[-1] - close[0]) / close[0]

        # 2. 相对强度（简化：用涨幅代替）
        # 实际应该用 vs 指数涨幅
        rs_score = returns_20d

        # 3. 创新高能力
        high_20d = df['high'].values[-self.strength_lookback:]
        current_high = high_20d[-1]
        period_high = high_20d.max()
        new_high_score = (current_high - period_high) / period_high + 1

        # 4. 均线多头排列
        ma5 = df['close'].rolling(5).mean().values[-1]
        ma10 = df['close'].rolling(10).mean().values[-1]
        ma20 = df['close'].rolling(20).mean().values[-1]

        ma_bullish = 0
        if ma5 > ma10 > ma20:
            ma_bullish = 0.3
        elif ma5 > ma10:
            ma_bullish = 0.15

        # 综合得分
        strength_score = (
            rs_score * 3 +      # 涨幅权重 30%
            new_high_score * 2 +  # 新高权重 20%
            ma_bullish          # 均线权重 30%
        ) / 6

        # 归一化到 0-1
        strength_score = max(0, min(1, strength_score + 0.5))

        return strength_score

    def calculate_support_level(self, df: pd.DataFrame) -> float:
        """
        计算支撑位（用于设置止损）

        支撑位：
        1. 最近 N 日低点
        2. MA20
        3. 前一根 K 线低点

        Returns:
            支撑位价格
        """
        if len(df) < 10:
            return df['close'].iloc[-1] * 0.92

        # 最近 10 日最低点
        low_10d = df['low'].values[-10:].min()

        # MA20
        ma20 = df['close'].rolling(20).mean().iloc[-1]

        # 前一根 K 线低点
        prev_low = df['low'].iloc[-2] if len(df) > 1 else df['low'].iloc[-1]

        # 取最高支撑位
        support = max(low_10d, ma20, prev_low)

        return support

    def check_cooling_period(self, code: str, current_time: datetime) -> bool:
        """
        检查冷却期

        Args:
            code: 股票代码
            current_time: 当前时间

        Returns:
            是否可以买入
        """
        if code not in self.last_sell_time:
            return True

        days_since_sell = (current_time - self.last_sell_time[code]).days
        return days_since_sell >= self.cooling_period

    def record_sell(self, code: str, timestamp: datetime):
        """记录卖出时间"""
        self.last_sell_time[code] = timestamp

    def generate_signals(self, df: pd.DataFrame, stock_code: str) -> List[Dict]:
        """
        生成 V4 信号

        买入条件（全部满足）：
        1. 股票强弱得分 > 0.3
        2. ADX >= 25（趋势市）
        3. 价格 > MA20 * 1.02
        4. MA5 > MA10 > MA20（多头排列）
        5. MACD 金叉或 DIF > 0
        6. RSI < 65（未超买）
        7. 成交量放大 > 1.5 倍
        8. 不在冷却期

        卖出条件（任一满足）：
        1. 价格 < MA20 * 0.98
        2. RSI > 75
        3. 技术得分 < 0
        """
        signals = []
        if len(df) < 30:
            return signals

        # 计算指标
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']

        ma5 = close.rolling(5).mean()
        ma10 = close.rolling(10).mean()
        ma20 = close.rolling(20).mean()

        # MACD
        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        macd_dif = exp1 - exp2
        macd_dea = macd_dif.ewm(span=9, adjust=False).mean()

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        # ADX
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        tr_smooth = tr.ewm(span=14, adjust=False).mean()
        plus_di = 100 * (plus_dm.ewm(span=14, adjust=False).mean() / tr_smooth)
        minus_di = 100 * (minus_dm.ewm(span=14, adjust=False).mean() / tr_smooth)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.ewm(span=14, adjust=False).mean()

        # ATR
        atr = tr_smooth.iloc[-1]

        # 股票强弱得分
        strength_score = self.calculate_stock_strength(df)

        # 支撑位
        support = self.calculate_support_level(df)

        for i in range(30, len(df)):
            subset = df.iloc[:i+1].copy()

            current_price = float(df.iloc[i]['close'])
            current_volume = float(df.iloc[i]['volume'])

            # 获取指标值
            curr_ma5 = float(ma5.iloc[i])
            curr_ma10 = float(ma10.iloc[i])
            curr_ma20 = float(ma20.iloc[i])
            curr_macd = float(macd_dif.iloc[i])
            prev_macd = float(macd_dif.iloc[i-1])
            curr_rsi = float(rsi.iloc[i])
            curr_adx = float(adx.iloc[i])
            avg_volume = float(volume.iloc[i-20:i].mean()) if i >= 20 else float(volume.iloc[i])

            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

            # 获取日期
            trade_date = df.iloc[i].get("trade_date", str(i))
            if isinstance(trade_date, str):
                try:
                    trade_date = datetime.strptime(trade_date, "%Y%m%d")
                except:
                    trade_date = datetime(2024, 1, 1) + timedelta(days=i)

            # ========== 买入条件检查 ==========
            buy_conditions = []
            buy_score = 0

            # 条件 1: 股票强弱得分 > 0.3
            if strength_score > self.min_stock_score:
                buy_conditions.append("强势股")
                buy_score += 0.2
            else:
                # 弱势股，跳过
                signals.append({
                    "stock_code": stock_code,
                    "signal": "hold",
                    "timestamp": trade_date,
                    "price": current_price,
                    "reason": f"弱势股 (strength={strength_score:.2f})",
                })
                continue

            # 条件 2: ADX >= 25（趋势市）
            is_trend = curr_adx >= self.adx_threshold
            if is_trend:
                buy_conditions.append(f"趋势市 (ADX={curr_adx:.1f})")
                buy_score += 0.15
            else:
                signals.append({
                    "stock_code": stock_code,
                    "signal": "hold",
                    "timestamp": trade_date,
                    "price": current_price,
                    "reason": f"震荡市 (ADX={curr_adx:.1f}<{self.adx_threshold})",
                })
                continue

            # 条件 3: 价格 > MA20 * 1.02
            if current_price > curr_ma20 * (1 + self.ma20_threshold):
                buy_conditions.append("MA20 上方")
                buy_score += 0.15
            else:
                signals.append({
                    "stock_code": stock_code,
                    "signal": "hold",
                    "timestamp": trade_date,
                    "price": current_price,
                    "reason": f"价格<MA20 ({current_price:.2f}<{curr_ma20:.2f})",
                })
                continue

            # 条件 4: 多头排列
            if curr_ma5 > curr_ma10 > curr_ma20:
                buy_conditions.append("多头排列")
                buy_score += 0.2
            else:
                signals.append({
                    "stock_code": stock_code,
                    "signal": "hold",
                    "timestamp": trade_date,
                    "price": current_price,
                    "reason": "非多头排列",
                })
                continue

            # 条件 5: MACD 金叉或 DIF>0
            if curr_macd > 0 or (curr_macd > prev_macd and prev_macd <= 0):
                buy_conditions.append("MACD 多")
                buy_score += 0.15
            else:
                signals.append({
                    "stock_code": stock_code,
                    "signal": "hold",
                    "timestamp": trade_date,
                    "price": current_price,
                    "reason": "MACD 空",
                })
                continue

            # 条件 6: RSI < 65
            if curr_rsi < self.rsi_buy_max:
                buy_conditions.append(f"RSI={curr_rsi:.0f}")
                buy_score += 0.1
            else:
                signals.append({
                    "stock_code": stock_code,
                    "signal": "hold",
                    "timestamp": trade_date,
                    "price": current_price,
                    "reason": f"RSI 超买 ({curr_rsi:.0f}>{self.rsi_buy_max})",
                })
                continue

            # 条件 7: 成交量放大
            if volume_ratio > self.volume_ratio_buy:
                buy_conditions.append(f"放量 {volume_ratio:.1f}x")
                buy_score += 0.15
            else:
                signals.append({
                    "stock_code": stock_code,
                    "signal": "hold",
                    "timestamp": trade_date,
                    "price": current_price,
                    "reason": f"缩量 ({volume_ratio:.1f}x)",
                })
                continue

            # 条件 8: 冷却期检查
            if self.check_cooling_period(stock_code, trade_date):
                buy_conditions.append("非冷却期")
            else:
                days_left = self.cooling_period - (trade_date - self.last_sell_time[stock_code]).days
                signals.append({
                    "stock_code": stock_code,
                    "signal": "hold",
                    "timestamp": trade_date,
                    "price": current_price,
                    "reason": f"冷却期 (剩余{days_left}天)",
                })
                continue

            # ========== 所有条件满足，生成买入信号 ==========
            # 根据得分确定信号强度
            if buy_score >= 0.8:
                signal_type = "strong_buy"
                position_ratio = 0.25
            elif buy_score >= 0.6:
                signal_type = "buy"
                position_ratio = 0.15
            else:
                signal_type = "weak_buy"
                position_ratio = 0.08

            # 计算止损（支撑位下方 3%）
            stop_price = support * 0.97
            stop_distance = (current_price - stop_price) / current_price
            stop_distance = max(0.05, min(0.15, stop_distance))  # 限制在 5-15%

            signals.append({
                "stock_code": stock_code,
                "signal": signal_type,
                "timestamp": trade_date,
                "price": current_price,
                "reason": "; ".join(buy_conditions),
                "score": buy_score,
                "stop_distance": stop_distance,
                "position_ratio": position_ratio,
                "strength_score": strength_score,
                "atr": atr,
            })

            # ========== 卖出信号 ==========
        # 重新遍历生成卖出信号（针对持仓股票）
        for i in range(30, len(df)):
            subset = df.iloc[:i+1].copy()

            current_price = float(df.iloc[i]['close'])

            curr_ma20 = float(ma20.iloc[i])
            curr_rsi = float(rsi.iloc[i])
            curr_macd = float(macd_dif.iloc[i])
            prev_macd = float(macd_dif.iloc[i-1])

            trade_date = df.iloc[i].get("trade_date", str(i))
            if isinstance(trade_date, str):
                try:
                    trade_date = datetime.strptime(trade_date, "%Y%m%d")
                except:
                    trade_date = datetime(2024, 1, 1) + timedelta(days=i)

            sell_conditions = []
            sell_score = 0

            # 条件 1: 价格跌破 MA20
            if current_price < curr_ma20 * 0.98:
                sell_conditions.append("跌破 MA20")
                sell_score += 0.5

            # 条件 2: RSI 超买
            if curr_rsi > self.rsi_sell_max:
                sell_conditions.append(f"RSI={curr_rsi:.0f}")
                sell_score += 0.3

            # 条件 3: MACD 死叉
            if curr_macd < prev_macd and curr_macd < 0:
                sell_conditions.append("MACD 空")
                sell_score += 0.3

            # 条件 4: 跌破支撑位
            support = self.calculate_support_level(subset)
            if current_price < support * 0.97:
                sell_conditions.append("跌破支撑")
                sell_score += 0.5

            if sell_score >= 0.5:
                signals.append({
                    "stock_code": stock_code,
                    "signal": "sell",
                    "timestamp": trade_date,
                    "price": current_price,
                    "reason": "; ".join(sell_conditions),
                    "sell_score": sell_score,
                })

        return signals

    def get_strategy_status(self) -> Dict:
        """获取策略状态"""
        return {
            "cooling_stocks": len(self.last_sell_time),
            "adx_threshold": self.adx_threshold,
            "strength_lookback": self.strength_lookback,
            "stop_loss_mult": self.atr_stop_mult,
        }


# 辅助函数：在回测中使用
def create_v4_position(
    code: str,
    entry_price: float,
    quantity: int,
    entry_time: datetime,
    stop_distance: float,
    take_profit_distance: float,
) -> Dict:
    """创建 V4 持仓"""
    return {
        "code": code,
        "quantity": quantity,
        "avg_cost": entry_price,
        "entry_time": entry_time,
        "stop_price": entry_price * (1 - stop_distance),
        "take_profit": entry_price * (1 + take_profit_distance),
        "highest_price": entry_price,
        "sold_quantity": 0,
    }
