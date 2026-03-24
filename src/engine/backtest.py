"""
回测评估模块 - 评估交易系统盈利能力
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import pandas as pd
import numpy as np

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Trade:
    """交易记录"""
    stock_code: str
    stock_name: str
    entry_price: float
    exit_price: float
    quantity: int
    entry_time: datetime
    exit_time: datetime
    direction: str  # long/short
    pnl: float = 0.0
    pnl_pct: float = 0.0
    exit_reason: str = ""  # stop_loss/take_profit/signal

    def __post_init__(self):
        """计算盈亏"""
        if self.direction == "long":
            self.pnl = (self.exit_price - self.entry_price) * self.quantity
            self.pnl_pct = (self.exit_price - self.entry_price) / self.entry_price
        else:
            self.pnl = (self.entry_price - self.exit_price) * self.quantity
            self.pnl_pct = (self.entry_price - self.exit_price) / self.entry_price


@dataclass
class BacktestResult:
    """回测结果"""
    # 基本信息
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float

    # 盈利指标
    total_return: float = 0.0
    annual_return: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_loss_ratio: float = 0.0
    expectancy: float = 0.0

    # 风险指标
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0  # 最大回撤持续期数
    volatility: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    # 交易质量
    avg_holding_period: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    # 资金曲线
    equity_curve: List[float] = field(default_factory=list)
    trade_details: List[Trade] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "回测区间": f"{self.start_date.strftime('%Y-%m-%d')} ~ {self.end_date.strftime('%Y-%m-%d')}",
            "初始资金": f"{self.initial_capital:,.2f}",
            "最终资金": f"{self.final_capital:,.2f}",
            "总收益率": f"{self.total_return:.2%}",
            "年化收益率": f"{self.annual_return:.2%}",
            "总交易次数": self.total_trades,
            "胜率": f"{self.win_rate:.2%}",
            "盈亏比": f"{self.profit_loss_ratio:.2f}",
            "期望值": f"{self.expectancy:.4f}",
            "最大回撤": f"{self.max_drawdown:.2%}",
            "夏普比率": f"{self.sharpe_ratio:.2f}",
            "索提诺比率": f"{self.sortino_ratio:.2f}",
            "卡玛比率": f"{self.calmar_ratio:.2f}",
            "平均持仓期 (天)": f"{self.avg_holding_period:.1f}",
            "最大连续盈利": self.max_consecutive_wins,
            "最大连续亏损": self.max_consecutive_losses,
        }


class BacktestEngine:
    """
    回测引擎

    功能：
    - 历史数据回测
    - 绩效指标计算
    - 风险评估
    """

    def __init__(
        self,
        initial_capital: float = 100000.0,
        commission_rate: float = 0.0003,  # 万三
        slippage: float = 0.001,  # 滑点 0.1%
        risk_free_rate: float = 0.02,  # 无风险利率 2%
    ):
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage = slippage
        self.risk_free_rate = risk_free_rate

    def run(
        self,
        price_data: Dict[str, pd.DataFrame],  # {stock_code: DataFrame}
        signals: List[Dict],  # 信号列表
        decision_engine,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> BacktestResult:
        """
        运行回测

        Args:
            price_data: 价格数据字典
            signals: 信号列表，每个包含 stock_code, signal, timestamp
            decision_engine: 决策引擎实例
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            回测结果
        """
        # 初始化状态
        capital = self.initial_capital
        positions: Dict[str, Dict] = {}  # {stock_code: {quantity, avg_cost, entry_time}}
        trades: List[Trade] = []
        equity_curve: [float] = [capital]

        # 按时间排序信号
        signals_sorted = sorted(signals, key=lambda x: x.get("timestamp", datetime.now()))

        for signal in signals_sorted:
            stock_code = signal.get("stock_code")
            signal_type = signal.get("signal")
            timestamp = signal.get("timestamp")
            current_price = signal.get("price", 0)

            if stock_code not in price_data:
                continue

            df = price_data[stock_code]

            # 执行决策
            if signal_type in ["buy", "strong_buy"] and stock_code not in positions:
                # 买入
                quantity = int(capital * 0.2 / current_price / 100) * 100  # 20% 仓位，100 股整数倍
                if quantity > 0:
                    cost = quantity * current_price * (1 + self.commission_rate + self.slippage)
                    if cost <= capital:
                        capital -= cost
                        positions[stock_code] = {
                            "quantity": quantity,
                            "avg_cost": current_price,
                            "entry_time": timestamp,
                        }

            elif signal_type in ["sell", "strong_sell"] and stock_code in positions:
                # 卖出
                pos = positions[stock_code]
                sale_value = pos["quantity"] * current_price * (1 - self.commission_rate - self.slippage)
                capital += sale_value

                # 记录交易
                trade = Trade(
                    stock_code=stock_code,
                    stock_name="",
                    entry_price=pos["avg_cost"],
                    exit_price=current_price,
                    quantity=pos["quantity"],
                    entry_time=pos["entry_time"],
                    exit_time=timestamp,
                    direction="long",
                    exit_reason="signal",
                )
                trades.append(trade)
                del positions[stock_code]

        # 计算最终资金（包括未平仓头寸）
        final_capital = capital
        for stock_code, pos in positions.items():
            if stock_code in price_data:
                last_price = price_data[stock_code]["close"].iloc[-1]
                final_capital += pos["quantity"] * last_price

        # 计算绩效指标
        result = self._calculate_metrics(
            initial_capital=self.initial_capital,
            final_capital=final_capital,
            trades=trades,
            equity_curve=equity_curve,
            start_date=start_date or datetime.now(),
            end_date=end_date or datetime.now(),
        )
        result.trade_details = trades

        return result

    def _calculate_metrics(
        self,
        initial_capital: float,
        final_capital: float,
        trades: List[Trade],
        equity_curve: List[float],
        start_date: datetime,
        end_date: datetime,
    ) -> BacktestResult:
        """计算回测指标"""
        result = BacktestResult(
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            final_capital=final_capital,
        )

        # 总收益率
        result.total_return = (final_capital - initial_capital) / initial_capital

        # 年化收益率
        days = (end_date - start_date).days
        if days > 0:
            result.annual_return = (1 + result.total_return) ** (365 / days) - 1

        # 交易统计
        result.total_trades = len(trades)
        if trades:
            winning = [t for t in trades if t.pnl > 0]
            losing = [t for t in trades if t.pnl <= 0]
            result.winning_trades = len(winning)
            result.losing_trades = len(losing)
            result.win_rate = result.winning_trades / result.total_trades

            if winning:
                result.avg_win = np.mean([t.pnl_pct for t in winning])
            if losing:
                result.avg_loss = abs(np.mean([t.pnl_pct for t in losing]))

            # 盈亏比
            if result.avg_loss > 0:
                result.profit_loss_ratio = result.avg_win / result.avg_loss

            # 期望值
            result.expectancy = (
                result.win_rate * result.avg_win -
                (1 - result.win_rate) * result.avg_loss
            )

            # 平均持仓期
            holding_periods = [(t.exit_time - t.entry_time).days for t in trades]
            result.avg_holding_period = np.mean(holding_periods)

            # 最大连续盈利/亏损
            result.max_consecutive_wins = self._max_consecutive(trades, win=True)
            result.max_consecutive_losses = self._max_consecutive(trades, win=False)

        # 风险指标（需要完整的资金曲线）
        if len(equity_curve) > 1:
            returns = pd.Series(equity_curve).pct_change().dropna()
            result.volatility = returns.std() * np.sqrt(252)

            # 夏普比率
            if result.volatility > 0:
                result.sharpe_ratio = (result.annual_return - self.risk_free_rate) / result.volatility

            # 索提诺比率（只考虑下行波动）
            downside_returns = returns[returns < 0]
            if len(downside_returns) > 0:
                downside_deviation = downside_returns.std() * np.sqrt(252)
                if downside_deviation > 0:
                    result.sortino_ratio = (result.annual_return - self.risk_free_rate) / downside_deviation

        # 最大回撤
        if len(equity_curve) > 1:
            result.max_drawdown, result.max_drawdown_duration = self._calc_max_drawdown(equity_curve)

        # 卡玛比率
        if result.max_drawdown > 0:
            result.calmar_ratio = result.annual_return / result.max_drawdown

        return result

    def _calc_max_drawdown(self, equity_curve: List[float]) -> Tuple[float, int]:
        """计算最大回撤"""
        peak = equity_curve[0]
        max_dd = 0.0
        max_duration = 0
        current_duration = 0

        for equity in equity_curve:
            if equity > peak:
                peak = equity
                current_duration = 0
            else:
                dd = (peak - equity) / peak
                if dd > max_dd:
                    max_dd = dd
                current_duration += 1
                if current_duration > max_duration:
                    max_duration = current_duration

        return max_dd, max_duration

    def _max_consecutive(self, trades: List[Trade], win: bool) -> int:
        """计算最大连续盈利/亏损"""
        if not trades:
            return 0

        max_count = 0
        current_count = 0

        for trade in trades:
            is_win = trade.pnl > 0
            if is_win == win:
                current_count += 1
                max_count = max(max_count, current_count)
            else:
                current_count = 0

        return max_count


def evaluate_system(trades: List[Trade], initial_capital: float) -> Dict:
    """
    评估交易系统

    Args:
        trades: 交易记录列表
        initial_capital: 初始资金

    Returns:
        评估指标字典
    """
    if not trades:
        return {"error": "无交易记录"}

    engine = BacktestEngine(initial_capital=initial_capital)
    equity_curve = [initial_capital]

    for trade in trades:
        equity_curve.append(equity_curve[-1] + trade.pnl)

    result = engine._calculate_metrics(
        initial_capital=initial_capital,
        final_capital=equity_curve[-1],
        trades=trades,
        equity_curve=equity_curve,
        start_date=min(t.entry_time for t in trades),
        end_date=max(t.exit_time for t in trades),
    )

    return result.to_dict()


__all__ = ["BacktestEngine", "BacktestResult", "Trade", "evaluate_system"]
