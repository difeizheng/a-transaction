"""
A 股自动监控系统 - 主入口

功能：
- 定时任务调度
- 数据采集协调
- 信号生成与输出
- 异常处理
"""
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from src.config.settings import load_config, get_config
from src.utils.logger import setup_logger, get_logger
from src.utils.db import Database
from src.utils.notification import NotificationManager

from src.collectors.news_collector import CompositeNewsCollector
from src.collectors.price_collector import PriceCollector
from src.collectors.fund_collector import FundCollector

from src.analyzers.sentiment_analyzer import SentimentAnalyzer
from src.analyzers.technical_analyzer import TechnicalAnalyzer
from src.analyzers.fund_analyzer import FundAnalyzer

from src.engine.signal_fusion import SignalFusionEngine
from src.engine.decision_engine import DecisionEngine
from src.engine.risk_manager import RiskManager

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

logger = get_logger(__name__)
console = Console()


class AStockMonitor:
    """
    A 股自动监控系统主类
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化监控系统

        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self._initialized = False

        # 配置
        self.settings = None

        # 数据采集器
        self.news_collector = None
        self.price_collector = None
        self.fund_collector = None

        # 分析器
        self.sentiment_analyzer = None
        self.technical_analyzer = None
        self.fund_analyzer = None

        # 引擎
        self.signal_fusion = None
        self.decision_engine = None
        self.risk_manager = None

        # 工具
        self.db = None
        self.notification = None

        # 调度器
        self.scheduler = None

        # 状态
        self.stock_pool: List[Dict] = []
        self.last_run: Optional[datetime] = None

    def initialize(self):
        """初始化系统"""
        if self._initialized:
            return

        logger.info("正在初始化 A 股监控系统...")

        # 1. 加载配置
        self.settings = load_config(self.config_path)
        logger.info(f"配置加载成功：股票池={self.settings.stock_pool_type}, "
                   f"监控间隔={self.settings.monitor_interval}秒")

        # 2. 确保目录存在
        Path(self.settings.log_dir).mkdir(parents=True, exist_ok=True)
        Path(self.settings.data_dir).mkdir(parents=True, exist_ok=True)

        # 3. 设置日志
        setup_logger(
            log_dir=self.settings.log_dir,
            log_level=self.settings.log_level,
        )

        # 4. 初始化数据库
        self.db = Database(self.settings.db_path)
        logger.info("数据库初始化成功")

        # 5. 初始化数据采集器
        self.news_collector = CompositeNewsCollector()
        self.price_collector = PriceCollector()
        self.fund_collector = FundCollector()
        logger.info("数据采集器初始化成功")

        # 6. 初始化分析器
        self.sentiment_analyzer = SentimentAnalyzer(model=self.settings.news_weight > 0)
        self.technical_analyzer = TechnicalAnalyzer()
        self.fund_analyzer = FundAnalyzer()
        logger.info("分析器初始化成功")

        # 7. 初始化引擎
        self.signal_fusion = SignalFusionEngine(
            news_weight=self.settings.news_weight,
            technical_weight=self.settings.technical_weight,
            fund_weight=self.settings.fund_weight,
            sentiment_weight=self.settings.sentiment_weight,
        )

        self.decision_engine = DecisionEngine(
            initial_capital=self.settings.initial_capital,
            max_position_per_stock=self.settings.max_position_per_stock,
            max_total_position=self.settings.max_total_position,
            stop_loss=self.settings.stop_loss,
            take_profit=self.settings.take_profit,
            min_buy_score=self.settings.min_buy_score,
            max_sell_score=self.settings.max_sell_score,
        )

        self.risk_manager = RiskManager(
            max_drawdown=self.settings.max_drawdown,
            max_position_per_stock=self.settings.max_position_per_stock,
            max_total_position=self.settings.max_total_position,
            stop_loss=self.settings.stop_loss,
            take_profit=self.settings.take_profit,
            blacklist=self.settings.blacklist,
            exclude_st=self.settings.exclude_st,
            exclude_kcb=self.settings.exclude_kcb,
        )
        logger.info("决策引擎初始化成功")

        # 8. 初始化通知
        self.notification = NotificationManager(
            wechat_webhook=self.settings.wechat_webhook,
            dingtalk_webhook=self.settings.dingtalk_webhook,
            console_output=self.settings.console_output,
        )
        logger.info("通知管理器初始化成功")

        # 9. 初始化调度器
        self.scheduler = BlockingScheduler()
        logger.info("调度器初始化成功")

        # 10. 加载股票池
        self._load_stock_pool()

        self._initialized = True
        logger.info("=" * 50)
        logger.info("A 股监控系统初始化完成")
        logger.info("=" * 50)

    def _load_stock_pool(self):
        """加载股票池"""
        logger.info("正在加载股票池...")

        if self.settings.stock_pool_type == "custom":
            # 自定义股票池
            codes = self.settings.custom_stock_codes
            self.stock_pool = [{"code": code, "name": ""} for code in codes]
        elif self.settings.stock_pool_type == "hs300":
            # 沪深 300
            stocks = self.price_collector.get_hs300_stocks()
            self.stock_pool = stocks[:self.settings.max_stocks]
        else:
            # 全部 A 股
            stocks = self.price_collector.get_all_stocks()
            self.stock_pool = stocks[:self.settings.max_stocks]

        # 过滤黑名单和 ST
        filtered = []
        for stock in self.stock_pool:
            code = stock.get("code", "")
            name = stock.get("name", "")

            # 检查黑名单
            if code in self.risk_manager.blacklist:
                continue

            # 检查 ST
            if self.settings.exclude_st and ("ST" in name or "*ST" in name):
                continue

            filtered.append(stock)

        self.stock_pool = filtered
        logger.info(f"股票池加载完成，共 {len(self.stock_pool)} 只股票")

    def run_once(self):
        """执行一次完整监控流程"""
        start_time = datetime.now()
        logger.info(f"开始执行监控任务 - {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            # 检查是否在交易时间
            if self.settings.market_hours_only:
                if not self.price_collector.is_trading_time():
                    logger.info("非交易时间，跳过监控")
                    return

            # 1. 采集数据并分析
            results = []

            # 限制处理数量，避免耗时过长
            process_count = min(len(self.stock_pool), 20)  # 每次最多处理 20 只
            sample_stocks = self.stock_pool[:process_count]

            for stock in sample_stocks:
                try:
                    result = self._analyze_stock(stock)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"分析股票 {stock.get('code')} 失败：{e}")
                    continue

            # 2. 生成信号
            if results:
                fused_results = self.signal_fusion.fuse_batch(results)

                # 3. 生成决策并输出
                self._output_signals(fused_results)

                # 4. 发送通知
                self._send_notifications(fused_results)

            # 5. 记录运行时间
            self.last_run = datetime.now()
            elapsed = (self.last_run - start_time).total_seconds()
            logger.info(f"监控任务执行完成，耗时 {elapsed:.1f} 秒")

        except Exception as e:
            logger.error(f"执行监控任务失败：{e}", exc_info=True)

    def _analyze_stock(self, stock: Dict) -> Optional[Dict]:
        """
        分析单只股票

        Args:
            stock: 股票信息

        Returns:
            分析结果
        """
        code = stock.get("code", "")
        name = stock.get("name", "")

        if not code:
            return None

        # 1. 获取行情数据
        kline_data = self.price_collector.get_kline(code, period="daily", limit=60)
        if kline_data.empty:
            return None

        # 2. 技术分析
        tech_signal = self.technical_analyzer.analyze(kline_data)
        technical_score = tech_signal.score

        # 3. 获取资金数据
        fund_flow = self.fund_collector.get_stock_fund_flow(code)
        fund_signal = self.fund_analyzer.analyze(stock_fund_flow=fund_flow)
        fund_score = fund_signal.score

        # 4. 获取新闻并分析
        news_list = self.news_collector.collect(stock_code=code, limit=5)
        if news_list:
            news_texts = [f"{n.title} {n.content}" for n in news_list]
            combined_news = " ".join(news_texts)
            sentiment_result = self.sentiment_analyzer.analyze(combined_news)
            news_score = sentiment_result.score
        else:
            news_score = 0.0

        # 5. 市场情绪（简化为 0）
        sentiment_score = 0.0

        return {
            "stock_code": code,
            "stock_name": name,
            "news_score": news_score,
            "technical_score": technical_score,
            "fund_score": fund_score,
            "sentiment_score": sentiment_score,
            "current_price": float(kline_data["close"].iloc[-1]) if not kline_data.empty else 0,
        }

    def _output_signals(self, results):
        """输出信号到终端"""
        if not self.settings.console_output:
            return

        # 创建信号表格
        table = Table(title=f"[bold cyan]交易信号 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold cyan]")
        table.add_column("代码", style="cyan")
        table.add_column("名称", style="white")
        table.add_column("信号", style="green")
        table.add_column("得分", style="yellow")
        table.add_column("新闻", style="blue")
        table.add_column("技术", style="blue")
        table.add_column("资金", style="blue")
        table.add_column("置信度", style="magenta")

        # 信号颜色映射
        signal_colors = {
            "strong_buy": "green",
            "buy": "light_green",
            "hold": "yellow",
            "sell": "red",
            "strong_sell": "bright_red",
        }

        signal_labels = {
            "strong_buy": "强烈买入",
            "buy": "买入",
            "hold": "持有",
            "sell": "卖出",
            "strong_sell": "强烈卖出",
        }

        # 只显示有明确信号的
        for r in results[:15]:
            if r.signal in ["strong_buy", "buy", "sell", "strong_sell"]:
                table.add_row(
                    r.stock_code,
                    r.stock_name or "",
                    f"[{signal_colors.get(r.signal, 'white')}]{signal_labels.get(r.signal, r.signal)}[/{signal_colors.get(r.signal, 'white')}]",
                    f"{r.total_score:.2f}",
                    f"{r.news_score:.2f}",
                    f"{r.technical_score:.2f}",
                    f"{r.fund_score:.2f}",
                    f"{r.confidence:.1%}",
                )

        console.print(table)

        # 显示汇总
        summary = self.signal_fusion.generate_summary(results)
        summary_table = Table(title="[bold green]信号汇总[/bold green]")
        summary_table.add_column("类型", style="cyan")
        summary_table.add_column("数量", style="white")
        summary_table.add_row("强烈买入", f"[green]{summary.get('strong_buy', 0)}[/green]")
        summary_table.add_row("买入", f"[light_green]{summary.get('buy', 0)}[/light_green]")
        summary_table.add_row("持有", f"[yellow]{summary.get('hold', 0)}[/yellow]")
        summary_table.add_row("卖出", f"[red]{summary.get('sell', 0)}[/red]")
        summary_table.add_row("强烈卖出", f"[bright_red]{summary.get('strong_sell', 0)}[/bright_red]")
        summary_table.add_row("平均得分", f"{summary.get('avg_score', 0):.3f}")

        console.print(summary_table)

    def _send_notifications(self, results):
        """发送通知"""
        if not self.settings.notification_enabled:
            return

        # 筛选重要信号
        important_signals = [
            r for r in results
            if r.signal in ["strong_buy", "strong_sell"] or abs(r.total_score) >= self.settings.signal_threshold
        ]

        if not important_signals:
            return

        # 发送每个重要信号
        for signal in important_signals[:5]:  # 最多发送 5 个
            self.notification.send_signal(
                stock_code=signal.stock_code,
                stock_name=signal.stock_name,
                signal_type=signal.signal.split("_")[-1] if "_" in signal.signal else signal.signal,
                signal_score=signal.total_score,
                decision={
                    "strong_buy": "强烈买入",
                    "buy": "买入",
                    "hold": "持有",
                    "sell": "卖出",
                    "strong_sell": "强烈卖出",
                }.get(signal.signal, signal.signal),
                price=signal.sentiment_score,  # 这里应该传入当前价格
                reason=f"综合得分：{signal.total_score:.2f}, "
                       f"新闻：{signal.news_score:.2f}, "
                       f"技术：{signal.technical_score:.2f}, "
                       f"资金：{signal.fund_score:.2f}",
            )

    def start(self):
        """启动监控系统"""
        if not self._initialized:
            self.initialize()

        logger.info("启动监控系统...")

        # 添加定时任务
        interval_seconds = self.settings.monitor_interval

        self.scheduler.add_job(
            self.run_once,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="monitor_task",
            name="A 股监控任务",
            replace_existing=True,
        )

        # 添加每日汇总任务（收盘后）
        self.scheduler.add_job(
            self._daily_summary,
            trigger=CronTrigger(hour=15, minute=30),  # 15:30
            id="daily_summary",
            name="每日汇总",
            replace_existing=True,
        )

        console.print(Panel(
            f"[green]A 股自动监控系统已启动[/green]\n\n"
            f"监控间隔：{interval_seconds}秒\n"
            "监控股票数：" + str(len(self.stock_pool)) + "\n"
            f"日志目录：{self.settings.log_dir}\n\n"
            "[yellow]按 Ctrl+C 停止系统[/yellow]",
            title="[bold] 系统状态[/bold]",
            border_style="green",
        ))

        # 先执行一次
        self.run_once()

        # 启动调度器
        try:
            self.scheduler.start()
        except KeyboardInterrupt:
            logger.info("收到中断信号，正在停止系统...")
            self.shutdown()

    def shutdown(self):
        """关闭系统"""
        if self.scheduler:
            self.scheduler.shutdown()
        logger.info("系统已关闭")

    def _daily_summary(self):
        """每日汇总"""
        logger.info("生成每日汇总...")
        # 这里可以实现每日汇总逻辑，包括：
        # - 今日交易信号统计
        # - 模拟收益计算
        # - 风险评估
        pass


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="A 股自动监控系统")
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="配置文件路径"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="只执行一次，不启动调度器"
    )

    args = parser.parse_args()

    # 创建监控器
    monitor = AStockMonitor(config_path=args.config)

    if args.once:
        # 只执行一次
        monitor.initialize()
        monitor.run_once()
    else:
        # 启动持续监控
        monitor.start()


if __name__ == "__main__":
    main()
