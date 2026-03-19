"""
情感分析模块 - NLP 中文情感分析
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import re

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SentimentResult:
    """情感分析结果"""
    score: float  # [-1, 1], 正数为利好，负数为利空
    label: str    # positive/negative/neutral
    confidence: float  # 置信度 [0, 1]
    keywords: List[str]  # 关键词


class SentimentAnalyzer:
    """
    情感分析器

    支持：
    - SnowNLP 情感分析
    - 基于词典的规则分析
    - 关键词提取
    """

    # 利好关键词
    POSITIVE_KEYWORDS = [
        "利好", "增长", "上涨", "突破", "重组", "并购", "业绩预增", "扭亏为盈",
        "分红", "回购", "增持", "中标", "签约", "合作", "创新", "专利",
        "突破", "爆发", "强势", "新高", "推荐", "买入", "增持", "看好",
        "政策扶持", "税收优惠", "补贴", "奖励", "订单", "大单", "放量",
        "主力流入", "北向流入", "资金净流入", "供不应求", "涨价", "提价",
        "业绩亮眼", "高速增长", "超预期", "重大利好", "战略投资", "引进战投",
        "股权激励", "员工持股", "管理层增持", "优质", "龙头", "领军",
        "独家", "垄断", "壁垒", "护城河", "领先", "优势", "潜力",
    ]

    # 利空关键词
    NEGATIVE_KEYWORDS = [
        "利空", "下跌", "暴跌", "跳水", "亏损", "业绩下滑", "预亏", "预警",
        "减持", "套现", "抛售", "减持", "解禁", "退市", "ST", "*ST",
        "立案调查", "处罚", "罚款", "诉讼", "仲裁", "违约", "破产",
        "重组失败", "并购失败", "项目失败", "亏损", "资不抵债", "债务危机",
        "资金链断裂", "流动性危机", "质押", "冻结", "强平", "爆仓",
        "主力流出", "北向流出", "资金净流出", "缩量", "破位", "下行",
        "看跌", "卖出", "减持", "下调", "评级下调", "目标价下调",
        "重大利空", "黑天鹅", "暴雷", "踩雷", "商誉减值", "资产减值",
        "股东减持", "高管离职", "核心技术流失", "市场份额下滑", "竞争加剧",
    ]

    # 程度副词
    DEGREE_ADVERBS = {
        "极其": 2.0, "非常": 1.8, "特别": 1.8, "十分": 1.8, "极为": 2.0,
        "很": 1.5, "较为": 1.3, "比较": 1.3, "相当": 1.5,
        "略": 0.8, "略微": 0.8, "小幅": 0.8, "小幅": 0.8,
        "继续": 1.1, "持续": 1.2, "进一步": 1.3,
    }

    def __init__(self, model: str = "snownlp"):
        """
        初始化情感分析器

        Args:
            model: 使用的模型 (snownlp / rule)
        """
        self.model_type = model
        self._snownlp = None

        if model == "snownlp":
            self._init_snownlp()

    def _init_snownlp(self):
        """初始化 SnowNLP"""
        try:
            from snownlp import SnowNLP
            self._snownlp = SnowNLP
            logger.info("SnowNLP 初始化成功")
        except ImportError:
            logger.warning("SnowNLP 未安装，将使用规则分析")
            self.model_type = "rule"
        except Exception as e:
            logger.error(f"SnowNLP 初始化失败：{e}")
            self.model_type = "rule"

    def analyze(self, text: str, title: str = "") -> SentimentResult:
        """
        分析文本情感

        Args:
            text: 文本内容
            title: 标题（可选）

        Returns:
            情感分析结果
        """
        if not text and not title:
            return SentimentResult(
                score=0.0,
                label="neutral",
                confidence=0.0,
                keywords=[]
            )

        # 合并标题和正文
        full_text = f"{title} {text}" if title and text else (title or text)

        # 根据模型类型选择分析方法
        if self.model_type == "snownlp" and self._snownlp:
            return self._analyze_with_snownlp(full_text)
        else:
            return self._analyze_with_rules(full_text)

    def _analyze_with_snownlp(self, text: str) -> SentimentResult:
        """使用 SnowNLP 分析"""
        try:
            s = self._snownlp(text)

            # SnowNLP 返回 [0, 1]，转换为 [-1, 1]
            raw_score = s.sentiments
            score = (raw_score - 0.5) * 2  # 转换为 [-1, 1]

            # 结合关键词调整
            keyword_score, keywords = self._analyze_keywords(text)

            # 加权平均
            final_score = score * 0.7 + keyword_score * 0.3

            # 确定标签
            if final_score >= 0.2:
                label = "positive"
            elif final_score <= -0.2:
                label = "negative"
            else:
                label = "neutral"

            # 计算置信度
            confidence = min(abs(final_score) + 0.5, 1.0)

            return SentimentResult(
                score=final_score,
                label=label,
                confidence=confidence,
                keywords=keywords[:5]  # 返回前 5 个关键词
            )

        except Exception as e:
            logger.error(f"SnowNLP 分析失败：{e}")
            return self._analyze_with_rules(text)

    def _analyze_with_rules(self, text: str) -> SentimentResult:
        """使用规则分析"""
        score, keywords = self._analyze_keywords(text)

        # 确定标签
        if score >= 0.2:
            label = "positive"
        elif score <= -0.2:
            label = "negative"
        else:
            label = "neutral"

        # 计算置信度
        confidence = min(abs(score) + 0.3, 1.0) if keywords else 0.3

        return SentimentResult(
            score=score,
            label=label,
            confidence=confidence,
            keywords=keywords[:5]
        )

    def _analyze_keywords(self, text: str) -> Tuple[float, List[str]]:
        """
        基于关键词分析情感

        Returns:
            (情感得分，关键词列表)
        """
        if not text:
            return 0.0, []

        text_lower = text.lower()

        positive_count = 0
        negative_count = 0
        positive_keywords = []
        negative_keywords = []

        # 查找利好关键词
        for kw in self.POSITIVE_KEYWORDS:
            if kw in text_lower:
                positive_count += 1
                positive_keywords.append(kw)

        # 查找利空关键词
        for kw in self.NEGATIVE_KEYWORDS:
            if kw in text_lower:
                negative_count += 1
                negative_keywords.append(kw)

        # 应用程度副词
        for adverb, weight in self.DEGREE_ADVERBS.items():
            if adverb in text_lower:
                # 检查副词后是否跟着情感词
                for kw in self.POSITIVE_KEYWORDS:
                    if adverb + kw in text_lower or f"{adverb}{kw[:2]}" in text_lower:
                        positive_count += weight - 1
                for kw in self.NEGATIVE_KEYWORDS:
                    if adverb + kw in text_lower or f"{adverb}{kw[:2]}" in text_lower:
                        negative_count += weight - 1

        # 计算得分
        total = positive_count + negative_count
        if total == 0:
            return 0.0, []

        # 归一化到 [-1, 1]
        score = (positive_count - negative_count) / max(total, 1)

        # 限制分数范围
        score = max(-1.0, min(1.0, score))

        # 合并关键词
        all_keywords = positive_keywords + negative_keywords

        return score, all_keywords

    def analyze_batch(self, texts: List[str]) -> List[SentimentResult]:
        """
        批量分析

        Args:
            texts: 文本列表

        Returns:
            情感分析结果列表
        """
        return [self.analyze(text) for text in texts]

    def news_sentiment(self, news_list: List[Dict]) -> Dict[str, float]:
        """
        分析新闻列表的整体情感

        Args:
            news_list: 新闻列表，每条新闻包含 title 和 content

        Returns:
            {新闻 ID: 情感得分}
        """
        results = {}
        for i, news in enumerate(news_list):
            title = news.get("title", "")
            content = news.get("content", "")
            result = self.analyze(title, content)
            results[i] = result.score
        return results

    def extract_stock_keywords(self, text: str) -> List[str]:
        """
        提取与股票相关的关键词

        Args:
            text: 文本

        Returns:
            关键词列表
        """
        # 使用 jieba 分词（如果可用）
        try:
            import jieba
            words = jieba.lcut(text)

            # 过滤停用词和常见词
            stopwords = {"的", "了", "在", "是", "我", "有", "和", "就", "不", "人",
                         "都", "一", "一个", "上", "也", "很", "到", "说", "要",
                         "去", "你", "这", "那", "他", "她", "它", "们", "这个",
                         "那个", "什么", "怎么", "可以", "没有", "看", "着", "过"}

            keywords = [w for w in words if len(w) >= 2 and w not in stopwords]
            return keywords[:10]

        except ImportError:
            # 简单提取
            return []


__all__ = ["SentimentAnalyzer", "SentimentResult"]
