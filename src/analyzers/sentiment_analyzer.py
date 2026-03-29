"""
情感分析模块 - NLP 中文情感分析
支持：情感分析、事件类型识别、影响程度分级、时效性加权、来源可信度
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
    event_type: str = ""  # 事件类型
    impact_level: str = ""  # 影响程度 (high/medium/low)
    time_weight: float = 1.0  # 时效性权重
    source_credibility: float = 1.0  # 来源可信度


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

    # 事件类型分类
    EVENT_TYPES = {
        # 业绩类
        "earnings": ["业绩", "财报", "年报", "季报", "营收", "净利润", "利润", "盈利", "亏损", "每股收益"],
        # 资本运作类
        "capital_operation": ["重组", "并购", "收购", "兼并", "定增", "配股", "发债", "IPO", "上市", "退市"],
        # 管理层类
        "management": ["高管", "董事", "监事", "辞职", "离职", "变更", "调查", "处罚", "诉讼", "仲裁"],
        # 业务类
        "business": ["订单", "中标", "签约", "合作", "合同", "大单", "项目", "投产", "扩产", "产能"],
        # 政策类
        "policy": ["政策", "扶持", "补贴", "税收", "优惠", "监管", "限制", "牌照", "许可", "审批"],
        # 股权类
        "equity": ["增持", "减持", "解禁", "质押", "冻结", "强平", "举牌", "回购", "分红", "送转"],
        # 产品技术类
        "product_tech": ["产品", "技术", "专利", "研发", "创新", "突破", "发布", "上市", "认证", "注册"],
        # 行业类
        "industry": ["行业", "板块", "概念", "题材", "周期", "景气", "需求", "供给", "价格", "涨价"],
        # 资金类
        "fund_flow": ["资金", "流入", "流出", "主力", "北向", "南向", "融资", "融券", "龙虎榜"],
        # 市场传闻类
        "rumor": ["传闻", "消息", "爆料", "疑似", "或", "可能", "据悉", "传言"],
    }

    # 影响程度关键词
    IMPACT_LEVELS = {
        "high": ["重大", "重要", "关键", "核心", "战略", "首次", "突破", "历史", "创纪录", "特别", "极其", "非常",
                 "重组", "退市", "处罚", "立案调查", "破产", "违约", "爆雷", "黑天鹅", "重磅", "重磅利好", "重磅利空"],
        "medium": ["一般", "普通", "常规", "正常", "继续", "持续", "进一步", "稳步", "平稳", "正常", "符合预期"],
        "low": ["轻微", "小幅", "略有", "微", "小幅", "窄幅", "震荡", "整理", "小幅波动"],
    }

    # 来源可信度评级
    SOURCE_CREDIBILITY = {
        # 官方来源 (最高可信度)
        "official": {
            "sources": ["证监会", "交易所", "公司公告", "巨潮资讯", "官方披露", "法定披露"],
            "weight": 1.0
        },
        # 权威媒体 (高可信度)
        "authoritative_media": {
            "sources": ["新华社", "人民日报", "央视", "财新", "财经", "证券时报", "中国证券报", "上海证券报",
                       "证券日报", "经济参考报", " Bloomberg", "Reuters", "华尔街见闻"],
            "weight": 0.9
        },
        # 主流财经媒体 (中高可信度)
        "mainstream_media": {
            "sources": ["东方财富", "同花顺", "新浪财经", "腾讯自选股", "网易财经", "搜狐财经", "财联社",
                       "格隆汇", "智通财经", "富途牛牛", "老虎证券"],
            "weight": 0.75
        },
        # 一般媒体/自媒体 (中等可信度)
        "general_media": {
            "sources": ["微博", "公众号", "雪球", "知乎", "头条", "百度", "搜狐", "网易"],
            "weight": 0.5
        },
        # 传闻/小道消息 (低可信度)
        "rumor": {
            "sources": ["传闻", "传言", "爆料", "小道消息", "网友", "匿名", "据悉", "或", "可能"],
            "weight": 0.3
        },
    }

    def __init__(self, model: str = "snownlp", default_source: str = "mainstream_media"):
        """
        初始化情感分析器

        Args:
            model: 使用的模型 (snownlp / rule)
            default_source: 默认来源类型
        """
        self.model_type = model
        self._snownlp = None
        self.default_source_type = default_source

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

    def analyze(
        self,
        text: str,
        title: str = "",
        source: str = "",
        publish_time: Optional[datetime] = None,
    ) -> SentimentResult:
        """
        分析文本情感

        Args:
            text: 文本内容
            title: 标题（可选）
            source: 来源（可选）
            publish_time: 发布时间（可选）

        Returns:
            情感分析结果
        """
        if not text and not title:
            return SentimentResult(
                score=0.0,
                label="neutral",
                confidence=0.0,
                keywords=[],
                event_type="",
                impact_level="",
                time_weight=1.0,
                source_credibility=1.0,
            )

        # 合并标题和正文
        full_text = f"{title} {text}" if title and text else (title or text)

        # 根据模型类型选择分析方法
        if self.model_type == "snownlp" and self._snownlp:
            base_result = self._analyze_with_snownlp(full_text)
        else:
            base_result = self._analyze_with_rules(full_text)

        # 事件类型识别
        event_type = self._identify_event_type(full_text)

        # 影响程度分级
        impact_level = self._assess_impact_level(full_text)

        # 时效性加权
        time_weight = self._calculate_time_weight(publish_time)

        # 来源可信度
        source_credibility = self._assess_source_credibility(source)

        # 综合调整分数
        final_score = base_result.score * time_weight * source_credibility

        return SentimentResult(
            score=final_score,
            label=base_result.label,
            confidence=base_result.confidence,
            keywords=base_result.keywords,
            event_type=event_type,
            impact_level=impact_level,
            time_weight=time_weight,
            source_credibility=source_credibility,
        )

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

    def _identify_event_type(self, text: str) -> str:
        """
        识别事件类型

        Args:
            text: 文本内容

        Returns:
            事件类型（英文）
        """
        if not text:
            return ""

        text_lower = text.lower()
        event_scores = {}

        # 计算每个事件类型的匹配度
        for event_type, keywords in self.EVENT_TYPES.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                event_scores[event_type] = score

        if not event_scores:
            return "general"  # 一般事件

        # 返回匹配度最高的事件类型
        return max(event_scores, key=event_scores.get)

    def _assess_impact_level(self, text: str) -> str:
        """
        评估事件影响程度

        Args:
            text: 文本内容

        Returns:
            影响程度 (high/medium/low)
        """
        if not text:
            return "medium"

        text_lower = text.lower()

        # 检查高影响关键词
        high_impact_count = sum(1 for kw in self.IMPACT_LEVELS["high"] if kw in text_lower)
        if high_impact_count >= 2:
            return "high"

        # 检查低影响关键词
        low_impact_count = sum(1 for kw in self.IMPACT_LEVELS["low"] if kw in text_lower)
        if low_impact_count >= 2:
            return "low"

        # 检查中影响关键词
        medium_impact_count = sum(1 for kw in self.IMPACT_LEVELS["medium"] if kw in text_lower)
        if medium_impact_count >= 1:
            return "medium"

        # 默认根据情感强度判断
        if high_impact_count >= 1:
            return "high"
        if low_impact_count >= 1:
            return "low"

        return "medium"  # 默认中等影响

    def _calculate_time_weight(self, publish_time: Optional[datetime]) -> float:
        """
        计算时效性权重

        Args:
            publish_time: 发布时间

        Returns:
            权重系数 [0.5, 1.0]
        """
        if not publish_time:
            return 1.0  # 没有时间信息，默认最大权重

        now = datetime.now()
        try:
            time_diff = now - publish_time
            hours = time_diff.total_seconds() / 3600

            # 1 小时内：1.0
            # 1-6 小时：0.95
            # 6-24 小时：0.85
            # 24-72 小时：0.7
            # 超过 72 小时：0.5

            if hours <= 1:
                return 1.0
            elif hours <= 6:
                return 0.95
            elif hours <= 24:
                return 0.85
            elif hours <= 72:
                return 0.7
            else:
                return 0.5

        except Exception as e:
            logger.warning(f"计算时效性权重失败：{e}")
            return 1.0

    def _assess_source_credibility(self, source: str) -> float:
        """
        评估来源可信度

        Args:
            source: 来源名称

        Returns:
            可信度系数 [0.3, 1.0]
        """
        if not source:
            # 使用默认来源
            return self.SOURCE_CREDIBILITY.get(self.default_source_type, {}).get("weight", 0.75)

        source_lower = source.lower()

        # 检查来源属于哪个类别
        for category, info in self.SOURCE_CREDIBILITY.items():
            for src in info["sources"]:
                if src.lower() in source_lower:
                    return info["weight"]

        # 未知来源，默认中等可信度
        return 0.6

    def analyze_with_details(
        self,
        news_item: Dict[str, any],
    ) -> SentimentResult:
        """
        分析新闻条目的完整情感（包含所有元数据）

        Args:
            news_item: 新闻条目，包含 title, content, source, publish_time 等

        Returns:
            情感分析结果
        """
        title = news_item.get("title", "")
        content = news_item.get("content", "")
        source = news_item.get("source", "")
        publish_time = news_item.get("publish_time")

        # 合并标题和正文进行情感分析
        full_text = f"{title} {content}" if title and content else (title or content)

        # 基础情感分析
        if self.model_type == "snownlp" and self._snownlp:
            base_result = self._analyze_with_snownlp(full_text)
        else:
            base_result = self._analyze_with_rules(full_text)

        # 事件类型识别
        event_type = self._identify_event_type(full_text)

        # 影响程度分级
        impact_level = self._assess_impact_level(full_text)

        # 时效性加权
        time_weight = self._calculate_time_weight(publish_time)

        # 来源可信度
        source_credibility = self._assess_source_credibility(source)

        # 综合调整分数
        final_score = base_result.score * time_weight * source_credibility

        # 影响程度调整：高影响事件放大分数
        impact_multiplier = {"high": 1.2, "medium": 1.0, "low": 0.8}
        final_score *= impact_multiplier.get(impact_level, 1.0)

        # 限制分数在 [-1, 1] 范围内
        final_score = max(-1.0, min(1.0, final_score))

        return SentimentResult(
            score=final_score,
            label=base_result.label,
            confidence=base_result.confidence,
            keywords=base_result.keywords,
            event_type=event_type,
            impact_level=impact_level,
            time_weight=time_weight,
            source_credibility=source_credibility,
        )


__all__ = ["SentimentAnalyzer", "SentimentResult"]
