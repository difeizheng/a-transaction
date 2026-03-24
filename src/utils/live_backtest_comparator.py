"""
实盘回测对比系统

功能：
1. 记录实盘交易数据
2. 对比回测与实盘差异
3. 分析滑点和冲击成本
4. 自动调整回测参数
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import json
from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class LiveTrade:
    """实盘交易记录"""
    code: str
    name: str
    action: str  # buy/sell
    quantity: int
    price: float
    timestamp: datetime
    commission: float = 0.0
    stamp_tax: float = 0.0
    slip_loss: float = 0.0  # 滑点损失
    reason: str = ""
    signal_score: float = 0.0
    expected_return: float = 0.0


@dataclass
class BacktestTrade:
    """回测交易记录"""
    code: str
    name: str
    action: str
    quantity: int
    price: float
    timestamp: datetime
    commission: float = 0.0
    signal_score: float = 0.0
    expected_return: float = 0.0


@dataclass
class ComparisonResult:
    """对比结果"""
    # 交易级别对比
    avg_slip_loss: float = 0.0        # 平均滑点损失
    avg_price_diff: float = 0.0       # 平均价格差异
    execution_rate: float = 0.0       # 执行率（实盘执行次数/回测信号次数）

    # 绩效对比
    live_return: float = 0.0          # 实盘收益率
    backtest_return: float = 0.0      # 回测收益率
    return_gap: float = 0.0           # 收益差距

    # 风险对比
    live_max_dd: float = 0.0          # 实盘最大回撤
    backtest_max_dd: float = 0.0      # 回测最大回撤
    dd_gap: float = 0.0               # 回撤差距

    # 调整建议
    suggested_slip: float = 0.0       # 建议滑点值
    suggested_commission: float = 0.0 # 建议手续费率
    confidence_score: float = 0.0     # 回测可信度


class LiveBacktestComparator:
    """
    实盘回测对比器

    功能：
    1. 记录实盘交易
    2. 对比回测与实盘
    3. 分析差异原因
    4. 调整回测参数
    """

    def __init__(self, data_dir: str = "data/live_compare"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.live_trades: List[LiveTrade] = []
        self.backtest_trades: List[BacktestTrade] = []

        # 实盘绩效
        self.live_capital = 0.0
        self.live_peak = 0.0
        self.live_max_dd = 0.0

        # 回测绩效
        self.backtest_capital = 0.0
        self.backtest_peak = 0.0
        self.backtest_max_dd = 0.0

        # 滑点统计
        self.slip_losses: List[float] = []
        self.price_diffs: List[float] = []

    def record_live_trade(self, trade: LiveTrade):
        """
        记录实盘交易

        Args:
            trade: 实盘交易记录
        """
        self.live_trades.append(trade)
        self._save_trades()

        # 计算滑点
        if trade.slip_loss > 0:
            self.slip_losses.append(trade.slip_loss)

        logger.info(f"记录实盘交易：{trade.code} {trade.action} {trade.quantity} @ {trade.price}")

    def record_backtest_trade(self, trade: BacktestTrade):
        """
        记录回测交易

        Args:
            trade: 回测交易记录
        """
        self.backtest_trades.append(trade)
        logger.info(f"记录回测交易：{trade.code} {trade.action} {trade.quantity} @ {trade.price}")

    def update_live_performance(
        self,
        current_capital: float,
        date: Optional[datetime] = None,
    ):
        """
        更新实盘绩效

        Args:
            current_capital: 当前资金
            date: 日期
        """
        self.live_capital = current_capital

        # 更新峰值
        if current_capital > self.live_peak:
            self.live_peak = current_capital

        # 计算回撤
        if self.live_peak > 0:
            current_dd = (self.live_peak - current_capital) / self.live_peak
            if current_dd > self.live_max_dd:
                self.live_max_dd = current_dd

        self._save_performance()

    def calculate_slip_loss(
        self,
        signal_price: float,
        execution_price: float,
        action: str,
    ) -> float:
        """
        计算滑点损失

        Args:
            signal_price: 信号价格
            execution_price: 执行价格
            action: buy/sell

        Returns:
            滑点损失比例
        """
        if action == "buy":
            # 买入时，执行价高于信号价为滑点损失
            slip = (execution_price - signal_price) / signal_price
        else:
            # 卖出时，执行价低于信号价为滑点损失
            slip = (signal_price - execution_price) / signal_price

        return max(0, slip)  # 滑点为非负

    def compare(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> ComparisonResult:
        """
        对比实盘与回测

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            对比结果
        """
        result = ComparisonResult()

        # 1. 交易级别对比
        if self.live_trades and self.backtest_trades:
            # 匹配同股票同时间的交易
            live_dict = {(t.code, t.timestamp.date()): t for t in self.live_trades}
            backtest_dict = {(t.code, t.timestamp.date()): t for t in self.backtest_trades}

            common_keys = set(live_dict.keys()) & set(backtest_dict.keys())

            if common_keys:
                price_diffs = []
                for key in common_keys:
                    live_trade = live_dict[key]
                    backtest_trade = backtest_dict[key]

                    # 价格差异
                    price_diff = abs(live_trade.price - backtest_trade.price) / backtest_trade.price
                    price_diffs.append(price_diff)

                    # 滑点
                    slip = self.calculate_slip_loss(
                        backtest_trade.price,
                        live_trade.price,
                        live_trade.action,
                    )
                    self.price_diffs.append(price_diff)

                result.avg_slip_loss = np.mean(self.slip_losses) if self.slip_losses else 0
                result.avg_price_diff = np.mean(price_diffs) if price_diffs else 0

            # 执行率
            result.execution_rate = len(self.live_trades) / max(1, len(self.backtest_trades))

        # 2. 绩效对比
        result.live_return = (self.live_capital - self.live_peak) / self.live_peak if self.live_peak > 0 else 0
        result.backtest_return = (self.backtest_capital - self.backtest_peak) / self.backtest_peak if self.backtest_peak > 0 else 0
        result.return_gap = result.backtest_return - result.live_return

        # 3. 风险对比
        result.live_max_dd = self.live_max_dd
        result.backtest_max_dd = self.backtest_max_dd
        result.dd_gap = result.backtest_max_dd - self.live_max_dd

        # 4. 调整建议
        # 建议滑点 = 平均滑点 + 1 倍标准差
        if self.slip_losses:
            result.suggested_slip = np.mean(self.slip_losses) + np.std(self.slip_losses)
        else:
            result.suggested_slip = 0.002  # 默认 0.2%

        result.suggested_commission = 0.0003  # 万三

        # 5. 回测可信度
        # 基于执行率、滑点、回撤差距计算
        confidence_factors = []

        # 执行率高，可信度高
        confidence_factors.append(min(1.0, result.execution_rate))

        # 滑点小，可信度高
        slip_score = 1 - min(1, result.avg_slip_loss * 100)
        confidence_factors.append(slip_score)

        # 回撤差距小，可信度高
        dd_score = 1 - min(1, abs(result.dd_gap) * 5)
        confidence_factors.append(dd_score)

        result.confidence_score = np.mean(confidence_factors)

        return result

    def get_adjustment_suggestions(self) -> Dict:
        """
        获取回测参数调整建议

        Returns:
            调整建议字典
        """
        result = self.compare()

        suggestions = {
            "slip_adjustment": result.suggested_slip,
            "commission_adjustment": result.suggested_commission,
            "impact_cost": result.avg_price_diff,
            "execution_rate": result.execution_rate,
            "reliability": result.confidence_score,
        }

        # 解释
        explanations = []

        if result.avg_slip_loss > 0.005:
            explanations.append(f"滑点偏高 ({result.avg_slip_loss:.2%})，建议增加回测滑点参数")

        if result.execution_rate < 0.8:
            explanations.append(f"执行率偏低 ({result.execution_rate:.0%})，可能存在信号滞后")

        if result.dd_gap > 0.05:
            explanations.append(f"实盘回撤大于回测 ({result.dd_gap:.1%})，注意风险控制")

        suggestions["explanations"] = explanations

        return suggestions

    def _save_trades(self):
        """保存交易记录"""
        trade_file = self.data_dir / "live_trades.json"

        data = []
        for t in self.live_trades:
            data.append({
                "code": t.code,
                "name": t.name,
                "action": t.action,
                "quantity": t.quantity,
                "price": t.price,
                "timestamp": t.timestamp.isoformat(),
                "commission": t.commission,
                "stamp_tax": t.stamp_tax,
                "slip_loss": t.slip_loss,
                "reason": t.reason,
            })

        with open(trade_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _save_performance(self):
        """保存绩效数据"""
        perf_file = self.data_dir / "performance.json"

        data = {
            "live_capital": self.live_capital,
            "live_peak": self.live_peak,
            "live_max_dd": self.live_max_dd,
            "live_trade_count": len(self.live_trades),
            "update_time": datetime.now().isoformat(),
        }

        with open(perf_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_history(self):
        """加载历史数据"""
        trade_file = self.data_dir / "live_trades.json"

        if trade_file.exists():
            with open(trade_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.live_trades = [
                LiveTrade(
                    code=t["code"],
                    name=t["name"],
                    action=t["action"],
                    quantity=t["quantity"],
                    price=t["price"],
                    timestamp=datetime.fromisoformat(t["timestamp"]),
                    commission=t.get("commission", 0),
                    stamp_tax=t.get("stamp_tax", 0),
                    slip_loss=t.get("slip_loss", 0),
                    reason=t.get("reason", ""),
                )
                for t in data
            ]

            logger.info(f"加载历史交易记录：{len(self.live_trades)} 条")

        perf_file = self.data_dir / "performance.json"
        if perf_file.exists():
            with open(perf_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.live_capital = data.get("live_capital", 0)
            self.live_peak = data.get("live_peak", 0)
            self.live_max_dd = data.get("live_max_dd", 0)

            logger.info(f"加载绩效数据：当前资金 {self.live_capital:.2f}")

    def export_report(self, output_path: str) -> str:
        """
        导出对比报告

        Args:
            output_path: 输出路径

        Returns:
            报告内容
        """
        result = self.compare()
        suggestions = self.get_adjustment_suggestions()

        report = []
        report.append("=" * 60)
        report.append("实盘回测对比报告")
        report.append("=" * 60)
        report.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")

        report.append("【交易对比】")
        report.append(f"  实盘交易数：{len(self.live_trades)}")
        report.append(f"  回测交易数：{len(self.backtest_trades)}")
        report.append(f"  执行率：{result.execution_rate:.1%}")
        report.append(f"  平均滑点：{result.avg_slip_loss:.2%}")
        report.append(f"  平均价格差异：{result.avg_price_diff:.2%}")
        report.append("")

        report.append("【绩效对比】")
        report.append(f"  实盘收益率：{result.live_return:.2%}")
        report.append(f"  回测收益率：{result.backtest_return:.2%}")
        report.append(f"  收益差距：{result.return_gap:.2%}")
        report.append("")

        report.append("【风险对比】")
        report.append(f"  实盘最大回撤：{result.live_max_dd:.2%}")
        report.append(f"  回测最大回撤：{result.backtest_max_dd:.2%}")
        report.append(f"  回撤差距：{result.dd_gap:.2%}")
        report.append("")

        report.append("【调整建议】")
        report.append(f"  建议滑点：{result.suggested_slip:.2%}")
        report.append(f"  建议手续费：{result.suggested_commission:.2%}")
        report.append(f"  回测可信度：{result.confidence_score:.1%}")
        report.append("")

        if suggestions["explanations"]:
            report.append("【说明】")
            for exp in suggestions["explanations"]:
                report.append(f"  - {exp}")

        report_content = "\n".join(report)

        # 保存到文件
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report_content)
            logger.info(f"报告已保存到：{output_path}")

        return report_content


# 装饰器：自动记录实盘交易
def record_trade(comparator: LiveBacktestComparator):
    """
    交易记录装饰器

    用法:
        @record_trade(comparator)
        def execute_trade(...):
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # 执行前
            result = func(*args, **kwargs)

            # 执行后记录
            if result:
                comparator.record_live_trade(LiveTrade(
                    code=result.get("code", ""),
                    name=result.get("name", ""),
                    action=result.get("action", ""),
                    quantity=result.get("quantity", 0),
                    price=result.get("price", 0),
                    timestamp=datetime.now(),
                    commission=result.get("commission", 0),
                    slip_loss=result.get("slip_loss", 0),
                    reason=result.get("reason", ""),
                ))

            return result
        return wrapper
    return decorator
