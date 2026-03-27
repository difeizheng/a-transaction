"""
并行数据采集模块
功能：使用异步/多线程优化数据采集性能
"""
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from threading import Lock
import time
import logging

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class FetchResult:
    """抓取结果"""
    stock_code: str
    data_type: str
    success: bool
    data: Any = None
    error: str = ""
    fetch_time: float = 0.0  # 抓取耗时 (ms)
    source: str = ""


@dataclass
class BatchFetchResult:
    """批量抓取结果"""
    total: int
    success_count: int
    failed_count: int
    total_time: float  # 总耗时 (ms)
    avg_time: float    # 平均耗时 (ms)
    results: List[FetchResult] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "total": self.total,
            "success": self.success_count,
            "failed": self.failed_count,
            "total_time_ms": f"{self.total_time:.0f}",
            "avg_time_ms": f"{self.avg_time:.0f}",
            "success_rate": f"{self.success_count / self.total * 100:.1f}%" if self.total > 0 else "0%",
        }


class AsyncDataFetcher:
    """
    异步数据抓取器

    使用 aiohttp 实现高并发 HTTP 请求
    """

    def __init__(self, max_concurrent: int = 10, timeout: int = 30):
        """
        初始化异步抓取器

        Args:
            max_concurrent: 最大并发数
            timeout: 请求超时时间 (秒)
        """
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch(
        self,
        session: aiohttp.ClientSession,
        url: str,
        stock_code: str,
        data_type: str,
        source: str,
    ) -> FetchResult:
        """异步抓取单个 URL"""
        start_time = time.time()

        async with self._semaphore:
            try:
                async with session.get(url, timeout=self.timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        return FetchResult(
                            stock_code=stock_code,
                            data_type=data_type,
                            success=True,
                            data=data,
                            fetch_time=(time.time() - start_time) * 1000,
                            source=source,
                        )
                    else:
                        return FetchResult(
                            stock_code=stock_code,
                            data_type=data_type,
                            success=False,
                            error=f"HTTP {response.status}",
                            fetch_time=(time.time() - start_time) * 1000,
                            source=source,
                        )
            except asyncio.TimeoutError:
                return FetchResult(
                    stock_code=stock_code,
                    data_type=data_type,
                    success=False,
                    error="Timeout",
                    fetch_time=(time.time() - start_time) * 1000,
                    source=source,
                )
            except Exception as e:
                return FetchResult(
                    stock_code=stock_code,
                    data_type=data_type,
                    success=False,
                    error=str(e),
                    fetch_time=(time.time() - start_time) * 1000,
                    source=source,
                )

    async def fetch_batch(
        self,
        urls: List[Dict],
    ) -> BatchFetchResult:
        """
        批量异步抓取

        Args:
            urls: URL 列表，每项包含 {url, stock_code, data_type, source}

        Returns:
            批量抓取结果
        """
        start_time = time.time()

        connector = aiohttp.TCPConnector(limit=self.max_concurrent)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                self.fetch(
                    session,
                    item["url"],
                    item["stock_code"],
                    item["data_type"],
                    item["source"],
                )
                for item in urls
            ]

            results = await asyncio.gather(*tasks)

        total_time = (time.time() - start_time) * 1000
        success_count = sum(1 for r in results if r.success)

        return BatchFetchResult(
            total=len(results),
            success_count=success_count,
            failed_count=len(results) - success_count,
            total_time=total_time,
            avg_time=total_time / len(results) if results else 0,
            results=list(results),
        )


class ThreadPoolDataFetcher:
    """
    线程池数据抓取器

    适用于 CPU 密集型任务或需要阻塞 IO 的场景
    """

    def __init__(self, max_workers: int = 10):
        """
        初始化线程池抓取器

        Args:
            max_workers: 最大工作线程数
        """
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = Lock()

    def fetch(
        self,
        fetch_func: Callable[[str], Any],
        stock_code: str,
        data_type: str,
        source: str,
    ) -> FetchResult:
        """
        抓取单个股票数据

        Args:
            fetch_func: 抓取函数 (接收 stock_code 返回数据)
            stock_code: 股票代码
            data_type: 数据类型
            source: 数据源

        Returns:
            抓取结果
        """
        start_time = time.time()

        try:
            data = fetch_func(stock_code)
            return FetchResult(
                stock_code=stock_code,
                data_type=data_type,
                success=True,
                data=data,
                fetch_time=(time.time() - start_time) * 1000,
                source=source,
            )
        except Exception as e:
            return FetchResult(
                stock_code=stock_code,
                data_type=data_type,
                success=False,
                error=str(e),
                fetch_time=(time.time() - start_time) * 1000,
                source=source,
            )

    def fetch_batch(
        self,
        fetch_func: Callable[[str], Any],
        stock_codes: List[str],
        data_type: str,
        source: str,
    ) -> BatchFetchResult:
        """
        批量抓取

        Args:
            fetch_func: 抓取函数
            stock_codes: 股票代码列表
            data_type: 数据类型
            source: 数据源

        Returns:
            批量抓取结果
        """
        start_time = time.time()

        futures = {
            self._executor.submit(
                self.fetch,
                fetch_func,
                code,
                data_type,
                source,
            ): code
            for code in stock_codes
        }

        results = []
        for future in as_completed(futures):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                code = futures[future]
                results.append(FetchResult(
                    stock_code=code,
                    data_type=data_type,
                    success=False,
                    error=str(e),
                    fetch_time=0,
                    source=source,
                ))

        total_time = (time.time() - start_time) * 1000
        success_count = sum(1 for r in results if r.success)

        return BatchFetchResult(
            total=len(results),
            success_count=success_count,
            failed_count=len(results) - success_count,
            total_time=total_time,
            avg_time=total_time / len(results) if results else 0,
            results=results,
        )

    def shutdown(self):
        """关闭线程池"""
        self._executor.shutdown(wait=True)


