"""
波动率分析模块 - ATR 动态止损基础
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import pandas as pd
import numpy as np

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class VolatilitySignal:
    """波动率信号"""
    atr: float                # 平均真实波幅
    atr_ratio: float          # ATR/价格 比率
    historical_volatility: float  # 历史波动率
    volatility_rank: float    # 波动率分位
    signal: str               # 高波/低波
    suggested_stop_distance: float  # 建议止损距离


class VolatilityAnalyzer:
    """
    波动率分析器

    功能：
    - ATR（平均真实波幅）计算
    - 历史波动率计算
    - 波动率分位分析
    - 动态止损距离建议
    """

    def __init__(
        self,
        atr_period: int = 14,
        hv_period: int = 20,
        lookback_period: int = 252,  # 一年交易日
    ):
        self.atr_period = atr_period
        self.hv_period = hv_period
        self.lookback_period = lookback_period

    def calculate_atr(self, df: pd.DataFrame) -> pd.Series:
        """计算 ATR（Average True Range）"""
        high = df['high']
        low = df['low']
        close = df['close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(span=self.atr_period, adjust=False).mean()
        return atr

    def get_current_atr(self, df: pd.DataFrame) -> float:
        """获取最新 ATR 值"""
        if len(df) < self.atr_period + 1:
            return 0.0
        atr = self.calculate_atr(df)
        return round(atr.iloc[-1], 4)

    def calculate_historical_volatility(self, df: pd.DataFrame) -> pd.Series:
        """计算历史波动率"""
        close = df['close']
        log_returns = np.log(close / close.shift(1))
        rolling_std = log_returns.rolling(window=self.hv_period).std()
        hv = rolling_std * np.sqrt(252)
        return hv

    def get_current_volatility(self, df: pd.DataFrame) -> float:
        """获取最新历史波动率"""
        if len(df) < self.hv_period + 1:
            return 0.0
        hv = self.calculate_historical_volatility(df)
        return round(hv.iloc[-1], 4)

    def calculate_volatility_rank(self, df: pd.DataFrame) -> float:
        """计算波动率分位"""
        if len(df) < self.lookback_period + self.hv_period:
            return 0.5
        hv = self.calculate_historical_volatility(df)
        hv_history = hv.iloc[-self.lookback_period:]
        current_hv = hv.iloc[-1]
        rank = (hv_history < current_hv).sum() / len(hv_history)
        return round(rank, 3)

    def get_suggested_stop_distance(
        self, df: pd.DataFrame, multiplier: float = 2.0,
        min_distance: float = 0.03, max_distance: float = 0.15,
    ) -> float:
        """获取建议止损距离"""
        if len(df) < self.atr_period + 1:
            return 0.08
        atr = self.calculate_atr(df)
        close = df['close']
        current_atr = atr.iloc[-1]
        current_price = close.iloc[-1]
        atr_distance = (current_atr * multiplier) / current_price
        stop_distance = max(min_distance, min(max_distance, atr_distance))
        return round(stop_distance, 4)

    def get_atr_based_stop_price(
        self, df: pd.DataFrame, entry_price: float,
        direction: str = "long", multiplier: float = 2.0,
    ) -> float:
        """计算基于 ATR 的止损价"""
        if len(df) < self.atr_period + 1:
            return entry_price * (1 - 0.08) if direction == "long" else entry_price * (1 + 0.08)
        atr = self.get_current_atr(df)
        atr_distance = atr * multiplier
        if direction == "long":
            stop_price = entry_price - atr_distance
        else:
            stop_price = entry_price + atr_distance
        return round(stop_price, 2)

    def get_trailing_stop_price(
        self, df: pd.DataFrame, entry_price: float, current_price: float,
        direction: str = "long", multiplier: float = 2.0,
    ) -> float:
        """计算移动止损价"""
        if len(df) < self.atr_period + 1:
            return entry_price
        atr = self.get_current_atr(df)
        atr_distance = atr * multiplier
        if direction == "long":
            highest = max(entry_price, current_price)
            stop_price = highest - atr_distance
            stop_price = max(stop_price, entry_price * (1 - 0.08))
        else:
            lowest = min(entry_price, current_price)
            stop_price = lowest + atr_distance
            stop_price = min(stop_price, entry_price * (1 + 0.08))
        return round(stop_price, 2)

    def analyze(self, df: pd.DataFrame) -> VolatilitySignal:
        """全面波动率分析"""
        if len(df) < self.atr_period + 1:
            return VolatilitySignal(0, 0, 0, 0.5, "unknown", 0.08)
        atr = self.get_current_atr(df)
        atr_ratio = (self.calculate_atr(df) / df['close']).iloc[-1]
        hv = self.get_current_volatility(df)
        vol_rank = self.calculate_volatility_rank(df)
        stop_distance = self.get_suggested_stop_distance(df)
        signal = "high" if vol_rank > 0.7 else ("low" if vol_rank < 0.3 else "normal")
        return VolatilitySignal(
            atr=atr, atr_ratio=round(atr_ratio, 4), historical_volatility=hv,
            volatility_rank=vol_rank, signal=signal, suggested_stop_distance=stop_distance,
        )


class DynamicStopLossManager:
    """动态止损管理器"""

    def __init__(self, atr_multiplier: float = 2.0, min_stop_distance: float = 0.03, max_stop_distance: float = 0.15):
        self.atr_multiplier = atr_multiplier
        self.min_stop_distance = min_stop_distance
        self.max_stop_distance = max_stop_distance
        self.analyzer = VolatilityAnalyzer()
        self.stop_levels: Dict[str, Dict] = {}

    def init_position(self, stock_code: str, stock_name: str, entry_price: float, df: pd.DataFrame):
        """初始化持仓止损"""
        stop_price = self.analyzer.get_atr_based_stop_price(df, entry_price, "long", self.atr_multiplier)
        self.stop_levels[stock_code] = {
            "stock_name": stock_name, "entry_price": entry_price,
            "current_stop": stop_price, "highest_price": entry_price, "trailing_activated": False,
        }
        logger.info(f"{stock_code} 初始止损价：{stop_price:.2f}")

    def update_stop_price(self, stock_code: str, current_price: float, df: pd.DataFrame, enable_trailing: bool = True) -> float:
        """更新止损价"""
        if stock_code not in self.stop_levels:
            return 0.0
        level = self.stop_levels[stock_code]
        entry_price = level["entry_price"]
        if current_price > level["highest_price"]:
            level["highest_price"] = current_price
        if enable_trailing and current_price > entry_price * 1.05:
            new_stop = self.analyzer.get_trailing_stop_price(df, entry_price, current_price, "long", self.atr_multiplier)
            level["trailing_activated"] = True
        else:
            new_stop = self.analyzer.get_atr_based_stop_price(df, entry_price, "long", self.atr_multiplier)
        if new_stop > level["current_stop"]:
            level["current_stop"] = new_stop
        return level["current_stop"]

    def check_stop_loss(self, stock_code: str, current_price: float) -> Tuple[bool, str]:
        """检查是否触发止损"""
        if stock_code not in self.stop_levels:
            return (False, "无止损记录")
        level = self.stop_levels[stock_code]
        stop_price = level["current_stop"]
        entry_price = level["entry_price"]
        if current_price <= stop_price:
            profit_rate = (current_price - entry_price) / entry_price
            return (True, f"触发止损 (止损价={stop_price:.2f}, 盈利率={profit_rate:.1%})")
        return (False, "未触发止损")

    def remove_position(self, stock_code: str):
        """移除持仓止损记录"""
        if stock_code in self.stop_levels:
            del self.stop_levels[stock_code]

    def get_stop_info(self, stock_code: str) -> Optional[Dict]:
        """获取止损信息"""
        return self.stop_levels.get(stock_code)


__all__ = ["VolatilityAnalyzer", "VolatilitySignal", "DynamicStopLossManager"]
