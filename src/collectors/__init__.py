"""
collectors 包初始化 - 数据采集器模块
"""
from .news_collector import NewsCollector
from .price_collector import PriceCollector
from .fund_collector import FundCollector

__all__ = ["NewsCollector", "PriceCollector", "FundCollector"]
