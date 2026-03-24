"""
市场状态判断模块 - 识别牛市/熊市/震荡市

功能：
- 根据沪深 300 指数判断市场趋势
- 识别牛市/熊市/震荡市
- 提供市场状态评分用于动态调整策略参数
"""
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MarketRegimeSignal:
    """市场状态信号"""
    regime: str                    # bull/bear/oscillating
    trend_score: float             # 趋势得分 [-1, 1]
    breadth_score: float           # 市场宽度得分 [-1, 1]
    volume_score: float            # 成交量得分 [-1, 1]
    composite_score: float         # 综合得分 [-1, 1]
    is_oscillating: bool           # 是否震荡市
    suggestion: str                # 操作建议


class MarketRegimeAnalyzer:
    """
    市场状态分析器

    判断逻辑：
    1. 趋势判断：沪深 300 MA20 vs MA60
    2. 市场宽度：上涨家数/下跌家数
    3. 成交量：5 日均量 vs 20 日均量

    市场状态：
    - 牛市：MA20>MA60 且 市场宽度>1.5
    - 熊市：MA20<MA60 且 市场宽度<0.7
    - 震荡市：其他情况
    """

    def __init__(
        self,
        trend_threshold: float = 0.02,
        breadth_bull: float = 1.5,
        breadth_bear: float = 0.7,
    ):
        """
        初始化市场状态分析器

        Args:
            trend_threshold: 趋势阈值 (MA 乖离率超过此值才认为有趋势)
            breadth_bull: 牛市宽度阈值
            breadth_bear: 熊市宽度阈值
        """
        self.trend_threshold = trend_threshold
        self.breadth_bull = breadth_bull
        self.breadth_bear = breadth_bear

        # 缓存的市场数据
        self._market_data: Optional[Dict] = None

    def analyze(self, index_data: pd.DataFrame, market_breadth: Optional[Dict] = None) -> MarketRegimeSignal:
        """
        全面分析市场状态

        Args:
            index_data: 沪深 300 指数数据，包含 close, volume 列
            market_breadth: 市场宽度数据 {up_count, down_count}

        Returns:
            市场状态信号
        """
        if index_data.empty or len(index_data) < 60:
            return MarketRegimeSignal(
                regime="oscillating",
                trend_score=0,
                breadth_score=0,
                volume_score=0,
                composite_score=0,
                is_oscillating=True,
                suggestion="数据不足，默认震荡市"
            )

        # 1. 趋势分析
        trend_score, ma_ratio = self._analyze_trend(index_data)

        # 2. 市场宽度分析
        breadth_score = self._analyze_breadth(market_breadth)

        # 3. 成交量分析
        volume_score = self._analyze_volume(index_data)

        # 4. 综合得分
        composite_score = 0.5 * trend_score + 0.3 * breadth_score + 0.2 * volume_score

        # 5. 确定市场状态
        regime, is_oscillating = self._determine_regime(trend_score, breadth_score)

        # 6. 操作建议
        suggestion = self._get_suggestion(regime, composite_score)

        logger.info(f"市场状态分析：regime={regime}, trend={trend_score:.2f}, "
                   f"breadth={breadth_score:.2f}, volume={volume_score:.2f}")

        return MarketRegimeSignal(
            regime=regime,
            trend_score=trend_score,
            breadth_score=breadth_score,
            volume_score=volume_score,
            composite_score=composite_score,
            is_oscillating=is_oscillating,
            suggestion=suggestion
        )

    def _analyze_trend(self, index_data: pd.DataFrame) -> Tuple[float, float]:
        """
        分析趋势

        Args:
            index_data: 指数数据

        Returns:
            (趋势得分，MA 比率)
        """
        close = index_data['close']

        # 计算 MA20 和 MA60
        ma20 = close.rolling(20).mean()
        ma60 = close.rolling(60).mean()

        if len(ma20) < 60 or len(ma60) < 60:
            return 0.0, 1.0

        current_ma20 = ma20.iloc[-1]
        current_ma60 = ma60.iloc[-1]
        current_close = close.iloc[-1]

        # MA 比率
        ma_ratio = current_ma20 / current_ma60 if current_ma60 > 0 else 1.0

        # MA20 相对 MA60 的乖离率
        ma_diff = (current_ma20 - current_ma60) / current_ma60

        # 趋势得分：MA20>MA60 为正，乖离率越大得分越高
        if ma_diff > self.trend_threshold:
            trend_score = min(1.0, ma_diff / 0.05)  # 5% 乖离率满分
        elif ma_diff < -self.trend_threshold:
            trend_score = max(-1.0, ma_diff / 0.05)
        else:
            trend_score = ma_diff / 0.05  # 在阈值内线性映射

        return round(trend_score, 3), round(ma_ratio, 4)

    def _analyze_breadth(self, market_breadth: Optional[Dict]) -> float:
        """
        分析市场宽度

        Args:
            market_breadth: {up_count, down_count}

        Returns:
            市场宽度得分 [-1, 1]
        """
        if market_breadth is None:
            return 0.0

        up_count = market_breadth.get('up_count', 0)
        down_count = market_breadth.get('down_count', 0)

        if up_count + down_count == 0:
            return 0.0

        # 涨跌比
        ratio = up_count / down_count if down_count > 0 else 3.0

        # 映射到 [-1, 1]
        if ratio >= self.breadth_bull:
            score = min(1.0, (ratio - 1) / (self.breadth_bull - 1))
        elif ratio <= self.breadth_bear:
            score = max(-1.0, (ratio - 1) / (1 - self.breadth_bear))
        else:
            score = (ratio - 1) / ((self.breadth_bull + self.breadth_bear) / 2 - 1)

        return round(score, 3)

    def _analyze_volume(self, index_data: pd.DataFrame) -> float:
        """
        分析成交量

        Args:
            index_data: 指数数据

        Returns:
            成交量得分 [-1, 1]
        """
        if len(index_data) < 20:
            return 0.0

        volume = index_data['volume']

        # 5 日均量 vs 20 日均量
        ma5_vol = volume.rolling(5).mean()
        ma20_vol = volume.rolling(20).mean()

        if len(ma5_vol) < 20:
            return 0.0

        current_ma5 = ma5_vol.iloc[-1]
        current_ma20 = ma20_vol.iloc[-1]

        # 量比
        volume_ratio = current_ma5 / current_ma20 if current_ma20 > 0 else 1.0

        # 放量得分高，缩量得分低
        # 量比>1.2 得分正，<0.8 得分负
        if volume_ratio > 1.2:
            score = min(1.0, (volume_ratio - 1) / 0.5)
        elif volume_ratio < 0.8:
            score = max(-1.0, (volume_ratio - 1) / 0.3)
        else:
            score = (volume_ratio - 1) / 0.2

        return round(score, 3)

    def _determine_regime(self, trend_score: float, breadth_score: float) -> Tuple[str, bool]:
        """
        确定市场状态

        Returns:
            (市场状态，是否震荡市)
        """
        # 综合判断
        composite = 0.6 * trend_score + 0.4 * breadth_score

        if composite > 0.3 and trend_score > 0.2:
            return "bull", False
        elif composite < -0.3 and trend_score < -0.2:
            return "bear", False
        else:
            return "oscillating", True

    def _get_suggestion(self, regime: str, composite_score: float) -> str:
        """获取操作建议"""
        if regime == "bull":
            if composite_score > 0.7:
                return "强势市场，积极做多，仓位可提升至 80%+"
            else:
                return "牛市格局，保持较高仓位，重点关注强势股"
        elif regime == "bear":
            if composite_score < -0.7:
                return "弱势市场，空仓观望，等待右侧信号"
            else:
                return "熊市格局，降低仓位至 30% 以下，快进快出"
        else:
            if abs(composite_score) < 0.2:
                return "典型震荡市，仓位 50% 左右，高抛低吸"
            else:
                return "震荡偏多/空，仓位 50-60%，等待方向选择"

    def get_position_limit(self, regime: str, composite_score: float) -> float:
        """
        根据市场状态获取仓位上限

        Args:
            regime: 市场状态
            composite_score: 综合得分

        Returns:
            仓位上限 [0, 1]
        """
        if regime == "bull":
            # 牛市：80-100%
            return min(1.0, 0.8 + 0.2 * composite_score)
        elif regime == "bear":
            # 熊市：0-30%
            return max(0.0, 0.3 + 0.3 * composite_score)
        else:
            # 震荡市：40-60%
            base = 0.5
            adjustment = 0.1 * composite_score
            return max(0.4, min(0.6, base + adjustment))

    def get_buy_threshold_adjustment(self, regime: str) -> float:
        """
        根据市场状态调整买入阈值

        Args:
            regime: 市场状态

        Returns:
            买入阈值调整值 (加到基础阈值上)
        """
        if regime == "bull":
            return -0.1  # 牛市降低阈值，更容易买入
        elif regime == "bear":
            return 0.15  # 熊市提高阈值，更谨慎
        else:
            return 0.0  # 震荡市不调整

    def get_weight_adjustment(self, regime: str) -> Dict[str, float]:
        """
        根据市场状态调整信号权重

        Args:
            regime: 市场状态

        Returns:
            权重调整后的配置
        """
        if regime == "bull":
            # 牛市：技术权重↑，新闻权重↓
            return {
                "news": 0.20,
                "technical": 0.35,
                "fund": 0.25,
                "volatility": 0.10,
                "sentiment": 0.10,
            }
        elif regime == "bear":
            # 熊市：资金权重↑ (跟着主力走)
            return {
                "news": 0.15,
                "technical": 0.20,
                "fund": 0.35,
                "volatility": 0.20,
                "sentiment": 0.10,
            }
        else:
            # 震荡市：波动率权重↑
            return {
                "news": 0.25,
                "technical": 0.25,
                "fund": 0.20,
                "volatility": 0.20,
                "sentiment": 0.10,
            }