class ParallelPriceCollector:
    """
    并行行情数据采集器

    整合多种数据源，使用并行方式抓取
    """

    def __init__(
        self,
        price_collector,
        max_concurrent: int = 5,
        use_async: bool = True,
    ):
        """
        初始化并行采集器

        Args:
            price_collector: 原始 PriceCollector 实例
            max_concurrent: 最大并发数
            use_async: 是否使用异步 (True=异步，False=线程池)
        """
        self.price_collector = price_collector
        self.max_concurrent = max_concurrent
        self.use_async = use_async

        if use_async:
            self.async_fetcher = AsyncDataFetcher(max_concurrent=max_concurrent)
        else:
            self.thread_fetcher = ThreadPoolDataFetcher(max_workers=max_concurrent)

    def get_batch_kline(
        self,
        stock_codes: List[str],
        period: str = "daily",
        limit: int = 120,
    ) -> BatchFetchResult:
        """
        批量获取 K 线数据

        Args:
            stock_codes: 股票代码列表
            period: 周期 (daily/weekly/monthly)
            limit: 数据条数

        Returns:
            批量抓取结果
        """
        if self.use_async:
            # 构建 URL 列表（异步方式）
            urls = []
            for code in stock_codes:
                # 使用新浪财经 API（示例）
                if code.startswith("6"):
                    market = "sh"
                else:
                    market = "sz"

                url = f"http://api.finance.ifeng.com/akdaily/?code={market}{code}&type=last_{limit}"
                urls.append({
                    "url": url,
                    "stock_code": code,
                    "data_type": "kline",
                    "source": "ifeng",
                })

            # 异步抓取
            return asyncio.run(self.async_fetcher.fetch_batch(urls))
        else:
            # 线程池方式
            def fetch_kline(code: str):
                return self.price_collector.get_kline(code, period=period, limit=limit)

            return self.thread_fetcher.fetch_batch(
                fetch_kline,
                stock_codes,
                data_type="kline",
                source="collector",
            )

    def get_batch_realtime(
        self,
        stock_codes: List[str],
    ) -> BatchFetchResult:
        """
        批量获取实时行情

        Args:
            stock_codes: 股票代码列表

        Returns:
            批量抓取结果
        """
        if self.use_async:
            # 构建 URL 列表
            codes_str = ",".join(
                [f"sh{c}" if c.startswith("6") else f"sz{c}" for c in stock_codes]
            )
            url = f"http://hq.sinajs.cn/list={codes_str}"

            urls = [{
                "url": url,
                "stock_code": code,
                "data_type": "realtime",
                "source": "sina",
            } for code in stock_codes]

            return asyncio.run(self.async_fetcher.fetch_batch(urls))
        else:
            def fetch_realtime(code: str):
                return self.price_collector.get_realtime_quote(code)

            return self.thread_fetcher.fetch_batch(
                fetch_realtime,
                stock_codes,
                data_type="realtime",
                source="collector",
            )


def run_parallel_fetch_demo():
    """并行抓取演示"""
    print("=" * 60)
    print("并行数据采集演示")
    print("=" * 60)

    from src.collectors.price_collector import PriceCollector

    # 测试股票列表
    stock_codes = ["000001", "000002", "000948", "600000", "601360"]

    print(f"\n测试股票：{stock_codes}")

    # 创建采集器
    collector = PriceCollector()
    parallel_collector = ParallelPriceCollector(
        collector,
        max_concurrent=5,
        use_async=False,  # 使用线程池
    )

    # 测试批量 K 线获取
    print("\n[测试] 批量获取 K 线数据...")
    kline_result = parallel_collector.get_batch_kline(
        stock_codes,
        period="daily",
        limit=30,
    )

    print(f"K 线抓取结果：{kline_result.to_dict()}")

    # 测试批量实时行情
    print("\n[测试] 批量获取实时行情...")
    realtime_result = parallel_collector.get_batch_realtime(stock_codes)

    print(f"实时行情抓取结果：{realtime_result.to_dict()}")

    # 性能对比
    print("\n" + "=" * 60)
    print("性能对比")
    print("=" * 60)

    # 串行获取（模拟）
    print("\n串行方式（估算）:")
    single_time = kline_result.avg_time * len(stock_codes)
    print(f"  预计总耗时：{single_time:.0f}ms")

    print(f"\n并行方式（实际）:")
    print(f"  实际总耗时：{kline_result.total_time:.0f}ms")

    if single_time > 0:
        speedup = single_time / kline_result.total_time
        print(f"  加速比：{speedup:.1f}x")

    return kline_result, realtime_result


if __name__ == "__main__":
    run_parallel_fetch_demo()
