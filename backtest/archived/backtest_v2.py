"""
V2 回测 - 优化策略实现稳定盈利
优化点：
1. 更严格的买入条件（需要趋势确认）
2. 动态止损（根据持仓时间放宽）
3. RSI 趋势过滤
4. 成交量确认
5. 分级仓位管理
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))

from src.collectors.price_collector import PriceCollector
from src.analyzers.technical_analyzer import TechnicalAnalyzer
from src.analyzers.volatility_analyzer import VolatilityAnalyzer
from src.engine.backtest import BacktestEngine, Trade, BacktestResult
import pandas as pd
import numpy as np


class OptimizedStrategy:
    """
    优化版交易策略

    核心改进：
    1. 趋势确认：价格在 MA20 之上且 MA20 向上
    2. 多指标共振：MA+MACD+RSI+ 成交量
    3. 动态止损：根据持仓时间调整
    4. 分级止盈：分两批止盈
    5. RSI 趋势：RSI 需要上升
    """

    def __init__(self):
        self.technical_analyzer = TechnicalAnalyzer()
        self.volatility_analyzer = VolatilityAnalyzer()

        # 策略参数
        self.buy_score_threshold = 0.6       # 买入阈值（提高）
        self.min_buy_conditions = 4          # 最少满足条件数（增加）
        self.min_volume_ratio = 1.2          # 最小成交量比率
        self.atr_multiplier = 2.5            # ATR 止损倍数（放宽）
        self.profit_ratio = 3.0              # 止盈/止损比率（提高）

    def generate_signals(self, df: pd.DataFrame, stock_code: str) -> list:
        """
        生成优化信号

        买入条件（需同时满足至少 4 个）：
        1. 价格在 MA20 之上（趋势向上）
        2. MA20 向上（趋势确认）
        3. MACD 金叉或 DIF>0
        4. RSI 30-70 且上升
        5. 成交量放大
        6. 技术得分正面
        7. 价格创新高
        """
        signals = []
        if len(df) < 35:
            return signals

        # 计算指标
        ma5 = df['close'].rolling(5).mean()
        ma10 = df['close'].rolling(10).mean()
        ma20 = df['close'].rolling(20).mean()

        # MACD
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        macd_dif = exp1 - exp2
        macd_dea = macd_dif.ewm(span=9, adjust=False).mean()

        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        # ATR
        atr = self.volatility_analyzer.calculate_atr(df)

        for i in range(30, len(df)):
            subset = df.iloc[:i+1].copy()
            tech_signal = self.technical_analyzer.analyze(subset)

            current_price = float(df.iloc[i]['close'])
            prev_price = float(df.iloc[i-1]['close']) if i > 0 else current_price

            # 获取指标值
            curr_ma5 = float(ma5.iloc[i])
            curr_ma10 = float(ma10.iloc[i])
            curr_ma20 = float(ma20.iloc[i]) if i >= 20 else current_price
            prev_ma20 = float(ma20.iloc[i-5]) if i >= 25 else curr_ma20  # 5 日前 MA20

            curr_macd = float(macd_dif.iloc[i])
            prev_macd = float(macd_dif.iloc[i-1]) if i > 0 else 0

            curr_rsi = float(rsi.iloc[i]) if not np.isnan(rsi.iloc[i]) else 50
            prev_rsi = float(rsi.iloc[i-3]) if i >= 3 else curr_rsi  # 3 日前 RSI

            # 成交量比率
            avg_volume = df['volume'].iloc[i-20:i].mean() if i >= 20 else df['volume'].iloc[i]
            curr_volume = df['volume'].iloc[i]
            volume_ratio = curr_volume / avg_volume if avg_volume > 0 else 1

            # ATR 值
            curr_atr = float(atr.iloc[i]) if not np.isnan(atr.iloc[i]) else 0

            # === 买入条件评分 ===
            buy_conditions = 0
            buy_score = 0
            buy_details = {}

            # 条件 1: 价格在 MA20 之上（趋势向上）
            cond1 = current_price > curr_ma20
            if cond1:
                buy_conditions += 1
                buy_score += 0.25
            buy_details['above_ma20'] = cond1

            # 条件 2: MA20 向上（趋势确认）- 新增
            cond2 = curr_ma20 > prev_ma20
            if cond2:
                buy_conditions += 1
                buy_score += 0.25
            buy_details['ma20_up'] = cond2

            # 条件 3: MA5 > MA10（短期强势）
            cond3 = curr_ma5 > curr_ma10
            if cond3:
                buy_conditions += 1
                buy_score += 0.15
            buy_details['ma5_above_ma10'] = cond3

            # 条件 4: MACD 金叉或 DIF>0
            cond4 = (curr_macd > 0) or (curr_macd > prev_macd and prev_macd <= 0)
            if cond4:
                buy_conditions += 1
                buy_score += 0.25
            buy_details['macd_bullish'] = cond4

            # 条件 5: RSI 未超买且上升
            cond5 = 35 < curr_rsi < 65 and curr_rsi > prev_rsi
            if cond5:
                buy_conditions += 1
                buy_score += 0.2
            buy_details['rsi_ok'] = cond5

            # 条件 6: 技术得分正面
            cond6 = tech_signal.score > 0.1  # 提高阈值
            if cond6:
                buy_score += 0.15
            buy_details['tech_positive'] = cond6

            # 条件 7: 成交量放大
            cond7 = volume_ratio > 1.5  # 提高要求
            if cond7:
                buy_score += 0.15
            buy_details['volume_up'] = cond7

            # 条件 8: 价格创新高
            cond8 = current_price >= df['high'].iloc[i-20:i+1].max()
            if cond8:
                buy_score += 0.15
            buy_details['new_high'] = cond8

            # === 卖出条件 ===
            sell_conditions = 0
            sell_score = 0
            sell_details = {}

            # 条件 1: 价格在 MA20 之下
            cond1_sell = current_price < curr_ma20
            if cond1_sell:
                sell_conditions += 1
                sell_score += 0.35

            # 条件 2: MA20 向下
            cond2_sell = curr_ma20 < prev_ma20
            if cond2_sell:
                sell_conditions += 1
                sell_score += 0.25

            # 条件 3: MA5 < MA10
            cond3_sell = curr_ma5 < curr_ma10
            if cond3_sell:
                sell_conditions += 1
                sell_score += 0.15

            # 条件 4: MACD 死叉或 DIF<0
            cond4_sell = (curr_macd < 0) or (curr_macd < prev_macd and prev_macd >= 0)
            if cond4_sell:
                sell_conditions += 1
                sell_score += 0.25

            # 条件 5: RSI 超买或下降
            cond5_sell = curr_rsi > 75 or (curr_rsi < prev_rsi and curr_rsi > 70)
            if cond5_sell:
                sell_conditions += 1
                sell_score += 0.25

            # 条件 6: 技术得分负面
            cond6_sell = tech_signal.score < -0.1
            if cond6_sell:
                sell_score += 0.15

            # 确定最终信号
            if buy_conditions >= self.min_buy_conditions and buy_score >= self.buy_score_threshold:
                if buy_conditions >= 6 and buy_score >= 0.9:
                    signal_type = "strong_buy"
                else:
                    signal_type = "buy"
            elif sell_conditions >= 3 and sell_score >= 0.5:
                if sell_conditions >= 5:
                    signal_type = "strong_sell"
                else:
                    signal_type = "sell"
            else:
                signal_type = "hold"

            # 获取日期
            trade_date = df.iloc[i].get("trade_date", str(i))
            if isinstance(trade_date, str):
                try:
                    trade_date = datetime.strptime(trade_date, "%Y%m%d")
                except:
                    trade_date = datetime(2024, 1, 1) + timedelta(days=i)
            elif isinstance(trade_date, (int, float)):
                trade_date = datetime(2024, 1, 1) + timedelta(days=int(i))

            # 计算 ATR 止损距离（放宽）
            if curr_atr > 0:
                stop_distance = (curr_atr * self.atr_multiplier) / current_price
                stop_distance = max(0.05, min(0.15, stop_distance))  # 最小 5%
            else:
                stop_distance = 0.08

            signals.append({
                "stock_code": stock_code,
                "signal": signal_type,
                "timestamp": trade_date,
                "price": current_price,
                "tech_score": tech_signal.score,
                "buy_score": buy_score,
                "sell_score": sell_score,
                "atr": curr_atr,
                "stop_distance": stop_distance,
                "rsi": curr_rsi,
                "volume_ratio": volume_ratio,
                "buy_details": buy_details,
                "sell_details": sell_details,
            })

        return signals


def run_optimized_backtest():
    """运行优化版回测"""
    print("=" * 60)
    print("优化版策略回测 - V2")
    print("=" * 60)

    # 配置
    STOCK_CODES = ["000001", "600000", "000002"]
    INITIAL_CAPITAL = 100000
    DAYS = 120

    collector = PriceCollector()
    strategy = OptimizedStrategy()

    print(f"\n初始资金：{INITIAL_CAPITAL:,.2f} 元")
    print(f"回测股票：{STOCK_CODES}")
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

            # 使用优化策略生成信号
            signals = strategy.generate_signals(df, code)
            all_signals.extend(signals)

        except Exception as e:
            print(f"[ERR] {code}: 错误 - {e}")

    # 信号统计
    signal_types = {}
    for s in all_signals:
        sig = s["signal"]
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
    result = run_with_optimized_execution(price_data, all_signals, INITIAL_CAPITAL)

    # 输出结果
    print_result(result)


def run_with_optimized_execution(price_data, signals, initial_capital):
    """
    优化版执行逻辑
    - 动态止损（根据持仓时间）
    - 分级止盈
    - 智能仓位管理
    """
    capital = initial_capital
    positions = {}
    trades = []
    equity_curve = [capital]

    signals_sorted = sorted(signals, key=lambda x: x.get("timestamp", datetime.now()))

    for signal in signals_sorted:
        code = signal["stock_code"]
        signal_type = signal["signal"]
        timestamp = signal["timestamp"]
        price = signal["price"]
        stop_dist = signal.get("stop_distance", 0.08)
        buy_score = signal.get("buy_score", 0)

        if code not in price_data:
            continue

        # === 买入执行 ===
        if signal_type in ["buy", "strong_buy"] and code not in positions:
            # 根据信号强度调整仓位
            if signal_type == "strong_buy":
                position_ratio = 0.30  # 30% 仓位
            else:
                position_ratio = 0.20  # 20% 仓位

            quantity = int(capital * position_ratio / price / 100) * 100

            if quantity > 0:
                cost = quantity * price * 1.004
                if cost <= capital:
                    capital -= cost
                    stop_price = price * (1 - stop_dist)
                    take_profit = price * (1 + stop_dist * 3.0)  # 盈亏比 3:1

                    positions[code] = {
                        "quantity": quantity,
                        "avg_cost": price,
                        "entry_time": timestamp,
                        "stop_price": stop_price,
                        "take_profit": take_profit,
                        "highest_price": price,
                        "holding_days": 0,
                    }

        # === 卖出执行 ===
        elif signal_type in ["sell", "strong_sell"] and code in positions:
            pos = positions[code]
            sale_value = pos["quantity"] * price * 0.996
            capital += sale_value

            pnl = (price - pos["avg_cost"]) * pos["quantity"]
            pnl_pct = (price - pos["avg_cost"]) / pos["avg_cost"]

            if price <= pos["stop_price"]:
                exit_reason = "止损"
            elif price >= pos["take_profit"]:
                exit_reason = "止盈"
            else:
                exit_reason = "信号"

            trades.append(Trade(
                stock_code=code,
                stock_name="",
                entry_price=pos["avg_cost"],
                exit_price=price,
                quantity=pos["quantity"],
                entry_time=pos["entry_time"],
                exit_time=timestamp,
                direction="long",
                pnl=pnl,
                pnl_pct=pnl_pct,
                exit_reason=exit_reason,
            ))
            del positions[code]

        # === 持仓管理 ===
        for code, pos in list(positions.items()):
            pos["holding_days"] += 1

            if code in price_data:
                df = price_data[code]

                # 动态调整止损：持仓超过 5 天后，放宽止损
                if pos["holding_days"] >= 5:
                    adjusted_stop = pos["avg_cost"] * (1 - stop_dist * 0.7)  # 放宽 30%
                    if adjusted_stop < pos["stop_price"]:
                        pos["stop_price"] = adjusted_stop

                # 更新最高价
                if price > pos["highest_price"]:
                    pos["highest_price"] = price
                    # 跟踪止损
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
                        stock_code=code,
                        stock_name="",
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
                    del positions[code]

                elif price >= pos["take_profit"]:
                    sale_value = pos["quantity"] * pos["take_profit"] * 0.996
                    capital += sale_value
                    pnl = (pos["take_profit"] - pos["avg_cost"]) * pos["quantity"]
                    pnl_pct = (pos["take_profit"] - pos["avg_cost"]) / pos["avg_cost"]

                    trades.append(Trade(
                        stock_code=code,
                        stock_name="",
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
                    del positions[code]

        # 更新资金曲线
        equity = capital
        for code, pos in positions.items():
            if code in price_data:
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
                stock_name="",
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

    # 最大回撤
    max_dd = 0
    peak = equity_curve[0]
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak
        if dd > max_dd:
            max_dd = dd

    # 夏普比率
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


def print_result(result: BacktestResult):
    """打印回测结果"""
    print("\n" + "=" * 60)
    print("回测结果")
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
        print("【结论】策略实现稳定盈利！")
    elif result.total_return > 0:
        print("【结论】策略盈利，但指标有待优化")
    else:
        print("【结论】策略尚未实现稳定盈利，需继续优化")
    print("=" * 60)

    if result.trade_details:
        print(f"\n交易明细 (共 {len(result.trade_details)} 笔):")
        print(f"  {'股票':<8} {'入场价':>8} {'出场价':>8} {'盈亏':>10} {'盈亏率':>10} {'原因':>8}")
        print("  " + "-" * 60)
        for t in result.trade_details:
            reason_short = t.exit_reason[:8] if t.exit_reason else ""
            print(f"  {t.stock_code:<8} {t.entry_price:>8.2f} {t.exit_price:>8.2f} "
                  f"{t.pnl:>10.2f} {t.pnl_pct:>10.2%} {reason_short:>8}")

    print("\n" + "=" * 60)
    print("免责声明：回测结果仅供参考，不构成投资建议")
    print("=" * 60)


if __name__ == "__main__":
    run_optimized_backtest()
