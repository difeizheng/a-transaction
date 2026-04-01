"""
爬虫调度器 - 后台定时采集股票新闻

功能：
- 后台线程定时采集新闻
- 支持动态修改采集间隔
- 支持动态添加/删除目标股票
- 采集结果自动保存到数据库并做情感分析
"""
import threading
import time
import sqlite3
from typing import List, Dict, Optional
from datetime import datetime
from dataclasses import dataclass

import akshare as ak

from src.utils.logger import get_logger
from src.analyzers.sentiment_analyzer import SentimentAnalyzer

logger = get_logger(__name__)


@dataclass
class CrawlerConfig:
    """爬虫配置"""
    enabled: bool = False
    interval: int = 300  # 秒
    stock_codes: List[str] = None
    news_limit: int = 20
    akshare_enabled: bool = True


class CrawlerScheduler:
    """爬虫调度器"""

    def __init__(self, config: CrawlerConfig = None):
        self.config = config or CrawlerConfig()
        self._running = False
        self._thread = None
        self._db_path = "data/trading.db"

        # 初始化情感分析器
        self.sentiment_analyzer = SentimentAnalyzer()

        logger.info(f"爬虫调度器初始化完成，间隔: {self.config.interval}秒")

    def start(self):
        """启动爬虫"""
        if self._running:
            logger.warning("爬虫已在运行中")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("爬虫已启动")

    def stop(self):
        """停止爬虫"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("爬虫已停止")

    def _run(self):
        """爬虫主循环"""
        while self._running:
            try:
                self._crawl_all()
            except Exception as e:
                logger.error(f"爬虫执行出错: {e}")

            # 检查是否还在运行
            if self._running:
                time.sleep(self.config.interval)

    def _crawl_all(self):
        """采集所有配置的股票和来源"""
        if not self.config.stock_codes:
            logger.debug("没有配置目标股票")
            return

        total_collected = 0

        for stock_code in self.config.stock_codes:
            # 使用 AkShare 采集
            if self.config.akshare_enabled:
                try:
                    count = self._crawl_akshare(stock_code)
                    total_collected += count
                except Exception as e:
                    logger.error(f"AkShare 采集失败 {stock_code}: {e}")

        if total_collected > 0:
            logger.info(f"本次采集完成，共 {total_collected} 条新闻")

    def _crawl_akshare(self, stock_code: str) -> int:
        """使用 AkShare 采集新闻"""
        count = 0
        try:
            # AkShare 财经新闻接口
            df = ak.stock_news_em(symbol=stock_code)
            if df is not None and not df.empty:
                self._save_akshare_news(df, stock_code)
                count = len(df)
        except Exception as e:
            logger.error(f"AkShare 新闻采集错误: {e}")
        return count

    def _save_akshare_news(self, df, stock_code: str):
        """保存 AkShare 新闻到数据库"""
        if df is None or df.empty:
            return

        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        # 获取列名（处理编码问题）
        cols = list(df.columns)
        # 列名映射（根据实际数据结构调整）
        col_map = {
            '关键词': 0,       # 股票代码
            '股票代码': 1,    # 新闻标题
            '新闻内容': 2,    # 新闻内容
            '发布时间': 3,    # 发布时间
            '新闻来源': 4,    # 新闻来源
            '文章地址': 5    # 文章URL
        }

        for _, row in df.iterrows():
            try:
                # 尝试获取正确的数据
                title = str(row.iloc[1]) if len(row) > 1 else str(stock_code)
                content = str(row.iloc[2]) if len(row) > 2 else ""
                publish_time = str(row.iloc[3]) if len(row) > 3 else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                source = str(row.iloc[4]) if len(row) > 4 else "东方财富"
                url = str(row.iloc[5]) if len(row) > 5 else ""

                # 情感分析
                try:
                    full_text = f"{title} {content}"
                    sentiment = self.sentiment_analyzer.analyze(text=full_text[:500])  # 限制长度
                    sentiment_score = sentiment.score
                    sentiment_label = sentiment.label
                except Exception as e:
                    sentiment_score = 0
                    sentiment_label = "中性"

                # 保存到数据库
                cursor.execute("""
                    INSERT OR REPLACE INTO news
                    (stock_code, title, content, source, url, publish_time,
                     sentiment_score, sentiment_label, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    stock_code,
                    title,
                    content[:500],  # 限制内容长度
                    source,
                    url,
                    publish_time[:19] if len(publish_time) > 19 else publish_time,
                    sentiment_score,
                    sentiment_label,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
            except Exception as e:
                logger.debug(f"保存新闻失败: {e}")

        conn.commit()
        conn.close()

    def update_config(self, config: CrawlerConfig):
        """更新配置"""
        self.config = config
        logger.info("爬虫配置已更新")

    def add_stock(self, stock_code: str):
        """添加目标股票"""
        if stock_code not in self.config.stock_codes:
            self.config.stock_codes.append(stock_code)
            logger.info(f"添加目标股票: {stock_code}")

    def remove_stock(self, stock_code: str):
        """移除目标股票"""
        if stock_code in self.config.stock_codes:
            self.config.stock_codes.remove(stock_code)
            logger.info(f"移除目标股票: {stock_code}")

    def crawl_now(self, stock_codes: List[str] = None, sources: List[str] = None):
        """立即采集指定股票的新闻"""
        target_codes = stock_codes or self.config.stock_codes
        collected = 0

        for stock_code in target_codes:
            if self.config.akshare_enabled:
                try:
                    count = self._crawl_akshare(stock_code)
                    collected += count
                except Exception as e:
                    logger.error(f"采集失败: {e}")

        return collected

    def get_stats(self) -> Dict:
        """获取采集统计"""
        stats = {
            "total_news": 0,
            "stocks": set(),
            "sources": set(),
            "latest_time": None
        }

        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()

            # 总数
            cursor.execute("SELECT COUNT(*) FROM news")
            stats["total_news"] = cursor.fetchone()[0]

            # 股票列表
            cursor.execute("SELECT DISTINCT stock_code FROM news")
            stats["stocks"] = {row[0] for row in cursor.fetchall()}

            # 数据源
            cursor.execute("SELECT DISTINCT source FROM news")
            stats["sources"] = {row[0] for row in cursor.fetchall()}

            # 最新时间
            cursor.execute("SELECT MAX(created_at) FROM news")
            stats["latest_time"] = cursor.fetchone()[0]

            conn.close()
        except Exception as e:
            logger.error(f"获取统计失败: {e}")

        return stats


# 全局爬虫实例
_crawler_scheduler = None


def get_crawler_scheduler(config: CrawlerConfig = None) -> CrawlerScheduler:
    """获取爬虫调度器实例"""
    global _crawler_scheduler
    if _crawler_scheduler is None:
        _crawler_scheduler = CrawlerScheduler(config)
    return _crawler_scheduler


__all__ = ["CrawlerScheduler", "CrawlerConfig", "get_crawler_scheduler"]