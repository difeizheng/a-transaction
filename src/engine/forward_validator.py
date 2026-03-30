"""
前向验证统计模块 - Forward Validator

计算基于真实模拟交易记录的策略绩效指标，
与历史回测结果对比，判断策略是否具备实盘价值。

使用方式：
    from src.engine.forward_validator import ForwardValidator
    from src.utils.db import Database

    db = Database('data/trading.db')
    stats = ForwardValidator.compute(db)
    print(stats.to_dict())
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

# 历史回测基准（V3 策略）
BACKTEST_WIN_RATE   = 0.504
BACKTEST_SHARPE     = 1.08    # 回测夏普（若有）
BACKTEST_MAX_DD     = 0.12    # 回测最大回撤

# 预警阈值：实际胜率低于回测的 80% 时告警
WIN_RATE_WARN_RATIO = 0.80


@dataclass
class ForwardStats:
    """前向验证统计结果"""
    # 基础计数
    total_trades: int = 0
    win_trades: int = 0
    loss_trades: int = 0

    # 盈亏指标
    win_rate: float = 0.0
    avg_win: float = 0.0          # 平均每笔盈利金额
    avg_loss: float = 0.0         # 平均每笔亏损金额（正值）
    profit_loss_ratio: float = 0.0  # 盈亏比
    expectancy: float = 0.0       # 期望值（每笔平均收益，单位：元）
    total_pnl: float = 0.0        # 累计实现盈亏

    # 连续性
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    # 风险指标
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0

    # 持仓时长
    avg_holding_days: float = 0.0

    # 与回测对比
    win_rate_vs_backtest: float = 0.0   # 实际胜率 - 回测胜率
    is_underperforming: bool = False     # 是否显著低于回测

    # 样本充足性
    sufficient_sample: bool = False      # 是否有足够样本（>=20 笔）

    # 计算时间
    computed_at: str = ""

    def to_dict(self) -> Dict:
        return {
            "总交易次数": self.total_trades,
            "盈利次数": self.win_trades,
            "亏损次数": self.loss_trades,
            "实际胜率": f"{self.win_rate:.1%}",
            "回测胜率": f"{BACKTEST_WIN_RATE:.1%}",
            "胜率差异": f"{self.win_rate_vs_backtest:+.1%}",
            "平均盈利": f"{self.avg_win:.2f}",
            "平均亏损": f"{self.avg_loss:.2f}",
            "盈亏比": f"{self.profit_loss_ratio:.2f}",
            "期望值": f"{self.expectancy:.2f}",
            "累计盈亏": f"{self.total_pnl:.2f}",
            "最大连续盈利": self.max_consecutive_wins,
            "最大连续亏损": self.max_consecutive_losses,
            "最大回撤": f"{self.max_drawdown:.2%}",
            "夏普比率": f"{self.sharpe_ratio:.2f}",
            "平均持仓天数": f"{self.avg_holding_days:.1f}",
            "样本充足": "是" if self.sufficient_sample else "否（需>=20笔）",
            "是否跑输回测": "是（需关注）" if self.is_underperforming else "否",
            "统计时间": self.computed_at,
        }


class ForwardValidator:
    """前向验证统计器"""

    @staticmethod
    def compute(db) -> ForwardStats:
        """
        从数据库读取已平仓记录，计算完整的前向验证统计。

        Args:
            db: Database 实例

        Returns:
            ForwardStats
        """
        closed_trades = db.get_closed_trades()
        equity_curve = db.get_equity_curve(limit=1000)

        stats = ForwardStats(computed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        if not closed_trades:
            return stats

        stats.total_trades = len(closed_trades)
        stats.sufficient_sample = stats.total_trades >= 20

        # ── 盈亏计算 ────────────────────────────────────
        wins, losses = [], []
        for t in closed_trades:
            pnl = t.get("profit_loss") or 0.0
            if pnl > 0:
                wins.append(pnl)
            else:
                losses.append(abs(pnl))

        stats.win_trades = len(wins)
        stats.loss_trades = len(losses)
        stats.total_pnl = sum(wins) - sum(losses)

        stats.win_rate = stats.win_trades / stats.total_trades if stats.total_trades > 0 else 0.0
        stats.avg_win = sum(wins) / len(wins) if wins else 0.0
        stats.avg_loss = sum(losses) / len(losses) if losses else 0.0
        stats.profit_loss_ratio = stats.avg_win / stats.avg_loss if stats.avg_loss > 0 else 0.0

        # 期望值（每笔平均收益）
        stats.expectancy = (
            stats.win_rate * stats.avg_win
            - (1 - stats.win_rate) * stats.avg_loss
        )

        # ── 连续性分析 ──────────────────────────────────
        cur_win = cur_loss = 0
        max_win = max_loss = 0
        for t in sorted(closed_trades, key=lambda x: x.get("exit_date", "")):
            pnl = t.get("profit_loss") or 0.0
            if pnl > 0:
                cur_win += 1
                cur_loss = 0
                max_win = max(max_win, cur_win)
            else:
                cur_loss += 1
                cur_win = 0
                max_loss = max(max_loss, cur_loss)
        stats.max_consecutive_wins = max_win
        stats.max_consecutive_losses = max_loss

        # ── 平均持仓天数 ────────────────────────────────
        holding_days = []
        for t in closed_trades:
            try:
                entry = datetime.fromisoformat(t["entry_date"])
                exit_ = datetime.fromisoformat(t["exit_date"])
                holding_days.append((exit_ - entry).days)
            except Exception:
                pass
        stats.avg_holding_days = sum(holding_days) / len(holding_days) if holding_days else 0.0

        # ── 净值曲线指标（夏普、最大回撤）───────────────
        if len(equity_curve) >= 2:
            stats.max_drawdown = ForwardValidator._max_drawdown(equity_curve)
            stats.sharpe_ratio = ForwardValidator._sharpe(equity_curve)

        # ── 与回测对比 ──────────────────────────────────
        stats.win_rate_vs_backtest = stats.win_rate - BACKTEST_WIN_RATE
        stats.is_underperforming = (
            stats.sufficient_sample
            and stats.win_rate < BACKTEST_WIN_RATE * WIN_RATE_WARN_RATIO
        )

        return stats

    @staticmethod
    def _max_drawdown(equity_curve: List[Dict]) -> float:
        """计算净值曲线的最大回撤"""
        peak = -math.inf
        max_dd = 0.0
        for row in equity_curve:
            val = row.get("total_equity", 0)
            if val > peak:
                peak = val
            dd = (peak - val) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        return max_dd

    @staticmethod
    def _sharpe(equity_curve: List[Dict], risk_free_rate: float = 0.02) -> float:
        """
        基于净值曲线计算年化夏普比率。
        净值曲线按每 5 分钟一个快照，换算为日收益率时取每日末快照。
        """
        # 按日分组，取每日末净值
        daily: Dict[str, float] = {}
        for row in equity_curve:
            ts = row.get("timestamp", "")
            date_key = ts[:10] if ts else ""
            if date_key:
                daily[date_key] = row["total_equity"]

        if len(daily) < 2:
            return 0.0

        equity_list = [v for _, v in sorted(daily.items())]
        returns = [
            (equity_list[i] - equity_list[i - 1]) / equity_list[i - 1]
            for i in range(1, len(equity_list))
            if equity_list[i - 1] > 0
        ]
        if not returns:
            return 0.0

        n = len(returns)
        mean_r = sum(returns) / n
        variance = sum((r - mean_r) ** 2 for r in returns) / n
        std_r = math.sqrt(variance) if variance > 0 else 0.0

        if std_r == 0:
            return 0.0

        daily_rf = risk_free_rate / 252
        sharpe = (mean_r - daily_rf) / std_r * math.sqrt(252)
        return round(sharpe, 2)

    @staticmethod
    def warn_if_underperforming(stats: ForwardStats) -> Optional[str]:
        """
        检查策略是否显著跑输回测预期。

        Returns:
            告警文字（如有），否则 None
        """
        if not stats.sufficient_sample:
            return None
        if stats.is_underperforming:
            return (
                f"[策略预警] 前向胜率 {stats.win_rate:.1%} 显著低于回测 {BACKTEST_WIN_RATE:.1%}，"
                f"差异 {stats.win_rate_vs_backtest:+.1%}，请检查策略参数或市场环境变化"
            )
        return None
