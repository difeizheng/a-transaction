"""
社交媒体情绪数据模块
支持：微博、雪球、东方财富股吧
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import re
import json
import logging

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SocialPost:
    """社交媒体帖子"""
    platform: str           # 平台：weibo/xueqiu/guba
    post_id: str            # 帖子 ID
    title: str              # 标题
    content: str            # 内容
    author: str             # 作者
    publish_time: datetime  # 发布时间
    likes: int = 0          # 点赞数
    comments: int = 0       # 评论数
    shares: int = 0         # 转发数
    sentiment_score: float = 0.0  # 情感得分
    keywords: List[str] = field(default_factory=list)


@dataclass
class SocialSentimentResult:
    """社交媒体情绪分析结果"""
    platform: str
    stock_code: str
    stock_name: str
    overall_sentiment: float    # 综合情绪得分 [-1, 1]
    post_count: int             # 帖子数量
    hot_posts: List[SocialPost] # 热门帖子
    trending_keywords: List[str] # 热门关键词
    sentiment_trend: str        # 情绪趋势：improving/worsening/stable
    discussion_intensity: str   # 讨论热度：high/medium/low
    created_at: datetime = field(default_factory=datetime.now)


class WeiboScraper:
    """
    微博数据抓取器

    注意：实际使用需要配置 Cookie 或使用 API
    """

    def __init__(self, cookie: Optional[str] = None):
        self.cookie = cookie
        self.base_url = "https://weibo.com"
        self.search_url = "https://s.weibo.com/weibo"

    def search_stock_topics(
        self,
        stock_code: str,
        stock_name: str,
        limit: int = 20,
    ) -> List[SocialPost]:
        """
        搜索股票相关微博

        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            limit: 返回数量限制

        Returns:
            微博帖子列表
        """
        # 注意：实际抓取需要实现 HTTP 请求
        # 这里提供框架，实际使用需要配置 Cookie 或使用第三方 API

        logger.info(f"搜索微博话题：{stock_name}({stock_code})")

        # 模拟数据（实际使用时替换为真实抓取）
        posts = self._mock_weibo_posts(stock_code, stock_name, limit)

        return posts

    def _mock_weibo_posts(
        self,
        stock_code: str,
        stock_name: str,
        limit: int,
    ) -> List[SocialPost]:
        """模拟微博数据（实际使用时替换）"""
        import random

        posts = []
        for i in range(limit):
            posts.append(SocialPost(
                platform="weibo",
                post_id=f"wb_{stock_code}_{i}",
                title=f"{stock_name}相关讨论{i}",
                content=f"关于{stock_name}的看法... #{stock_code}#",
                author=f"用户{i}",
                publish_time=datetime.now() - timedelta(hours=i),
                likes=random.randint(0, 1000),
                comments=random.randint(0, 100),
                shares=random.randint(0, 50),
            ))
        return posts


class XueqiuScraper:
    """
    雪球数据抓取器

    雪球是专业的投资社区，内容质量较高
    """

    def __init__(self, cookie: Optional[str] = None):
        self.cookie = cookie
        self.base_url = "https://xueqiu.com"

    def search_stock_topics(
        self,
        stock_code: str,
        stock_name: str,
        limit: int = 20,
    ) -> List[SocialPost]:
        """
        搜索雪球股票讨论

        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            limit: 返回数量限制

        Returns:
            雪球帖子列表
        """
        logger.info(f"搜索雪球话题：{stock_name}({stock_code})")

        # 模拟数据（实际使用时替换为真实抓取）
        posts = self._mock_xueqiu_posts(stock_code, stock_name, limit)

        return posts

    def _mock_xueqiu_posts(
        self,
        stock_code: str,
        stock_name: str,
        limit: int,
    ) -> List[SocialPost]:
        """模拟雪球数据（实际使用时替换）"""
        import random

        posts = []
        for i in range(limit):
            posts.append(SocialPost(
                platform="xueqiu",
                post_id=f"xq_{stock_code}_{i}",
                title=f"{stock_name}投资分析{i}",
                content=f"深入分析{stock_name}的基本面和技术面...",
                author=f"投资者{i}",
                publish_time=datetime.now() - timedelta(hours=i * 2),
                likes=random.randint(0, 500),
                comments=random.randint(0, 200),
                shares=random.randint(0, 100),
            ))
        return posts


class GubaScraper:
    """
    东方财富股吧抓取器

    股吧是最大的散户聚集地，情绪波动大
    """

    def __init__(self):
        self.base_url = "http://guba.eastmoney.com"

    def search_stock_topics(
        self,
        stock_code: str,
        stock_name: str,
        limit: int = 30,
    ) -> List[SocialPost]:
        """
        搜索股吧股票讨论

        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            limit: 返回数量限制

        Returns:
            股吧帖子列表
        """
        logger.info(f"搜索股吧话题：{stock_name}({stock_code})")

        # 模拟数据（实际使用时替换为真实抓取）
        posts = self._mock_guba_posts(stock_code, stock_name, limit)

        return posts

    def _mock_guba_posts(
        self,
        stock_code: str,
        stock_name: str,
        limit: int,
    ) -> List[SocialPost]:
        """模拟股吧数据（实际使用时替换）"""
        import random

        posts = []
        for i in range(limit):
            posts.append(SocialPost(
                platform="guba",
                post_id=f"gb_{stock_code}_{i}",
                title=f"{stock_name}吧{i}",
                content=f"{stock_name}今天怎么走？",
                author=f"股友{i}",
                publish_time=datetime.now() - timedelta(minutes=i * 30),
                likes=random.randint(0, 200),
                comments=random.randint(0, 500),
                shares=random.randint(0, 20),
            ))
        return posts


class SocialMediaSentimentAnalyzer:
    """
    社交媒体情绪分析器

    整合多个平台的数据，计算综合情绪指标
    """

    def __init__(
        self,
        weibo_cookie: Optional[str] = None,
        xueqiu_cookie: Optional[str] = None,
        platforms: List[str] = None,
    ):
        """
        初始化分析器

        Args:
            weibo_cookie: 微博 Cookie
            xueqiu_cookie: 雪球 Cookie
            platforms: 启用的平台列表
        """
        self.weibo_scraper = WeiboScraper(weibo_cookie)
        self.xueqiu_scraper = XueqiuScraper(xueqiu_cookie)
        self.guba_scraper = GubaScraper()

        self.platforms = platforms or ["weibo", "xueqiu", "guba"]

        # 平台权重（雪球内容质量高，权重较高）
        self.platform_weights = {
            "weibo": 0.25,
            "xueqiu": 0.45,
            "guba": 0.30,
        }

    def analyze_stock_sentiment(
        self,
        stock_code: str,
        stock_name: str,
        limit_per_platform: int = 20,
    ) -> SocialSentimentResult:
        """
        分析股票社交媒体情绪

        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            limit_per_platform: 每个平台抓取数量

        Returns:
            情绪分析结果
        """
        all_posts = []

        # 抓取各平台数据
        if "weibo" in self.platforms:
            weibo_posts = self.weibo_scraper.search_stock_topics(
                stock_code, stock_name, limit_per_platform
            )
            all_posts.extend(weibo_posts)

        if "xueqiu" in self.platforms:
            xueqiu_posts = self.xueqiu_scraper.search_stock_topics(
                stock_code, stock_name, limit_per_platform
            )
            all_posts.extend(xueqiu_posts)

        if "guba" in self.platforms:
            guba_posts = self.guba_scraper.search_stock_topics(
                stock_code, stock_name, limit_per_platform
            )
            all_posts.extend(guba_posts)

        # 分析情绪
        sentiment_scores = self._analyze_posts_sentiment(all_posts)

        # 计算综合情绪
        overall_sentiment = self._calculate_overall_sentiment(
            all_posts, sentiment_scores
        )

        # 提取热门关键词
        trending_keywords = self._extract_trending_keywords(all_posts)

        # 判断情绪趋势
        sentiment_trend = self._determine_sentiment_trend(all_posts)

        # 判断讨论热度
        discussion_intensity = self._determine_discussion_intensity(all_posts)

        # 筛选热门帖子（按互动量）
        hot_posts = sorted(
            all_posts,
            key=lambda p: p.likes + p.comments * 2 + p.shares * 3,
            reverse=True
        )[:10]

        return SocialSentimentResult(
            platform="all",
            stock_code=stock_code,
            stock_name=stock_name,
            overall_sentiment=overall_sentiment,
            post_count=len(all_posts),
            hot_posts=hot_posts,
            trending_keywords=trending_keywords[:10],
            sentiment_trend=sentiment_trend,
            discussion_intensity=discussion_intensity,
        )

    def _analyze_posts_sentiment(
        self,
        posts: List[SocialPost],
    ) -> Dict[str, List[float]]:
        """分析帖子情感"""
        from src.analyzers.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer()
        scores_by_platform = {}

        for post in posts:
            # 分析情感
            result = analyzer.analyze(
                text=post.content,
                title=post.title,
            )
            post.sentiment_score = result.score

            # 按平台分组
            if post.platform not in scores_by_platform:
                scores_by_platform[post.platform] = []
            scores_by_platform[post.platform].append(result.score)

        return scores_by_platform

    def _calculate_overall_sentiment(
        self,
        posts: List[SocialPost],
        scores_by_platform: Dict[str, List[float]],
    ) -> float:
        """计算综合情绪得分"""
        if not posts:
            return 0.0

        weighted_sum = 0.0
        total_weight = 0.0

        for platform, scores in scores_by_platform.items():
            if scores:
                platform_avg = sum(scores) / len(scores)
                weight = self.platform_weights.get(platform, 0.2)

                # 互动量加权
                platform_posts = [p for p in posts if p.platform == platform]
                total_engagement = sum(
                    p.likes + p.comments + p.shares for p in platform_posts
                )
                engagement_weight = min(2.0, 1 + total_engagement / 10000)

                weighted_sum += platform_avg * weight * engagement_weight
                total_weight += weight * engagement_weight

        if total_weight > 0:
            return weighted_sum / total_weight
        return 0.0

    def _extract_trending_keywords(
        self,
        posts: List[SocialPost],
    ) -> List[str]:
        """提取热门关键词"""
        import jieba

        # 合并所有内容
        all_text = " ".join([f"{p.title} {p.content}" for p in posts])

        # 分词
        words = jieba.lcut(all_text)

        # 过滤停用词
        stopwords = {
            "的", "了", "在", "是", "我", "有", "和", "就", "不", "人",
            "都", "一", "一个", "上", "也", "很", "到", "说", "要",
            "去", "你", "这", "那", "他", "她", "它", "们", "这个",
            "那个", "什么", "怎么", "可以", "没有", "看", "着", "过",
            "股票", "今天", "明天", "走势", "分析", "讨论"
        }

        # 统计词频
        word_freq = {}
        for word in words:
            if len(word) >= 2 and word not in stopwords:
                word_freq[word] = word_freq.get(word, 0) + 1

        # 返回 Top 关键词
        sorted_words = sorted(
            word_freq.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return [w[0] for w in sorted_words[:20]]

    def _determine_sentiment_trend(
        self,
        posts: List[SocialPost],
    ) -> str:
        """判断情绪趋势"""
        if not posts:
            return "stable"

        # 按时间排序
        sorted_posts = sorted(posts, key=lambda p: p.publish_time)

        # 比较近期和早期情绪
        mid = len(sorted_posts) // 2
        early_posts = sorted_posts[:mid]
        recent_posts = sorted_posts[mid:]

        early_sentiment = sum(p.sentiment_score for p in early_posts) / len(early_posts)
        recent_sentiment = sum(p.sentiment_score for p in recent_posts) / len(recent_posts)

        diff = recent_sentiment - early_sentiment

        if diff > 0.15:
            return "improving"
        elif diff < -0.15:
            return "worsening"
        else:
            return "stable"

    def _determine_discussion_intensity(
        self,
        posts: List[SocialPost],
    ) -> str:
        """判断讨论热度"""
        if not posts:
            return "low"

        # 统计总互动量
        total_engagement = sum(
            p.likes + p.comments + p.shares for p in posts
        )

        # 统计时间范围（小时）
        if posts:
            time_range = (datetime.now() - posts[-1].publish_time).total_seconds() / 3600
            time_range = max(1, time_range)
            engagement_per_hour = total_engagement / time_range
        else:
            engagement_per_hour = 0

        if engagement_per_hour > 100:
            return "high"
        elif engagement_per_hour > 20:
            return "medium"
        else:
            return "low"


def run_social_sentiment_demo():
    """社交媒体情绪分析演示"""
    print("=" * 60)
    print("社交媒体情绪分析演示")
    print("=" * 60)

    # 测试股票
    stock_code = "000001"
    stock_name = "平安银行"

    print(f"\n分析股票：{stock_name}({stock_code})")

    # 创建分析器
    analyzer = SocialMediaSentimentAnalyzer(
        platforms=["weibo", "xueqiu", "guba"]
    )

    # 分析情绪
    result = analyzer.analyze_stock_sentiment(
        stock_code, stock_name, limit_per_platform=10
    )

    # 输出结果
    print("\n" + "=" * 60)
    print("情绪分析结果")
    print("=" * 60)
    print(f"帖子总数：{result.post_count}")
    print(f"综合情绪：{result.overall_sentiment:.4f}")
    print(f"情绪趋势：{result.sentiment_trend}")
    print(f"讨论热度：{result.discussion_intensity}")
    print(f"\n热门关键词：{result.trending_keywords[:5]}")

    print("\n热门帖子:")
    for i, post in enumerate(result.hot_posts[:5], 1):
        print(f"  {i}. [{post.platform}] {post.title}")
        print(f"     互动：{post.likes + post.comments + post.shares}")

    return result


if __name__ == "__main__":
    run_social_sentiment_demo()
