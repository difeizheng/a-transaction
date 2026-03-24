"""
信号融合引擎 - 多因子信号融合
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class FusionResult:
    """融合结果"""
    stock_code: str
    stock_name: str
    news_score: float       # 新闻得分
    technical_score: float  # 技术面得分
    fund_score: float       # 资金面得分
    volatility_score: float # 波动率得分
    sentiment_score: float  # 情绪得分
    total_score: float      # 综合得分
    signal: str             # 最终信号
    confidence: float       # 置信度
    current_price: float    # 当前价格
    timestamp: datetime


class SignalFusionEngine:
    """
    信号融合引擎

    综合得分 = 新闻分 × 0.30 + 技术分 × 0.25 + 资金分 × 0.20 + 波动率分 × 0.15 + 情绪分 × 0.10

    信号判定:
    - 综合得分 >= 0.7: 强烈买入
    - 综合得分 >= 0.5: 买入
    - 综合得分 >= -0.3: 持有
    - 综合得分 >= -0.6: 卖出
    - 综合得分 < -0.6: 强烈卖出
    """

    def __init__(
        self,
        news_weight: float = 0.30,
        technical_weight: float = 0.25,
        fund_weight: float = 0.20,
        volatility_weight: float = 0.15,
        sentiment_weight: float = 0.10,
    ):
        """
        初始化信号融合引擎

        Args:
            news_weight: 新闻权重
            technical_weight: 技术面权重
            fund_weight: 资金面权重
            volatility_weight: 波动率权重
            sentiment_weight: 情绪权重
        """
        self.news_weight = news_weight
        self.technical_weight = technical_weight
        self.fund_weight = fund_weight
        self.volatility_weight = volatility_weight
        self.sentiment_weight = sentiment_weight

        # 验证权重和为 1
        total = news_weight + technical_weight + fund_weight + volatility_weight + sentiment_weight
        if abs(total - 1.0) > 0.001:
            logger.warning(f"权重和不为 1 ({total})，将自动归一化")
            self._normalize_weights()

    def _normalize_weights(self):
        """归一化权重"""
        total = (
            self.news_weight +
            self.technical_weight +
            self.fund_weight +
            self.volatility_weight +
            self.sentiment_weight
        )
        self.news_weight /= total
        self.technical_weight /= total
        self.fund_weight /= total
        self.volatility_weight /= total
        self.sentiment_weight /= total
        logger.info(
            f"归一化后权重：新闻={self.news_weight:.2f}, "
            f"技术={self.technical_weight:.2f}, "
            f"资金={self.fund_weight:.2f}, "
            f"波动率={self.volatility_weight:.2f}, "
            f"情绪={self.sentiment_weight:.2f}"
        )

    def fuse(
        self,
        stock_code: str,
        stock_name: str,
        news_score: float,
        technical_score: float,
        fund_score: float,
        volatility_score: float,
        sentiment_score: float,
        current_price: float = 0.0,
    ) -> FusionResult:
        """
        融合多因子信号

        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            news_score: 新闻得分 [-1, 1]
            technical_score: 技术面得分 [-1, 1]
            fund_score: 资金面得分 [-1, 1]
            volatility_score: 波动率得分 [-1, 1]
            sentiment_score: 情绪得分 [-1, 1]
            current_price: 当前价格

        Returns:
            融合结果
        """
        # 计算综合得分
        total_score = (
            news_score * self.news_weight +
            technical_score * self.technical_weight +
            fund_score * self.fund_weight +
            volatility_score * self.volatility_weight +
            sentiment_score * self.sentiment_weight
        )

        # 限制在 [-1, 1] 范围
        total_score = max(-1.0, min(1.0, total_score))

        # 确定信号
        signal = self._get_signal(total_score)

        # 计算置信度（各因子一致性）
        confidence = self._calculate_confidence(
            news_score, technical_score, fund_score, volatility_score, sentiment_score
        )

        return FusionResult(
            stock_code=stock_code,
            stock_name=stock_name,
            news_score=news_score,
            technical_score=technical_score,
            fund_score=fund_score,
            volatility_score=volatility_score,
            sentiment_score=sentiment_score,
            total_score=total_score,
            signal=signal,
            confidence=confidence,
            current_price=current_price,
            timestamp=datetime.now(),
        )

    def _get_signal(self, score: float) -> str:
        """
        根据得分确定信号

        Args:
            score: 综合得分

        Returns:
            信号类型
        """
        if score >= 0.7:
            return "strong_buy"    # 强烈买入
        elif score >= 0.5:
            return "buy"           # 买入
        elif score >= -0.3:
            return "hold"          # 持有
        elif score >= -0.6:
            return "sell"          # 卖出
        else:
            return "strong_sell"   # 强烈卖出

    def _calculate_confidence(
        self,
        news_score: float,
        technical_score: float,
        fund_score: float,
        volatility_score: float,
        sentiment_score: float,
    ) -> float:
        """
        计算置信度

        置信度基于各因子信号的一致性
        如果所有因子都指向同一方向，置信度高

        Args:
            news_score: 新闻得分
            technical_score: 技术面得分
            fund_score: 资金面得分
            volatility_score: 波动率得分
            sentiment_score: 情绪得分

        Returns:
            置信度 [0, 1]
        """
        scores = [news_score, technical_score, fund_score, volatility_score, sentiment_score]

        # 计算标准差（标准差越小，一致性越高）
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        std_dev = variance ** 0.5

        # 将标准差转换为置信度
        # 标准差为 0 时置信度为 1，标准差越大置信度越低
        confidence = 1.0 / (1.0 + std_dev)

        return round(confidence, 3)

    def fuse_batch(
        self,
        stock_data: List[Dict],
    ) -> List[FusionResult]:
        """
        批量融合信号

        Args:
            stock_data: 股票数据列表，每项包含：
                - stock_code: 股票代码
                - stock_name: 股票名称
                - news_score: 新闻得分
                - technical_score: 技术面得分
                - fund_score: 资金面得分
                - volatility_score: 波动率得分
                - sentiment_score: 情绪得分
                - current_price: 当前价格

        Returns:
            融合结果列表
        """
        results = []
        for data in stock_data:
            result = self.fuse(
                stock_code=data.get("stock_code", ""),
                stock_name=data.get("stock_name", ""),
                news_score=data.get("news_score", 0),
                technical_score=data.get("technical_score", 0),
                fund_score=data.get("fund_score", 0),
                volatility_score=data.get("volatility_score", 0),
                sentiment_score=data.get("sentiment_score", 0),
                current_price=data.get("current_price", 0),
            )
            results.append(result)

        # 按得分排序
        results.sort(key=lambda x: x.total_score, reverse=True)

        return results

    def get_top_signals(
        self,
        results: List[FusionResult],
        top_n: int = 10,
        signal_type: Optional[str] = None,
    ) -> List[FusionResult]:
        """
        获取前 N 个信号

        Args:
            results: 融合结果列表
            top_n: 数量
            signal_type: 信号类型过滤 (buy/sell/hold 等)

        Returns:
            前 N 个信号
        """
        filtered = results
        if signal_type:
            filtered = [r for r in results if r.signal == signal_type]

        return filtered[:top_n]

    def generate_summary(self, results: List[FusionResult]) -> Dict:
        """
        生成信号摘要

        Args:
            results: 融合结果列表

        Returns:
            摘要统计
        """
        if not results:
            return {
                "total": 0,
                "strong_buy": 0,
                "buy": 0,
                "hold": 0,
                "sell": 0,
                "strong_sell": 0,
                "avg_score": 0,
            }

        signal_counts = {
            "strong_buy": 0,
            "buy": 0,
            "hold": 0,
            "sell": 0,
            "strong_sell": 0,
        }

        for result in results:
            signal_counts[result.signal] = signal_counts.get(result.signal, 0) + 1

        avg_score = sum(r.total_score for r in results) / len(results)

        return {
            "total": len(results),
            "strong_buy": signal_counts["strong_buy"],
            "buy": signal_counts["buy"],
            "hold": signal_counts["hold"],
            "sell": signal_counts["sell"],
            "strong_sell": signal_counts["strong_sell"],
            "avg_score": round(avg_score, 3),
        }


__all__ = ["SignalFusionEngine", "FusionResult"]
