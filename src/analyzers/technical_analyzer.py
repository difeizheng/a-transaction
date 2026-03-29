"""
技术分析模块 - 计算各类技术指标
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import pandas as pd
import numpy as np

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TechnicalSignal:
    """技术信号"""
    ma_signal: str  # buy/sell/hold
    macd_signal: str
    rsi_signal: str
    kdj_signal: str
    boll_signal: str
    overall_signal: str  # 综合信号
    score: float  # 综合得分 [-1, 1]


class TechnicalAnalyzer:
    """
    技术分析器

    支持指标：
    - 均线系统 (MA)
    - MACD
    - RSI
    - KDJ
    - 布林带 (BOLL)
    """

    def __init__(
        self,
        ma_periods: List[int] = None,
        rsi_period: int = 14,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        kdj_n: int = 9,
    ):
        """
        初始化技术分析器

        Args:
            ma_periods: 均线周期列表
            rsi_period: RSI 周期
            macd_fast: MACD 快线周期
            macd_slow: MACD 慢线周期
            macd_signal: MACD 信号线周期
            kdj_n: KDJ 周期
        """
        self.ma_periods = ma_periods or [5, 10, 20, 60]
        self.rsi_period = rsi_period
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal_period = macd_signal
        self.kdj_n = kdj_n

    def analyze(self, df: pd.DataFrame) -> TechnicalSignal:
        """
        全面技术分析

        Args:
            df: DataFrame，包含 ohlcv 数据
                 必需列：open, high, low, close, volume

        Returns:
            技术信号
        """
        if df.empty or len(df) < self.macd_slow + self.macd_signal_period:
            return TechnicalSignal(
                ma_signal="hold",
                macd_signal="hold",
                rsi_signal="hold",
                kdj_signal="hold",
                boll_signal="hold",
                overall_signal="hold",
                score=0.0
            )

        # 计算各项指标
        ma_data = self.calculate_ma(df)
        macd_data = self.calculate_macd(df)
        rsi_data = self.calculate_rsi(df)
        kdj_data = self.calculate_kdj(df)
        boll_data = self.calculate_boll(df)

        # 新增指标
        obv_data = self.calculate_obv(df)
        bias_data = self.calculate_bias(df)
        vr_data = self.calculate_vr(df)

        # 生成各指标信号
        ma_signal = self._get_ma_signal(ma_data, df)
        macd_signal = self._get_macd_signal(macd_data)
        rsi_signal = self._get_rsi_signal(rsi_data)
        kdj_signal = self._get_kdj_signal(kdj_data)
        boll_signal = self._get_boll_signal(boll_data, df)

        # 计算综合得分（加入新指标权重）
        score = self._calculate_combined_score(
            ma_signal, macd_signal, rsi_signal, kdj_signal, boll_signal,
            obv_data, bias_data, vr_data
        )

        # 确定综合信号
        overall_signal = self._get_overall_signal(score)

        return TechnicalSignal(
            ma_signal=ma_signal,
            macd_signal=macd_signal,
            rsi_signal=rsi_signal,
            kdj_signal=kdj_signal,
            boll_signal=boll_signal,
            overall_signal=overall_signal,
            score=score
        )

    def calculate_ma(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """计算均线"""
        result = {}
        for period in self.ma_periods:
            result[f"ma{period}"] = df["close"].rolling(window=period).mean()
        return result

    def _get_ma_signal(self, ma_data: Dict[str, pd.Series], df: pd.DataFrame) -> str:
        """
        生成均线信号

        买入信号：
        - 短期均线上穿长期均线（金叉）
        - 价格站上多条均线

        卖出信号：
        - 短期均线下穿长期均线（死叉）
        - 价格跌破多条均线
        """
        if len(df) < max(self.ma_periods):
            return "hold"

        latest_close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2] if len(df) > 1 else latest_close

        buy_signals = 0
        sell_signals = 0

        # 检查价格与均线关系
        for i, period in enumerate(self.ma_periods):
            ma = ma_data[f"ma{period}"]
            if len(ma) < 2:
                continue

            current_ma = ma.iloc[-1]
            prev_ma = ma.iloc[-2]

            # 价格站上均线
            if prev_close <= prev_ma and latest_close > current_ma:
                buy_signals += 2
            elif prev_close >= prev_ma and latest_close < current_ma:
                sell_signals += 2

            # 均线多头/空头排列
            if i > 0:
                prev_period = self.ma_periods[i - 1]
                if ma_data[f"ma{prev_period}"].iloc[-1] > current_ma:
                    buy_signals += 1
                else:
                    sell_signals += 1

        # 金叉死叉检测
        if len(self.ma_periods) >= 2:
            ma_short = ma_data[f"ma{self.ma_periods[0]}"]
            ma_long = ma_data[f"ma{self.ma_periods[-1]}"]

            if len(ma_short) > 1 and len(ma_long) > 1:
                # 金叉：短均线上穿长均线
                if ma_short.iloc[-2] <= ma_long.iloc[-2] and ma_short.iloc[-1] > ma_long.iloc[-1]:
                    buy_signals += 3
                # 死叉：短均线下穿长均线
                elif ma_short.iloc[-2] >= ma_long.iloc[-2] and ma_short.iloc[-1] < ma_long.iloc[-1]:
                    sell_signals += 3

        if buy_signals >= sell_signals + 2:
            return "buy"
        elif sell_signals >= buy_signals + 2:
            return "sell"
        return "hold"

    def calculate_macd(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """
        计算 MACD

        DIF = EMA(close, fast) - EMA(close, slow)
        DEA = EMA(DIF, signal)
        MACD 柱 = (DIF - DEA) * 2
        """
        close = df["close"]

        ema_fast = close.ewm(span=self.macd_fast, adjust=False).mean()
        ema_slow = close.ewm(span=self.macd_slow, adjust=False).mean()

        dif = ema_fast - ema_slow
        dea = dif.ewm(span=self.macd_signal_period, adjust=False).mean()
        macd_hist = (dif - dea) * 2

        return {
            "dif": dif,
            "dea": dea,
            "macd_hist": macd_hist,
        }

    def _get_macd_signal(self, macd_data: Dict[str, pd.Series]) -> str:
        """
        生成 MACD 信号

        买入信号：
        - DIF 上穿 DEA（金叉）
        - MACD 柱由负转正

        卖出信号：
        - DIF 下穿 DEA（死叉）
        - MACD 柱由正转负
        """
        dif = macd_data["dif"]
        dea = macd_data["dea"]
        macd_hist = macd_data["macd_hist"]

        if len(dif) < 2:
            return "hold"

        # 金叉死叉
        dif_cross_up = dif.iloc[-2] <= dea.iloc[-2] and dif.iloc[-1] > dea.iloc[-1]
        dif_cross_down = dif.iloc[-2] >= dea.iloc[-2] and dif.iloc[-1] < dea.iloc[-1]

        # MACD 柱转正/转负
        hist_turn_positive = macd_hist.iloc[-2] <= 0 and macd_hist.iloc[-1] > 0
        hist_turn_negative = macd_hist.iloc[-2] >= 0 and macd_hist.iloc[-1] < 0

        if dif_cross_up or hist_turn_positive:
            return "buy"
        elif dif_cross_down or hist_turn_negative:
            return "sell"
        return "hold"

    def calculate_rsi(self, df: pd.DataFrame) -> pd.Series:
        """
        计算 RSI

        RSI = 100 - 100 / (1 + RS)
        RS = 平均涨幅 / 平均跌幅
        """
        close = df["close"]
        delta = close.diff()

        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.rolling(window=self.rsi_period).mean()
        avg_loss = loss.rolling(window=self.rsi_period).mean()

        rs = avg_gain / avg_loss.replace(0, np.inf)
        rsi = 100 - 100 / (1 + rs)

        return rsi.fillna(50)

    def _get_rsi_signal(self, rsi: pd.Series) -> str:
        """
        生成 RSI 信号

        RSI > 70: 超买，考虑卖出
        RSI < 30: 超卖，考虑买入
        """
        if len(rsi) < 1:
            return "hold"

        current_rsi = rsi.iloc[-1]

        if current_rsi < 25:
            return "buy"  # 严重超卖
        elif current_rsi < 35:
            return "buy"  # 超卖
        elif current_rsi > 75:
            return "sell"  # 严重超买
        elif current_rsi > 70:
            return "sell"  # 超买
        return "hold"

    def calculate_kdj(
        self, df: pd.DataFrame
    ) -> Dict[str, pd.Series]:
        """
        计算 KDJ

        RSV = (close - lowest) / (highest - lowest) * 100
        K = EMA(RSV)
        D = EMA(K)
        J = 3*K - 2*D
        """
        low = df["low"]
        high = df["high"]
        close = df["close"]

        lowest = low.rolling(window=self.kdj_n).min()
        highest = high.rolling(window=self.kdj_n).max()

        rsv = (close - lowest) / (highest - lowest).replace(0, np.inf) * 100
        rsv = rsv.fillna(50)

        k = rsv.ewm(com=2, adjust=False).mean()
        d = k.ewm(com=2, adjust=False).mean()
        j = 3 * k - 2 * d

        return {"k": k, "d": d, "j": j}

    def _get_kdj_signal(self, kdj_data: Dict[str, pd.Series]) -> str:
        """
        生成 KDJ 信号

        K/D < 20: 超卖，金叉买入
        K/D > 80: 超买，死叉卖出
        """
        k = kdj_data["k"]
        d = kdj_data["d"]

        if len(k) < 2:
            return "hold"

        current_k = k.iloc[-1]
        current_d = d.iloc[-1]
        prev_k = k.iloc[-2]
        prev_d = d.iloc[-2]

        # 金叉：K 线上穿 D 线
        golden_cross = prev_k <= prev_d and current_k > current_d
        # 死叉：K 线下穿 D 线
        death_cross = prev_k >= prev_d and current_k < current_d

        # 超买超卖区
        in_oversold = current_k < 20 and current_d < 20
        in_overbought = current_k > 80 and current_d > 80

        if in_oversold and golden_cross:
            return "buy"
        elif in_overbought and death_cross:
            return "sell"
        elif in_oversold:
            return "buy"
        elif in_overbought:
            return "sell"
        return "hold"

    def calculate_boll(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """
        计算布林带

        中轨 = MA(close, 20)
        上轨 = 中轨 + 2*STD(close, 20)
        下轨 = 中轨 - 2*STD(close, 20)
        """
        close = df["close"]
        period = 20

        middle = close.rolling(window=period).mean()
        std = close.rolling(window=period).std()
        upper = middle + 2 * std
        lower = middle - 2 * std

        return {"upper": upper, "middle": middle, "lower": lower}

    def _get_boll_signal(
        self, boll_data: Dict[str, pd.Series], df: pd.DataFrame
    ) -> str:
        """
        生成布林带信号

        价格触及下轨：可能反弹，买入
        价格触及上轨：可能回落，卖出
        价格突破上轨：强势，持有
        价格跌破下轨：弱势，观望
        """
        close = df["close"]
        upper = boll_data["upper"]
        lower = boll_data["lower"]
        middle = boll_data["middle"]

        if len(close) < 1:
            return "hold"

        current_close = close.iloc[-1]
        current_upper = upper.iloc[-1]
        current_lower = lower.iloc[-1]
        current_middle = middle.iloc[-1]

        # 价格位置
        if current_close <= current_lower * 1.01:  # 触及或跌破下轨
            return "buy"  # 可能反弹
        elif current_close >= current_upper * 0.99:  # 触及或突破上轨
            if current_close > current_upper:
                return "hold"  # 强势突破，持有
            else:
                return "sell"  # 触及上轨可能回落
        elif current_close < current_middle:
            return "hold"  # 在中轨下方，观望
        return "hold"

    def _calculate_combined_score(
        self,
        ma_signal: str,
        macd_signal: str,
        rsi_signal: str,
        kdj_signal: str,
        boll_signal: str,
        obv_data: pd.Series = None,
        bias_data: Dict[str, pd.Series] = None,
        vr_data: pd.Series = None,
    ) -> float:
        """
        计算综合得分

        权重分配（加入新指标后重新调整）：
        - MA: 20%
        - MACD: 20%
        - RSI: 12%
        - KDJ: 12%
        - BOLL: 16%
        - OBV: 10%
        - BIAS: 5%
        - VR: 5%
        """
        signal_score = {
            "buy": 1.0,
            "hold": 0.0,
            "sell": -1.0,
        }

        # 基础指标权重
        weights = {
            "ma": 0.20,
            "macd": 0.20,
            "rsi": 0.12,
            "kdj": 0.12,
            "boll": 0.16,
        }

        score = (
            signal_score.get(ma_signal, 0) * weights["ma"] +
            signal_score.get(macd_signal, 0) * weights["macd"] +
            signal_score.get(rsi_signal, 0) * weights["rsi"] +
            signal_score.get(kdj_signal, 0) * weights["kdj"] +
            signal_score.get(boll_signal, 0) * weights["boll"]
        )

        # OBV 信号（10%）：OBV 上升为正
        if obv_data is not None and len(obv_data) > 5:
            obv_up = obv_data.iloc[-1] > obv_data.iloc[-5]
            score += (0.5 if obv_up else -0.5) * 0.10

        # BIAS 信号（5%）：乖离率过大为负
        if bias_data is not None and "bias6" in bias_data:
            bias6 = bias_data["bias6"].iloc[-1] if not pd.isna(bias_data["bias6"].iloc[-1]) else 0
            if abs(bias6) > 10:
                score += (-0.5 if bias6 > 0 else 0.5) * 0.05  # 乖离过大要反向

        # VR 信号（5%）：VR>150 过热，VR<50 过冷
        if vr_data is not None and len(vr_data) > 0:
            vr = vr_data.iloc[-1] if not pd.isna(vr_data.iloc[-1]) else 100
            if vr > 200:
                score += -0.5 * 0.05  # VR 过高，警惕回调
            elif vr > 150:
                score += -0.25 * 0.05
            elif vr < 50:
                score += 0.5 * 0.05  # VR 过低，可能反弹
            elif vr < 75:
                score += 0.25 * 0.05

        return max(-1.0, min(1.0, score))

    def _get_overall_signal(self, score: float) -> str:
        """根据综合得分确定信号"""
        if score >= 0.5:
            return "strong_buy"
        elif score >= 0.2:
            return "buy"
        elif score >= -0.2:
            return "hold"
        elif score >= -0.5:
            return "sell"
        else:
            return "strong_sell"

    def get_indicators(self, df: pd.DataFrame) -> Dict:
        """
        获取所有技术指标数据

        Args:
            df: 行情数据

        Returns:
            包含所有指标的字典
        """
        ma = self.calculate_ma(df)
        macd = self.calculate_macd(df)
        rsi = self.calculate_rsi(df)
        kdj = self.calculate_kdj(df)
        boll = self.calculate_boll(df)
        obv = self.calculate_obv(df)
        bias = self.calculate_bias(df)
        vr = self.calculate_vr(df)

        # 获取最新值
        latest = {
            "ma": {k: round(v.iloc[-1], 2) for k, v in ma.items() if not pd.isna(v.iloc[-1])},
            "macd": {
                "dif": round(macd["dif"].iloc[-1], 4) if not pd.isna(macd["dif"].iloc[-1]) else 0,
                "dea": round(macd["dea"].iloc[-1], 4) if not pd.isna(macd["dea"].iloc[-1]) else 0,
                "hist": round(macd["macd_hist"].iloc[-1], 4) if not pd.isna(macd["macd_hist"].iloc[-1]) else 0,
            },
            "rsi": round(rsi.iloc[-1], 2) if not pd.isna(rsi.iloc[-1]) else 50,
            "kdj": {
                "k": round(kdj["k"].iloc[-1], 2) if not pd.isna(kdj["k"].iloc[-1]) else 50,
                "d": round(kdj["d"].iloc[-1], 2) if not pd.isna(kdj["d"].iloc[-1]) else 50,
                "j": round(kdj["j"].iloc[-1], 2) if not pd.isna(kdj["j"].iloc[-1]) else 50,
            },
            "boll": {
                "upper": round(boll["upper"].iloc[-1], 2) if not pd.isna(boll["upper"].iloc[-1]) else 0,
                "middle": round(boll["middle"].iloc[-1], 2) if not pd.isna(boll["middle"].iloc[-1]) else 0,
                "lower": round(boll["lower"].iloc[-1], 2) if not pd.isna(boll["lower"].iloc[-1]) else 0,
            },
            "obv": round(obv.iloc[-1], 0) if not pd.isna(obv.iloc[-1]) else 0,
            "bias": {
                "bias6": round(bias["bias6"].iloc[-1], 2) if not pd.isna(bias["bias6"].iloc[-1]) else 0,
                "bias12": round(bias["bias12"].iloc[-1], 2) if not pd.isna(bias["bias12"].iloc[-1]) else 0,
                "bias24": round(bias["bias24"].iloc[-1], 2) if not pd.isna(bias["bias24"].iloc[-1]) else 0,
            },
            "vr": round(vr.iloc[-1], 2) if not pd.isna(vr.iloc[-1]) else 100,
        }

        return latest

    def calculate_obv(self, df: pd.DataFrame) -> pd.Series:
        """
        计算 OBV (On-Balance Volume) 能量潮

        OBV = 前一日 OBV + 当日成交量 (当日收盘价>前一日收盘价)
            = 前一日 OBV - 当日成交量 (当日收盘价<前一日收盘价)
            = 前一日 OBV (当日收盘价=前一日收盘价)

        Args:
            df: 行情数据

        Returns:
            OBV 序列
        """
        close = df['close']
        volume = df['volume']

        # 价格变化方向
        price_change = close.diff()
        direction = price_change.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))

        # OBV 计算
        obv = (direction * volume).cumsum()

        return obv.fillna(0)

    def calculate_bias(self, df: pd.DataFrame, periods: List[int] = None) -> Dict[str, pd.Series]:
        """
        计算 BIAS (乖离率)

        BIAS = (收盘价 - MA) / MA * 100

        Args:
            df: 行情数据
            periods: 均线周期列表，默认 [6, 12, 24]

        Returns:
            BIAS 字典
        """
        if periods is None:
            periods = [6, 12, 24]

        close = df['close']
        result = {}

        for period in periods:
            ma = close.rolling(window=period).mean()
            bias = (close - ma) / ma * 100
            result[f"bias{period}"] = bias

        return result

    def calculate_vr(self, df: pd.DataFrame, period: int = 26) -> pd.Series:
        """
        计算 VR (Volume Ratio) 成交量比率

        VR = (上涨日成交量之和 + 1/2 平盘日成交量之和) / (下跌日成交量之和 + 1/2 平盘日成交量之和) * 100

        Args:
            df: 行情数据
            period: 统计周期，默认 26

        Returns:
            VR 序列
        """
        close = df['close']
        volume = df['volume']

        # 价格变化
        price_change = close.diff()

        # 上涨日、下跌日、平盘日成交量
        up_vol = volume.where(price_change > 0, 0)
        down_vol = volume.where(price_change < 0, 0)
        flat_vol = volume.where(price_change == 0, 0)

        # 滚动求和
        up_sum = up_vol.rolling(window=period).sum()
        down_sum = down_vol.rolling(window=period).sum()
        flat_sum = flat_vol.rolling(window=period).sum()

        # VR 计算
        vr = (up_sum + 0.5 * flat_sum) / (down_sum + 0.5 * flat_sum) * 100

        return vr.fillna(100)


__all__ = ["TechnicalAnalyzer", "TechnicalSignal"]
