"""
新闻采集器模块 - 从多个源采集财经新闻
"""
import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from abc import ABC, abstractmethod
import re
import json

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class NewsItem:
    """新闻数据类"""
    title: str
    content: str
    source: str
    url: str
    publish_time: datetime
    stock_code: Optional[str] = None
    stock_name: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "url": self.url,
            "publish_time": self.publish_time,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
        }


class NewsCollector(ABC):
    """新闻采集器基类"""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

    @abstractmethod
    def collect(self, stock_code: Optional[str] = None, limit: int = 20) -> List[NewsItem]:
        """
        采集新闻

        Args:
            stock_code: 股票代码，None 表示采集市场新闻
            limit: 采集数量上限

        Returns:
            新闻列表
        """
        pass

    def _clean_text(self, text: str) -> str:
        """清洗文本"""
        if not text:
            return ""
        # 去除多余空白
        text = re.sub(r"\s+", " ", text.strip())
        return text


class EastmoneyCollector(NewsCollector):
    """东方财富网新闻采集器"""

    def __init__(self, timeout: int = 10):
        super().__init__(timeout)
        self.base_url = "https://github.com"  # 使用通用 User-Agent

    def collect(self, stock_code: Optional[str] = None, limit: int = 20) -> List[NewsItem]:
        """
        采集东方财富新闻

        Args:
            stock_code: 股票代码
            limit: 采集数量

        Returns:
            新闻列表
        """
        news_list = []

        try:
            if stock_code:
                # 个股新闻
                url = f"https://newsapi.eastmoney.com/ksggb/{stock_code}"
                params = {
                    "pageIndex": 1,
                    "pageSize": limit,
                }
            else:
                # 市场要闻
                url = "https://api.eastmoney.com/news/list"
                params = {
                    "type": "cj",
                    "pageNo": 1,
                    "pageSize": limit,
                }

            response = self.session.get(url, params=params, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                # 根据实际 API 结构调整解析逻辑
                articles = data.get("data", []) or data.get("articles", [])

                for article in articles[:limit]:
                    news = NewsItem(
                        title=self._clean_text(article.get("Title", "") or article.get("title", "")),
                        content="",
                        source="东方财富",
                        url=article.get("Url", "") or article.get("url", ""),
                        publish_time=self._parse_time(article.get("PublishTime", "") or article.get("publish_time", "")),
                        stock_code=stock_code,
                    )
                    news_list.append(news)
            else:
                logger.warning(f"东方财富 API 返回状态码：{response.status_code}")

        except requests.RequestException as e:
            logger.error(f"采集东方财富新闻失败：{e}")
        except Exception as e:
            logger.error(f"解析东方财富新闻失败：{e}")

        return news_list

    def collect_web(self, stock_code: Optional[str] = None, limit: int = 20) -> List[NewsItem]:
        """
        通过网页采集东方财富新闻（备用方案）

        Args:
            stock_code: 股票代码
            limit: 采集数量

        Returns:
            新闻列表
        """
        news_list = []

        try:
            if stock_code:
                # 个股新闻页面
                url = f"https://emweb.eastmoney.com/PC_HSF10/NewsIndex/{stock_code}"
            else:
                url = "https://news.eastmoney.com/"

            response = self.session.get(url, timeout=self.timeout)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "lxml")

                # 查找新闻标题（选择器根据实际页面结构调整）
                news_items = soup.select(".news-item, .news-list li")[:limit]

                for item in news_items:
                    title_elem = item.select_one(".title, .news-title")
                    time_elem = item.select_one(".time, .news-time")
                    link_elem = item.select_one("a")

                    if title_elem and link_elem:
                        news = NewsItem(
                            title=self._clean_text(title_elem.get_text()),
                            content="",
                            source="东方财富",
                            url=link_elem.get("href", ""),
                            publish_time=self._parse_time(time_elem.get_text() if time_elem else ""),
                            stock_code=stock_code,
                        )
                        news_list.append(news)

        except Exception as e:
            logger.error(f"网页采集东方财富新闻失败：{e}")

        return news_list

    def _parse_time(self, time_str: str) -> datetime:
        """解析时间字符串"""
        if not time_str:
            return datetime.now()

        # 尝试多种格式
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%m-%d %H:%M",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue

        # 处理相对时间
        if "分钟" in time_str:
            match = re.search(r"(\d+) 分钟", time_str)
            if match:
                minutes = int(match.group(1))
                return datetime.now() - timedelta(minutes=minutes)
        elif "小时" in time_str:
            match = re.search(r"(\d+) 小时", time_str)
            if match:
                hours = int(match.group(1))
                return datetime.now() - timedelta(hours=hours)
        elif "今天" in time_str:
            time_part = time_str.replace("今天", "").strip()
            try:
                return datetime.now().replace(
                    hour=int(time_part.split(":")[0]) if ":" in time_part else 0,
                    minute=int(time_part.split(":")[1]) if ":" in time_part and len(time_part.split(":")) > 1 else 0,
                )
            except (ValueError, IndexError):
                pass

        return datetime.now()


