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
import sqlite3
import pandas as pd
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
from src.analyzers.volatility_analyzer import VolatilityAnalyzer, DynamicStopLossManager
from src.analyzers.market_regime_analyzer import MarketRegimeAnalyzer
from src.analyzers.sector_analyzer import SectorAnalyzer

from src.strategy.improved_strategy import ImprovedStrategy, StrategySignal

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
        self.volatility_analyzer = None
        self.market_regime_analyzer = None
        self.sector_analyzer = None

        # 策略
        self.improved_strategy = None

        # 引擎
        self.signal_fusion = None
        self.decision_engine = None
        self.risk_manager = None
        self.stop_loss_manager = None

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
        self.volatility_analyzer = VolatilityAnalyzer()
        self.market_regime_analyzer = MarketRegimeAnalyzer()
        self.sector_analyzer = SectorAnalyzer()
        logger.info("分析器初始化成功 - 新增市场状态判断、板块联动分析")

        # 7. 初始化 V3 改进策略（ADX 震荡过滤 + 实盘优化参数）
        # 核心改进：ADX>=30 过滤震荡市，胜率突破 50%
        self.improved_strategy = ImprovedStrategy(
            buy_threshold=0.7,           # 买入分数阈值
            sell_threshold=0.5,          # 卖出分数阈值
            min_buy_conditions=5,        # 最少买入条件数
            min_sell_conditions=3,       # 最少卖出条件数
            atr_multiplier=3.0,          # ATR 止损倍数
            min_stop_distance=0.08,      # 最小止损距离 8%
            max_stop_distance=0.20,      # 最大止损距离 20%
            profit_ratio=2.5,            # 止盈/止损比率
        )
        logger.info("V3 改进策略初始化成功 - ADX 震荡过滤 (>=30), 买入阈值 0.7, 最少 5 条件，止损 8%-20%")

        # 8. 分析当前市场状态，动态调整信号权重
        logger.info("正在分析当前市场状态...")
        try:
            # 获取沪深 300 指数数据（使用 akshare 指数格式）
            try:
                import akshare as ak
                index_data = ak.stock_zh_index_daily(symbol="sh000300")
                if index_data is not None and not index_data.empty:
                    # 重命名列为系统格式
                    index_data = index_data.rename(columns={
                        'close': 'close',
                        'open': 'open',
                        'high': 'high',
                        'low': 'low',
                        'volume': 'volume'
                    })
                    index_data.set_index('date', inplace=True)
            except Exception as e:
                logger.warning(f"AkShare 获取指数失败：{e}，使用备用方案")
                index_data = pd.DataFrame()

            if not index_data.empty and len(index_data) >= 60:
                # 获取市场宽度数据
                market_breadth = self._get_market_breadth()

                # 分析市场状态
                regime_signal = self.market_regime_analyzer.analyze(index_data, market_breadth)
                logger.info(f"当前市场状态：{regime_signal.regime}, 综合得分：{regime_signal.composite_score:.2f}")
                logger.info(f"操作建议：{regime_signal.suggestion}")

                # 根据市场状态调整信号融合权重
                weights = self.market_regime_analyzer.get_weight_adjustment(regime_signal.regime)
                self.signal_fusion = SignalFusionEngine(
                    news_weight=weights["news"],
                    technical_weight=weights["technical"],
                    fund_weight=weights["fund"],
                    sentiment_weight=weights["sentiment"],
                    market_regime=regime_signal.regime,
                )
                logger.info(f"动态权重配置：新闻={weights['news']:.0%}, 技术={weights['technical']:.0%}, "
                           f"资金={weights['fund']:.0%}, 波动率={weights['volatility']:.0%}, "
                           f"情绪={weights['sentiment']:.0%}")
            else:
                logger.warning("无法获取指数数据，使用默认权重")
                self._init_signal_fusion_default()
        except Exception as e:
            logger.error(f"分析市场状态失败：{e}，使用默认权重")
            self._init_signal_fusion_default()

        # 9. 初始化决策引擎
        self.decision_engine = DecisionEngine(
            initial_capital=self.settings.initial_capital,
            max_position_per_stock=self.settings.max_position_per_stock,
            max_total_position=self.settings.max_total_position,
            stop_loss=self.settings.stop_loss,
            take_profit=self.settings.take_profit,
            min_buy_score=self.settings.min_buy_score,
            max_sell_score=self.settings.max_sell_score,
        )

        # 10. 初始化风控管理器（增强组合级风控）
        self.risk_manager = RiskManager(
            max_drawdown=self.settings.max_drawdown,
            max_position_per_stock=self.settings.max_position_per_stock,
            max_total_position=self.settings.max_total_position,
            max_industry_exposure=self.settings.max_industry_exposure,  # 单行业最大暴露 30%
            stop_loss=self.settings.stop_loss,
            take_profit=self.settings.take_profit,
            blacklist=self.settings.blacklist,
            exclude_st=self.settings.exclude_st,
            exclude_kcb=self.settings.exclude_kcb,
        )

        # 初始化动态止损管理器
        self.stop_loss_manager = DynamicStopLossManager(
            atr_multiplier=2.0,
            min_stop_distance=0.03,
            max_stop_distance=0.15,
        )

        logger.info("决策引擎初始化成功")

        # 8. 初始化通知
        self.notification = NotificationManager(
            wechat_webhook=self.settings.wechat_webhook,
            dingtalk_webhook=self.settings.dingtalk_webhook,
            dingtalk_secret=self.settings.dingtalk_secret,
            hook_url=self.settings.hook_url,
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

        # 从数据库获取股票名称的辅助函数
        def get_stock_name_from_db(code: str) -> str:
            """从数据库获取股票名称"""
            try:
                conn = sqlite3.connect(self.settings.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM stocks WHERE code = ?", (code,))
                row = cursor.fetchone()
                conn.close()
                if row and row[0]:
                    return row[0]
                return ""
            except Exception as e:
                logger.warning(f"从数据库获取股票名称失败 ({code}): {e}")
                return ""

        if self.settings.stock_pool_type == "custom":
            # 自定义股票池 - 获取股票名称
            codes = self.settings.custom_stock_codes
            self.stock_pool = []
            for code in codes:
                try:
                    # 优先从数据库获取股票名称
                    name = get_stock_name_from_db(code)
                    # 备用：从 API 获取
                    if not name:
                        stock_info = self.price_collector.get_stock_info(code)
                        name = stock_info.get("name", "") if stock_info else ""
                    self.stock_pool.append({"code": code, "name": name})
                    logger.info(f"股票 {code}: {name}")
                except Exception as e:
                    logger.warning(f"获取股票 {code} 信息失败：{e}")
                    self.stock_pool.append({"code": code, "name": ""})
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

            # 1. 限制处理数量，避免耗时过长
            process_count = min(len(self.stock_pool), 20)  # 每次最多处理 20 只
            sample_stocks = self.stock_pool[:process_count]

            # 2. 生成信号（使用 V3 改进策略 - ADX 震荡过滤）
            results = []
            for stock in sample_stocks:
                try:
                    code = stock.get("code", "")
                    kline_data = self.price_collector.get_kline(
                        code, period="daily", limit=120
                    )
                    if kline_data.empty:
                        continue

                    signal = self.improved_strategy.generate_signal(
                        df=kline_data,
                        stock_code=code,
                        stock_name=stock.get("name", ""),
                    )

                    if signal.signal != "hold":
                        results.append({
                            "stock_code": signal.stock_code,
                            "stock_name": signal.stock_name,
                            "signal": signal.signal,
                            "price": signal.price,
                            "tech_score": signal.tech_score,
                            "buy_score": signal.buy_score,
                            "sell_score": signal.sell_score,
                            "rsi": signal.rsi,
                            "atr": signal.atr,
                            "stop_distance": signal.stop_distance,
                            "take_profit_distance": signal.take_profit_distance,
                        })

                        # 执行买入（V3 策略固定仓位）
                        if signal.signal in ["buy", "strong_buy"]:
                            # 固定仓位：strong_buy 25%, buy 20%
                            position_ratio = 0.25 if signal.signal == "strong_buy" else 0.20
                            quantity = int(self.settings.initial_capital * position_ratio / signal.price / 100) * 100
                            if quantity > 0:
                                self.improved_strategy.update_position(signal, quantity)

                except Exception as e:
                    logger.error(f"分析股票 {stock.get('code')} 失败：{e}")
                    continue

            # 3. 检查持仓退出条件（V3 策略）
            for stock in sample_stocks:
                try:
                    code = stock.get("code", "")
                    kline_data = self.price_collector.get_kline(code, period="daily", limit=5)
                    if kline_data.empty:
                        continue

                    current_price = float(kline_data["close"].iloc[-1])
                    timestamp = datetime.now()

                    # 更新跟踪止损并检查退出
                    pos_info = self.improved_strategy.get_position_info(code)
                    if pos_info:
                        # 更新跟踪止损
                        self.improved_strategy.update_trailing_stop(
                            code, current_price
                        )

                        # 检查退出条件
                        exit_result = self.improved_strategy.check_exit(
                            code, current_price, timestamp
                        )
                        if exit_result:
                            position, exit_reason, exit_price = exit_result
                            logger.info(f"{code}: 触发{exit_reason}，退出价={exit_price:.2f}")
                            self.improved_strategy.remove_position(code)

                except Exception as e:
                    logger.error(f"检查持仓 {stock.get('code')} 失败：{e}")
                    continue

            # 4. 输出信号
            if results:
                self._output_improved_signals(results)

                # 4. 发送通知
                self._send_improved_notifications(results)

            # 5. 统计信号
            buy_count = sum(1 for r in results if r["signal"] in ["buy", "strong_buy"])
            sell_count = sum(1 for r in results if r["signal"] in ["sell", "strong_sell"])
            hold_count = len(results) - buy_count - sell_count

            # 6. 发送监控汇总到 webhook
            self._send_monitor_summary(
                total_stocks=len(sample_stocks),
                bullish_count=buy_count,
                bearish_count=sell_count,
                neutral_count=hold_count,
                top_signals=results,
            )

            # 7. 记录运行时间
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

        # 5. 波动率分析
        vol_signal = self.volatility_analyzer.analyze(kline_data)
        volatility_score = -vol_signal.atr_ratio * 10  # ATR 比率越低越好，转换为 [-1, 1] 得分
        volatility_score = max(-1.0, min(1.0, volatility_score))

        # 6. 市场情绪（简化为 0）
        sentiment_score = 0.0

        return {
            "stock_code": code,
            "stock_name": name,
            "news_score": news_score,
            "technical_score": technical_score,
            "fund_score": fund_score,
            "volatility_score": volatility_score,
            "sentiment_score": sentiment_score,
            "current_price": float(kline_data["close"].iloc[-1]) if not kline_data.empty else 0,
            "volatility_signal": vol_signal,
        }

    def _output_improved_signals(self, results):
        """输出改进策略信号到终端"""
        if not self.settings.console_output:
            return

        # 创建信号表格
        table = Table(title=f"[bold cyan]改进策略信号 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold cyan]")
        table.add_column("代码", style="cyan")
        table.add_column("名称", style="white")
        table.add_column("信号", style="green")
        table.add_column("价格", style="yellow")
        table.add_column("买分", style="blue")
        table.add_column("卖分", style="blue")
        table.add_column("RSI", style="blue")
        table.add_column("止损%", style="red")
        table.add_column("止盈%", style="green")

        # 信号颜色映射
        signal_colors = {
            "strong_buy": "green",
            "buy": "light_green",
            "sell": "red",
            "strong_sell": "bright_red",
        }

        signal_labels = {
            "strong_buy": "强烈买入",
            "buy": "买入",
            "sell": "卖出",
            "strong_sell": "强烈卖出",
        }

        # 显示所有非 hold 信号
        for r in results[:15]:
            table.add_row(
                r["stock_code"],
                r["stock_name"] or "",
                f"[{signal_colors.get(r['signal'], 'white')}]{signal_labels.get(r['signal'], r['signal'])}[/{signal_colors.get(r['signal'], 'white')}]",
                f"{r['price']:.2f}",
                f"{r['buy_score']:.2f}",
                f"{r['sell_score']:.2f}",
                f"{r['rsi']:.0f}",
                f"{r['stop_distance']:.1%}",
                f"{r['take_profit_distance']:.1%}",
            )

        console.print(table)

        # 显示持仓状态
        positions = self.improved_strategy.get_all_positions()
        if positions:
            pos_table = Table(title="[bold yellow]当前持仓[/bold yellow]")
            pos_table.add_column("代码", style="cyan")
            pos_table.add_column("名称", style="white")
            pos_table.add_column("成本", style="yellow")
            pos_table.add_column("止损价", style="red")
            pos_table.add_column("止盈价", style="green")
            pos_table.add_column("最高价", style="magenta")

            for pos in positions:
                pos_table.add_row(
                    pos["stock_code"],
                    pos["stock_name"] or "",
                    f"{pos['avg_cost']:.2f}",
                    f"{pos['current_stop']:.2f}",
                    f"{pos['take_profit']:.2f}",
                    f"{pos['highest_price']:.2f}",
                )
            console.print(pos_table)

    def _send_improved_notifications(self, results):
        """发送改进策略通知 - 所有非 hold 信号"""
        if not self.settings.notification_enabled:
            return

        # 筛选所有非 hold 信号
        all_signals = [
            r for r in results
            if r["signal"] != "hold"
        ]

        if not all_signals:
            logger.debug("本次监控无交易信号，跳过通知")
            return

        # 发送每个信号（限制最多 10 个，避免刷屏）
        for signal in all_signals[:10]:
            # 构建详细的买卖原因
            conditions = signal.get("conditions", {})
            buy_details = conditions.get("buy_details", {})
            sell_details = conditions.get("sell_details", {})

            reason_parts = []

            if signal["signal"] in ["buy", "strong_buy"]:
                # 买入信号原因
                if buy_details.get("above_ma20"):
                    reason_parts.append("趋势向上 (价>MA20)")
                if buy_details.get("ma5_above_ma10"):
                    reason_parts.append("短期强势 (MA5>MA10)")
                if buy_details.get("macd_bullish"):
                    reason_parts.append("MACD 金叉")
                if buy_details.get("rsi_ok"):
                    reason_parts.append("RSI 健康")
                if buy_details.get("tech_positive"):
                    reason_parts.append("技术面积极")
                if buy_details.get("volume_up"):
                    reason_parts.append("成交量放大")
                if buy_details.get("new_high"):
                    reason_parts.append("突破新高")
                reason_parts.append(f"买分={signal['buy_score']:.2f}")
                reason_parts.append(f"RSI={signal['rsi']:.0f}")
            else:
                # 卖出信号原因
                if sell_details.get("below_ma20"):
                    reason_parts.append("趋势向下 (价<MA20)")
                if sell_details.get("ma5_below_ma10"):
                    reason_parts.append("短期弱势 (MA5<MA10)")
                if sell_details.get("macd_bearish"):
                    reason_parts.append("MACD 死叉")
                if sell_details.get("rsi_overbought"):
                    reason_parts.append("RSI 超买")
                if sell_details.get("tech_negative"):
                    reason_parts.append("技术面消极")
                if sell_details.get("volume_down"):
                    reason_parts.append("成交量萎缩")
                reason_parts.append(f"卖分={signal['sell_score']:.2f}")
                reason_parts.append(f"RSI={signal['rsi']:.0f}")

            reason_parts.append(f"止损={signal['stop_distance']:.1%}")
            reason_parts.append(f"止盈={signal['take_profit_distance']:.1%}")

            reason = "; ".join(reason_parts)

            self.notification.send_signal(
                stock_code=signal["stock_code"],
                stock_name=signal["stock_name"],
                signal_type=signal["signal"].split("_")[-1] if "_" in signal["signal"] else signal["signal"],
                signal_score=signal.get("buy_score", 0),
                decision={
                    "strong_buy": "强烈买入",
                    "buy": "买入",
                    "sell": "卖出",
                    "strong_sell": "强烈卖出",
                    "hold": "持有",
                }.get(signal["signal"], signal["signal"]),
                price=signal["price"],
                reason=reason,
            )

        logger.info(f"已发送 {len(all_signals)} 个交易信号通知")

    def _send_monitor_summary(
        self,
        total_stocks: int,
        bullish_count: int,
        bearish_count: int,
        neutral_count: int,
        top_signals: List[Dict],
    ):
        """
        发送监控汇总到 webhook

        Args:
            total_stocks: 监控股票总数
            bullish_count: 看多数量
            bearish_count: 看空数量
            neutral_count: 中性数量
            top_signals: 重要信号列表
        """
        if not self.settings.notification_enabled:
            return

        # 检查是否配置了发送汇总
        if not self.settings.send_summary:
            logger.debug("监控汇总发送已禁用，跳过")
            return

        # 获取当前持仓
        positions = self.improved_strategy.get_all_positions()

        # 筛选重要信号（买入/卖出）
        important_signals = [
            r for r in top_signals
            if r["signal"] in ["buy", "strong_buy", "sell", "strong_sell"]
        ]

        # 发送汇总
        self.notification.send_market_summary(
            total_stocks=total_stocks,
            bullish_count=bullish_count,
            bearish_count=bearish_count,
            neutral_count=neutral_count,
            top_signals=important_signals[:10],
            positions=positions[:5],
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

    def _init_signal_fusion_default(self):
        """使用默认权重初始化信号融合引擎"""
        self.signal_fusion = SignalFusionEngine(
            news_weight=self.settings.news_weight,
            technical_weight=self.settings.technical_weight,
            fund_weight=self.settings.fund_weight,
            sentiment_weight=self.settings.sentiment_weight,
            market_regime="oscillating",  # 默认为震荡市
        )
        logger.info("信号融合引擎初始化成功（默认权重）")

    def _get_market_breadth(self) -> Dict:
        """
        获取市场宽度数据（涨跌家数）

        Returns:
            {up_count, down_count}
        """
        try:
            # 简化实现：返回默认值
            # 实际可以通过 akshare 获取真实数据
            return {"up_count": 2500, "down_count": 2000}
        except Exception as e:
            logger.error(f"获取市场宽度失败：{e}")
            return {"up_count": 2000, "down_count": 2000}


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
