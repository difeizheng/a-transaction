"""
V4 深度优化策略回测 - 验证新股票池和深度优化策略

股票池：
- 000948 南天信息
- 601360 三六零
- 300459 汤姆猫
- 002714 牧原股份
- 600036 招商银行
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))

from src.collectors.price_collector import PriceCollector
from src.strategy.v4_strategy import V4Strategy
from src.engine.backtest import Trade, BacktestResult
import pandas as pd
import numpy as np


STOCK_CODES = ["000948", "601360", "300459", "002714", "600036"]
STOCK_NAMES = {
    "000948": "南天信息",
    "601360": "三六零",
    "300459": "汤姆猫",
    "002714": "牧原股份",
    "600036": "招商银行",
}


def run_v4_backtest():
    """运行 V4 深度优化策略回测"""
    print("=" * 60)
    print("V4 深度优化策略回测 - 新股票池验证")
    print("=" * 60)

    # 配置
    INITIAL_CAPITAL = 100000
    DAYS = 120

    collector = PriceCollector()
    strategy = V4Strategy()

    print(f"\n初始资金：{INITIAL_CAPITAL:,.2f} 元")
    print(f"股票池：{STOCK_CODES}")
    print(f"数据周期：{DAYS} 天")
    print("-" * 60)

    # 获取数据并生成信号
    price_data = {}
    all_signals = []

    for code in STOCK_CODES:
        try:
            df = collector.get_kline(code, period="daily", limit=DAYS)
            if df is None or df.empty:
                print(f"[ERR] {code}: 无法获取数据")
                continue

            price_data[code] = df
            print(f"[OK] {code}: 获取到 {len(df)} 条数据")

            # 使用 V4 策略生成信号
            signals = strategy.generate_signals(df, code)
            all_signals.extend(signals)

        except Exception as e:
            print(f"[ERR] {code}: 错误 - {e}")

    # 信号统计
    signal_types = {}
    for s in all_signals:
        sig = s.get("signal", "hold")
        signal_types[sig] = signal_types.get(sig, 0) + 1

    print(f"\n生成信号总数：{len(all_signals)}")
    print("信号类型统计:")
    for sig, count in sorted(signal_types.items()):
        print(f"  {sig}: {count}")
    print("-" * 60)

    if not all_signals:
        print("[ERR] 没有生成任何信号")
        return

    # 运行回测
    result = run_v4_backtest_execution(price_data, all_signals, INITIAL_CAPITAL, strategy)

    # 输出结果
    print_v4_result(result)


def run_v4_backtest_execution(price_data, signals, initial_capital, strategy):
    """V4 策略执行逻辑"""
    from src.engine.backtest import Trade, BacktestResult

    capital = initial_capital
    positions = {}
    trades = []
    equity_curve = [capital]

    # 按时间排序
    signals_sorted = sorted(signals, key=lambda x: x.get("timestamp", datetime.now()))

    for signal in signals_sorted:
        code = signal["stock_code"]
        signal_type = signal.get("signal", "hold")
        timestamp = signal.get("timestamp", datetime.now())
        price = signal.get("price", 0)

        if code not in price_data or price <= 0:
            continue

        # === 买入执行 ===
        if signal_type in ["buy", "strong_buy", "weak_buy"] and code not in positions:
            position_ratio = signal.get("position_ratio", 0.15)
            quantity = int(capital * position_ratio / price / 100) * 100

            if quantity > 0:
                cost = quantity * price * 1.004
                if cost <= capital:
                    capital -= cost
                    stop_dist = signal.get("stop_distance", 0.08)
                    stop_price = price * (1 - stop_dist)
                    take_profit = price * (1 + stop_dist * 2.5)

                    positions[code] = {
                        "quantity": quantity,
                        "avg_cost": price,
                        "entry_time": timestamp,
                        "stop_price": stop_price,
                        "take_profit": take_profit,
                        "highest_price": price,
                    }

        # === 卖出执行 ===
        elif signal_type == "sell" and code in positions:
            pos = positions[code]
            sale_value = pos["quantity"] * price * 0.996
            capital += sale_value

            pnl = (price - pos["avg_cost"]) * pos["quantity"]
            pnl_pct = (price - pos["avg_cost"]) / pos["avg_cost"]

            trades.append(Trade(
                stock_code=code,
                stock_name=STOCK_NAMES.get(code, ""),
                entry_price=pos["avg_cost"],
                exit_price=price,
                quantity=pos["quantity"],
                entry_time=pos["entry_time"],
                exit_time=timestamp,
                direction="long",
                pnl=pnl,
                pnl_pct=pnl_pct,
                exit_reason="信号",
            ))

            # 记录卖出时间（用于冷却期）
            strategy.record_sell(code, timestamp)
            del positions[code]

        # === 持仓管理 ===
        for code_held, pos in list(positions.items()):
            if code_held in price_data:
                if price > pos["highest_price"]:
                    pos["highest_price"] = price
                    stop_dist = signal.get("stop_distance", 0.08)
                    new_stop = price * (1 - stop_dist)
                    if new_stop > pos["stop_price"]:
                        pos["stop_price"] = new_stop

                # 检查止损/止盈
                if price <= pos["stop_price"]:
                    sale_value = pos["quantity"] * pos["stop_price"] * 0.996
                    capital += sale_value
                    pnl = (pos["stop_price"] - pos["avg_cost"]) * pos["quantity"]
                    pnl_pct = (pos["stop_price"] - pos["avg_cost"]) / pos["avg_cost"]

                    trades.append(Trade(
                        stock_code=code_held,
                        stock_name=STOCK_NAMES.get(code_held, ""),
                        entry_price=pos["avg_cost"],
                        exit_price=pos["stop_price"],
                        quantity=pos["quantity"],
                        entry_time=pos["entry_time"],
                        exit_time=timestamp,
                        direction="long",
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        exit_reason="动态止损",
                    ))
                    del positions[code_held]

                elif price >= pos["take_profit"]:
                    sale_value = pos["quantity"] * pos["take_profit"] * 0.996
                    capital += sale_value
                    pnl = (pos["take_profit"] - pos["avg_cost"]) * pos["quantity"]
                    pnl_pct = (pos["take_profit"] - pos["avg_cost"]) / pos["avg_cost"]

                    trades.append(Trade(
                        stock_code=code_held,
                        stock_name=STOCK_NAMES.get(code_held, ""),
                        entry_price=pos["avg_cost"],
                        exit_price=pos["take_profit"],
                        quantity=pos["quantity"],
                        entry_time=pos["entry_time"],
                        exit_time=timestamp,
                        direction="long",
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        exit_reason="止盈",
                    ))
                    del positions[code_held]

        # 更新资金曲线
        equity = capital
        for code_held, pos in positions.items():
            if code_held in price_data:
                equity += pos["quantity"] * price
        equity_curve.append(equity)

    # 强制平仓
    for code, pos in positions.items():
        if code in price_data:
            df = price_data[code]
            final_price = float(df["close"].iloc[-1])
            sale_value = pos["quantity"] * final_price * 0.996
            capital += sale_value
            pnl = (final_price - pos["avg_cost"]) * pos["quantity"]
            pnl_pct = (final_price - pos["avg_cost"]) / pos["avg_cost"]

            trades.append(Trade(
                stock_code=code,
                stock_name=STOCK_NAMES.get(code, ""),
                entry_price=pos["avg_cost"],
                exit_price=final_price,
                quantity=pos["quantity"],
                entry_time=pos["entry_time"],
                exit_time=signals_sorted[-1]["timestamp"] if signals_sorted else datetime.now(),
                direction="long",
                pnl=pnl,
                pnl_pct=pnl_pct,
                exit_reason="平仓",
            ))

    final_capital = capital

    # 计算指标
    start_date = signals_sorted[0]["timestamp"] if signals_sorted else datetime.now()
    end_date = signals_sorted[-1]["timestamp"] if signals_sorted else datetime.now()
    days = max(1, (end_date - start_date).days)

    total_return = (final_capital - initial_capital) / initial_capital
    annual_return = (1 + total_return) ** (365 / days) - 1 if days > 0 else 0

    winning = [t for t in trades if t.pnl > 0]
    losing = [t for t in trades if t.pnl <= 0]
    win_rate = len(winning) / len(trades) if trades else 0

    avg_win = np.mean([t.pnl_pct for t in winning]) if winning else 0
    avg_loss = abs(np.mean([t.pnl_pct for t in losing])) if losing else 0
    profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0

    max_dd = 0
    peak = equity_curve[0]
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak
        if dd > max_dd:
            max_dd = dd

    if len(equity_curve) > 1:
        returns = pd.Series(equity_curve).pct_change().dropna()
        volatility = returns.std() * np.sqrt(252) if len(returns) > 1 else 0.01
        sharpe = (annual_return - 0.02) / volatility if volatility > 0 else 0
    else:
        sharpe = 0

    result = BacktestResult(
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        final_capital=final_capital,
        total_return=total_return,
        annual_return=annual_return,
        total_trades=len(trades),
        winning_trades=len(winning),
        losing_trades=len(losing),
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        profit_loss_ratio=profit_loss_ratio,
        max_drawdown=max_dd,
        sharpe_ratio=sharpe,
        trade_details=trades,
    )

    return result


def print_v4_result(result: BacktestResult):
    """打印 V4 回测结果"""
    print("\n" + "=" * 60)
    print("V4 策略回测结果")
    print("=" * 60)

    print("\n【盈利指标】")
    print(f"  初始资金：     {result.initial_capital:>12,.2f} 元")
    print(f"  最终资金：     {result.final_capital:>12,.2f} 元")
    print(f"  总收益率：     {result.total_return:>12.2%}")
    print(f"  年化收益率：   {result.annual_return:>12.2%}")

    print("\n【交易统计】")
    print(f"  总交易次数：   {result.total_trades:>12} 笔")
    print(f"  盈利次数：     {result.winning_trades:>12} 笔")
    print(f"  亏损次数：     {result.losing_trades:>12} 笔")
    print(f"  胜率：         {result.win_rate:>12.1%}")

    if result.winning_trades > 0:
        print(f"  平均盈利：     {result.avg_win:>12.2%}")
    if result.losing_trades > 0:
        print(f"  平均亏损：     {result.avg_loss:>12.2%}")
    print(f"  盈亏比：       {result.profit_loss_ratio:>12.2f}")

    print("\n【风险指标】")
    print(f"  最大回撤：     {result.max_drawdown:>12.2%}")
    print(f"  夏普比率：     {result.sharpe_ratio:>12.2f}")

    print("\n" + "=" * 60)
    print("评估结论")
    print("=" * 60)

    passed = []
    failed = []

    if result.win_rate >= 0.45:
        passed.append(f"胜率达标 ({result.win_rate:.1%})")
    else:
        failed.append(f"胜率偏低 ({result.win_rate:.1%} < 45%)")

    if result.profit_loss_ratio >= 1.5:
        passed.append(f"盈亏比优秀 ({result.profit_loss_ratio:.2f})")
    elif result.profit_loss_ratio >= 1.0:
        passed.append(f"盈亏比合格 ({result.profit_loss_ratio:.2f})")
    else:
        failed.append(f"盈亏比偏低 ({result.profit_loss_ratio:.2f} < 1.0)")

    if result.total_return > 0:
        passed.append(f"实现盈利 (+{result.total_return:.2%})")
    else:
        failed.append(f"出现亏损 ({result.total_return:.2%})")

    if result.max_drawdown < 0.15:
        passed.append(f"回撤控制好 ({result.max_drawdown:.1%})")
    else:
        failed.append(f"回撤过大 ({result.max_drawdown:.1%} > 15%)")

    if result.sharpe_ratio > 1:
        passed.append(f"夏普比率优秀 ({result.sharpe_ratio:.2f})")
    elif result.sharpe_ratio > 0:
        passed.append(f"夏普比率正数 ({result.sharpe_ratio:.2f})")
    else:
        failed.append(f"夏普比率负数 ({result.sharpe_ratio:.2f})")

    if passed:
        print("\n[通过项]")
        for p in passed:
            print(f"  [OK] {p}")

    if failed:
        print("\n[需改进项]")
        for f in failed:
            print(f"  [!] {f}")

    print("\n" + "=" * 60)
    if result.total_return > 0 and result.win_rate >= 0.4 and result.profit_loss_ratio >= 1.0:
        print("【结论】V4 策略实现稳定盈利！")
    elif result.total_return > 0:
        print("【结论】V4 策略盈利，指标有待优化")
    else:
        print("【结论】V4 策略尚未实现稳定盈利，需继续优化")
    print("=" * 60)

    if result.trade_details:
        print(f"\n交易明细 (共 {len(result.trade_details)} 笔):")
        print(f"  {'股票':<10} {'入场价':>8} {'出场价':>8} {'盈亏':>10} {'盈亏率':>10} {'原因':>10}")
        print("  " + "-" * 65)
        for t in result.trade_details:
            reason_short = t.exit_reason[:10] if t.exit_reason else ""
            print(f"  {t.stock_code:<10} {t.entry_price:>8.2f} {t.exit_price:>8.2f} "
                  f"{t.pnl:>10.2f} {t.pnl_pct:>10.2%} {reason_short:>10}")

    print("\n" + "=" * 60)
    print("免责声明：回测结果仅供参考，不构成投资建议")
    print("=" * 60)


if __name__ == "__main__":
    run_v4_backtest()