def get_market_regime(index_code: str = "000300") -> Optional[MarketRegimeSignal]:
    """
    获取当前市场状态（便捷函数）

    Args:
        index_code: 指数代码，默认沪深 300

    Returns:
        市场状态信号
    """
    try:
        import akshare as ak

        # 获取指数数据
        df = ak.stock_zh_index_daily(symbol=index_code)

        if df.empty:
            return None

        # 获取市场宽度（涨跌家数）
        market_breadth = get_market_breadth()

        # 分析市场状态
        analyzer = MarketRegimeAnalyzer()
        signal = analyzer.analyze(df, market_breadth)

        return signal
    except Exception as e:
        logger.error(f"获取市场状态失败：{e}")
        return None


def get_market_breadth() -> Optional[Dict]:
    """
    获取市场宽度数据（涨跌家数）

    Returns:
        {up_count, down_count}
    """
    try:
        import akshare as ak

        # 获取市场涨跌家数
        df = ak.stock_market_pe_lg()

        if df is not None and not df.empty:
            # 这里需要根据实际 API 返回结构调整
            # 暂时返回默认值
            return {"up_count": 2000, "down_count": 2000}

        return {"up_count": 2000, "down_count": 2000}
    except Exception as e:
        logger.error(f"获取市场宽度失败：{e}")
        return {"up_count": 2000, "down_count": 2000}


__all__ = [
    "MarketRegimeAnalyzer",
    "MarketRegimeSignal",
    "get_market_regime",
]