class SinaCollector(NewsCollector):
    """新浪财经新闻采集器"""

    def collect(self, stock_code: Optional[str] = None, limit: int = 20) -> List[NewsItem]:
        """采集新浪新闻"""
        news_list = []

        try:
            if stock_code:
                # 个股新闻
                url = f"https://news.sina.com.cn/stock/{stock_code}"
            else:
                # 财经新闻
                url = "https://feed.mix.sina.com.cn/api/roll/get?pageid=153"

            response = self.session.get(url, timeout=self.timeout)
            if response.status_code == 200:
                # 解析 HTML 或 JSON
                soup = BeautifulSoup(response.text, "lxml")

                # 查找新闻列表
                news_items = soup.select(".feed_list li, .news-item")[:limit]

                for item in news_items:
                    title_elem = item.select_one("a")
                    time_elem = item.select_one(".date, .time")

                    if title_elem:
                        news = NewsItem(
                            title=self._clean_text(title_elem.get("title", "") or title_elem.get_text()),
                            content="",
                            source="新浪财经",
                            url=title_elem.get("href", ""),
                            publish_time=self._parse_time(time_elem.get_text() if time_elem else ""),
                            stock_code=stock_code,
                        )
                        news_list.append(news)

        except Exception as e:
            logger.error(f"采集新浪新闻失败：{e}")

        return news_list

    def _parse_time(self, time_str: str) -> datetime:
        """解析时间"""
        return EastmoneyCollector()._parse_time(time_str)


class AnnouncementCollector(NewsCollector):
    """公告采集器 - 巨潮资讯网"""

    def collect(self, stock_code: Optional[str] = None, limit: int = 20) -> List[NewsItem]:
        """采集公告"""
        news_list = []

        if not stock_code:
            return news_list

        try:
            # 巨潮资讯网 API
            url = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
            }

            data = {
                "stock": stock_code,
                "searchkey": "",
                "plate": "",
                "period": "",
                "category": "",
                "sortName": "time",
                "sortType": "desc",
                "pageNum": 1,
                "pageSize": limit,
            }

            response = self.session.post(url, headers=headers, data=data, timeout=self.timeout)
            if response.status_code == 200:
                result = response.json()
                announcements = result.get("announcements", [])

                for ann in announcements[:limit]:
                    news = NewsItem(
                        title=self._clean_text(ann.get("title", "")),
                        content="",
                        source="巨潮资讯",
                        url=f"http://www.cninfo.com.cn/new/disclosure/detail?stockCode={stock_code}&announcementId={ann.get('id', '')}",
                        publish_time=datetime.fromtimestamp(ann.get("announcementTime", 0) / 1000) if ann.get("announcementTime") else datetime.now(),
                        stock_code=stock_code,
                    )
                    news_list.append(news)

        except Exception as e:
            logger.error(f"采集公告失败：{e}")

        return news_list


class CailianCollector(NewsCollector):
    """财联社电报采集器"""

    def collect(self, stock_code: Optional[str] = None, limit: int = 20) -> List[NewsItem]:
        """采集财联社电报"""
        news_list = []

        try:
            url = "https://www.cls.cn/api/roll/list"
            params = {
                "app": "cailianpress",
                "category_id": "1",
                "last_time": int(datetime.now().timestamp()),
                "os": "web",
                "refresh_type": "1",
                "sv": "7.7.6",
            }

            response = self.session.get(url, params=params, timeout=self.timeout)
            if response.status_code == 200:
                result = response.json()
                items = result.get("data", {}).get("roll_data", [])

                for item in items[:limit]:
                    content = self._clean_text(item.get("content", ""))
                    # 从内容中提取股票代码（如果有）
                    stock_match = re.search(r"([Aa] 股|\(?\d{6}\)?|SZ\d{6}|SH\d{6})", content)

                    news = NewsItem(
                        title=content[:50] + "..." if len(content) > 50 else content,
                        content=content,
                        source="财联社",
                        url=f"https://www.cls.cn/detail/{item.get('id', '')}",
                        publish_time=datetime.fromtimestamp(item.get("ctime", 0)) if item.get("ctime") else datetime.now(),
                        stock_code=stock_code,
                    )
                    news_list.append(news)

        except Exception as e:
            logger.error(f"采集财联社电报失败：{e}")

        return news_list


class CompositeNewsCollector:
    """复合新闻采集器 - 从多个源采集"""

    def __init__(self):
        self.collectors = {
            "eastmoney": EastmoneyCollector(),
            "sina": SinaCollector(),
            "announcement": AnnouncementCollector(),
            "cailian": CailianCollector(),
        }

    def collect(
        self,
        stock_code: Optional[str] = None,
        limit: int = 20,
        sources: Optional[List[str]] = None,
    ) -> List[NewsItem]:
        """
        从多个源采集新闻

        Args:
            stock_code: 股票代码
            limit: 每个源采集数量
            sources: 指定源列表，None 表示使用所有源

        Returns:
            合并后的新闻列表（去重）
        """
        if sources is None:
            sources = ["eastmoney", "sina", "cailian"]

        all_news = []

        for source in sources:
            collector = self.collectors.get(source)
            if collector:
                news_list = collector.collect(stock_code, limit)
                all_news.extend(news_list)
                logger.info(f"从 {source} 采集 {len(news_list)} 条新闻")

        # 去重（基于标题）
        seen_titles = set()
        unique_news = []
        for news in all_news:
            if news.title not in seen_titles:
                seen_titles.add(news.title)
                unique_news.append(news)

        # 按时间排序
        unique_news.sort(key=lambda x: x.publish_time, reverse=True)

        logger.info(f"采集完成，共 {len(unique_news)} 条唯一新闻")
        return unique_news


# 默认导出复合采集器
__all__ = ["NewsCollector", "CompositeNewsCollector", "NewsItem"]
