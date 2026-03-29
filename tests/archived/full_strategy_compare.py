"""
完整策略对比 - 使用实际的回测执行逻辑
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from src.collectors.price_collector import PriceCollector
from src.analyzers.technical_analyzer import TechnicalAnalyzer
from src.analyzers.volatility_analyzer import VolatilityAnalyzer


def run_old_strategy_backtest(price_data, initial_capital=100000):
    """老策略回测"""
    technical_analyzer = TechnicalAnalyzer()
    volatility_analyzer = VolatilityAnalyzer()

    capital = initial_capital
    positions = {}
    trades = []
    equity_curve = [capital]
    all_signals = []

    for code, df in price_data.items():
        if len(df) < 30:
            continue

        ma5 = df['close'].rolling(5).mean()
        ma10 = df['close'].rolling(10).mean()
        ma20 = df['close'].rolling(20).mean()

        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        macd_dif = exp1 - exp2

        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        atr = volatility_analyzer.calculate_atr(df)

        for i in range(25, len(df)):
            current_price = float(df.iloc[i]['close'])
            curr_ma5 = float(ma5.iloc[i])
            curr_ma10 = float(ma10.iloc[i])
            curr_ma20 = float(ma20.iloc[i]) if i >= 20 else current_price
            curr_macd = float(macd_dif.iloc[i])
            prev_macd = float(macd_dif.iloc[i-1]) if i > 0 else 0
            curr_rsi = float(rsi.iloc[i]) if not np.isnan(rsi.iloc[i]) else 50

            avg_volume = df['volume'].iloc[i-20:i].mean() if i >= 20 else df['volume'].iloc[i]
            curr_volume = df['volume'].iloc[i]
            volume_ratio = curr_volume / avg_volume if avg_volume > 0 else 1

            tech_signal = technical_analyzer.analyze(df.iloc[:i+1])

            # 老策略买入条件
            buy_conditions = 0
            buy_score = 0

            if current_price > curr_ma20:
                buy_conditions += 1
                buy_score += 0.3
            if curr_ma5 > curr_ma10:
                buy_conditions += 1
                buy_score += 0.2
            if (curr_macd > 0) or (curr_macd > prev_macd and prev_macd <= 0):
                buy_conditions += 1
                buy_score += 0.3
            if 30 < curr_rsi < 70:
                buy_conditions += 1
                buy_score += 0.2
            if tech_signal.score > 0:
                buy_score += 0.2
            if volume_ratio > 1.2:
                buy_score += 0.1

            if buy_conditions >= 3 and buy_score >= 0.5:
                signal_type = "buy"
            elif buy_conditions >= 5:
                signal_type = "strong_buy"
            else:
                signal_type = "hold"

            trade_date = df.iloc[i].get("trade_date", str(i))
            if isinstance(trade_date, str):
                try:
                    trade_date = datetime.strptime(trade_date, "%Y%m%d")
                except:
                    trade_date = datetime(2024, 1, 1) + timedelta(days=i)

            all_signals.append({
                "stock_code": code,
                "signal": signal_type,
                "timestamp": trade_date,
                "price": current_price,
                "buy_score": buy_score,
                "buy_conditions": buy_conditions,
            })

    # 执行交易
    signals_sorted = sorted(all_signals, key=lambda x: x.get("timestamp", datetime.now()))

    for signal in signals_sorted:
        code = signal["stock_code"]
        signal_type = signal["signal"]
        timestamp = signal["timestamp"]
        price = signal["price"]

        if code not in price_data:
            continue

        if signal_type in ["buy", "strong_buy"] and code not in positions:
            position_ratio = 0.25 if signal_type == "strong_buy" else 0.15
            quantity = int(capital * position_ratio / price / 100) * 100

            if quantity > 0:
                cost = quantity * price * 1.004
                if cost <= capital:
                    capital -= cost
                    stop_price = price * 0.92
                    take_profit = price * 1.20

                    positions[code] = {
                        "quantity": quantity,
                        "avg_cost": price,
                        "entry_time": timestamp,
                        "stop_price": stop_price,
                        "take_profit": take_profit,
                        "highest_price": price,
                        "holding_days": 0,
                    }

        elif signal_type in ["sell", "strong_sell"] and code in positions:
            pos = positions[code]
            sale_value = pos["quantity"] * price * 0.996
            capital += sale_value

            pnl = (price - pos["avg_cost"]) * pos["quantity"]
            pnl_pct = (price - pos["avg_cost"]) / pos["avg_cost"]

            trades.append({
                "stock_code": code,
                "entry_price": pos["avg_cost"],
                "exit_price": price,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "exit_reason": "信号",
            })
            del positions[code]

        for code, pos in list(positions.items()):
            pos["holding_days"] += 1
            if code in price_data:
                df = price_data[code]
                curr_price = float(df["close"].iloc[-1])

                if curr_price > pos["highest_price"]:
                    pos["highest_price"] = curr_price
                    new_stop = curr_price * 0.92
                    if new_stop > pos["stop_price"]:
                        pos["stop_price"] = new_stop

                if curr_price <= pos["stop_price"]:
                    sale_value = pos["quantity"] * pos["stop_price"] * 0.996
                    capital += sale_value
                    pnl = (pos["stop_price"] - pos["avg_cost"]) * pos["quantity"]
                    pnl_pct = (pos["stop_price"] - pos["avg_cost"]) / pos["avg_cost"]

                    trades.append({
                        "stock_code": code,
                        "entry_price": pos["avg_cost"],
                        "exit_price": pos["stop_price"],
                        "pnl": pnl,
                        "pnl_pct": pnl_pct,
                        "exit_reason": "止损",
                    })
                    del positions[code]

                elif curr_price >= pos["take_profit"]:
                    sale_value = pos["quantity"] * pos["take_profit"] * 0.996
                    capital += sale_value
                    pnl = (pos["take_profit"] - pos["avg_cost"]) * pos["quantity"]
                    pnl_pct = (pos["take_profit"] - pos["avg_cost"]) / pos["avg_cost"]

                    trades.append({
                        "stock_code": code,
                        "entry_price": pos["avg_cost"],
                        "exit_price": pos["take_profit"],
                        "pnl": pnl,
                        "pnl_pct": pnl_pct,
                        "exit_reason": "止盈",
                    })
                    del positions[code]

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

            trades.append({
                "stock_code": code,
                "entry_price": pos["avg_cost"],
                "exit_price": final_price,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "exit_reason": "平仓",
            })

    # 计算指标
    winning = [t for t in trades if t["pnl"] > 0]
    losing = [t for t in trades if t["pnl"] <= 0]
    win_rate = len(winning) / len(trades) if trades else 0

    avg_win = np.mean([t["pnl_pct"] for t in winning]) if winning else 0
    avg_loss = abs(np.mean([t["pnl_pct"] for t in losing])) if losing else 0
    profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0

    max_dd = 0
    peak = equity_curve[0]
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak
        if dd > max_dd:
            max_dd = dd

    total_return = (capital - initial_capital) / initial_capital

    return {
        "total_return": total_return,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_loss_ratio": profit_loss_ratio,
        "max_drawdown": max_dd,
        "total_trades": len(trades),
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "final_capital": capital,
    }


def run_new_strategy_backtest(price_data, initial_capital=100000):
    """新策略回测"""
    technical_analyzer = TechnicalAnalyzer()
    volatility_analyzer = VolatilityAnalyzer()

    capital = initial_capital
    positions = {}
    trades = []
    equity_curve = [capital]
    all_signals = []

    for code, df in price_data.items():
        if len(df) < 35:
            continue

        ma5 = df['close'].rolling(5).mean()
        ma10 = df['close'].rolling(10).mean()
        ma20 = df['close'].rolling(20).mean()

        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        macd_dif = exp1 - exp2

        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        atr = volatility_analyzer.calculate_atr(df)

        for i in range(30, len(df)):
            current_price = float(df.iloc[i]['close'])
            curr_ma5 = float(ma5.iloc[i])
            curr_ma10 = float(ma10.iloc[i])
            curr_ma20 = float(ma20.iloc[i]) if i >= 20 else current_price
            prev_ma20 = float(ma20.iloc[i-5]) if i >= 25 else curr_ma20
            curr_macd = float(macd_dif.iloc[i])
            prev_macd = float(macd_dif.iloc[i-1]) if i > 0 else 0
            curr_rsi = float(rsi.iloc[i]) if not np.isnan(rsi.iloc[i]) else 50
            prev_rsi = float(rsi.iloc[i-3]) if i >= 3 else curr_rsi

            avg_volume = df['volume'].iloc[i-20:i].mean() if i >= 20 else df['volume'].iloc[i]
            curr_volume = df['volume'].iloc[i]
            volume_ratio = curr_volume / avg_volume if avg_volume > 0 else 1

            tech_signal = technical_analyzer.analyze(df.iloc[:i+1])

            # 新策略买入条件
            buy_conditions = 0
            buy_score = 0

            if current_price > curr_ma20:
                buy_conditions += 1
                buy_score += 0.25
            if curr_ma20 > prev_ma20:
                buy_conditions += 1
                buy_score += 0.25
            if curr_ma5 > curr_ma10:
                buy_conditions += 1
                buy_score += 0.15
            if (curr_macd > 0) or (curr_macd > prev_macd and prev_macd <= 0):
                buy_conditions += 1
                buy_score += 0.25
            if 35 < curr_rsi < 65 and curr_rsi > prev_rsi:
                buy_conditions += 1
                buy_score += 0.2
            if tech_signal.score > 0.1:
                buy_score += 0.15
            if volume_ratio > 1.5:
                buy_score += 0.15

            if buy_conditions >= 4 and buy_score >= 0.6:
                signal_type = "buy"
            elif buy_conditions >= 6 and buy_score >= 0.9:
                signal_type = "strong_buy"
            else:
                signal_type = "hold"

            trade_date = df.iloc[i].get("trade_date", str(i))
            if isinstance(trade_date, str):
                try:
                    trade_date = datetime.strptime(trade_date, "%Y%m%d")
                except:
                    trade_date = datetime(2024, 1, 1) + timedelta(days=i)

            all_signals.append({
                "stock_code": code,
                "signal": signal_type,
                "timestamp": trade_date,
                "price": current_price,
                "buy_score": buy_score,
                "buy_conditions": buy_conditions,
            })

    # 执行交易
    signals_sorted = sorted(all_signals, key=lambda x: x.get("timestamp", datetime.now()))

    for signal in signals_sorted:
        code = signal["stock_code"]
        signal_type = signal["signal"]
        timestamp = signal["timestamp"]
        price = signal["price"]

        if code not in price_data:
            continue

        if signal_type in ["buy", "strong_buy"] and code not in positions:
            position_ratio = 0.30 if signal_type == "strong_buy" else 0.20
            quantity = int(capital * position_ratio / price / 100) * 100

            if quantity > 0:
                cost = quantity * price * 1.004
                if cost <= capital:
                    capital -= cost
                    stop_price = price * 0.95  # 5% 止损
                    take_profit = price * 1.285  # 盈亏比 3:1

                    positions[code] = {
                        "quantity": quantity,
                        "avg_cost": price,
                        "entry_time": timestamp,
                        "stop_price": stop_price,
                        "take_profit": take_profit,
                        "highest_price": price,
                        "holding_days": 0,
                    }

        elif signal_type in ["sell", "strong_sell"] and code in positions:
            pos = positions[code]
            sale_value = pos["quantity"] * price * 0.996
            capital += sale_value

            pnl = (price - pos["avg_cost"]) * pos["quantity"]
            pnl_pct = (price - pos["avg_cost"]) / pos["avg_cost"]

            trades.append({
                "stock_code": code,
                "entry_price": pos["avg_cost"],
                "exit_price": price,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "exit_reason": "信号",
            })
            del positions[code]

        for code, pos in list(positions.items()):
            pos["holding_days"] += 1
            if code in price_data:
                df = price_data[code]
                curr_price = float(df["close"].iloc[-1])

                # 动态止损：持仓超过 5 天后放宽
                if pos["holding_days"] >= 5:
                    adjusted_stop = pos["avg_cost"] * 0.965
                    if adjusted_stop < pos["stop_price"]:
                        pos["stop_price"] = adjusted_stop

                if curr_price > pos["highest_price"]:
                    pos["highest_price"] = curr_price
                    new_stop = curr_price * 0.95
                    if new_stop > pos["stop_price"]:
                        pos["stop_price"] = new_stop

                if curr_price <= pos["stop_price"]:
                    sale_value = pos["quantity"] * pos["stop_price"] * 0.996
                    capital += sale_value
                    pnl = (pos["stop_price"] - pos["avg_cost"]) * pos["quantity"]
                    pnl_pct = (pos["stop_price"] - pos["avg_cost"]) / pos["avg_cost"]

                    trades.append({
                        "stock_code": code,
                        "entry_price": pos["avg_cost"],
                        "exit_price": pos["stop_price"],
                        "pnl": pnl,
                        "pnl_pct": pnl_pct,
                        "exit_reason": "止损",
                    })
                    del positions[code]

                elif curr_price >= pos["take_profit"]:
                    sale_value = pos["quantity"] * pos["take_profit"] * 0.996
                    capital += sale_value
                    pnl = (pos["take_profit"] - pos["avg_cost"]) * pos["quantity"]
                    pnl_pct = (pos["take_profit"] - pos["avg_cost"]) / pos["avg_cost"]

                    trades.append({
                        "stock_code": code,
                        "entry_price": pos["avg_cost"],
                        "exit_price": pos["take_profit"],
                        "pnl": pnl,
                        "pnl_pct": pnl_pct,
                        "exit_reason": "止盈",
                    })
                    del positions[code]

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

            trades.append({
                "stock_code": code,
                "entry_price": pos["avg_cost"],
                "exit_price": final_price,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "exit_reason": "平仓",
            })

    # 计算指标
    winning = [t for t in trades if t["pnl"] > 0]
    losing = [t for t in trades if t["pnl"] <= 0]
    win_rate = len(winning) / len(trades) if trades else 0

    avg_win = np.mean([t["pnl_pct"] for t in winning]) if winning else 0
    avg_loss = abs(np.mean([t["pnl_pct"] for t in losing])) if losing else 0
    profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0

    max_dd = 0
    peak = equity_curve[0]
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak
        if dd > max_dd:
            max_dd = dd

    total_return = (capital - initial_capital) / initial_capital

    return {
        "total_return": total_return,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_loss_ratio": profit_loss_ratio,
        "max_drawdown": max_dd,
        "total_trades": len(trades),
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "final_capital": capital,
    }


if __name__ == "__main__":
    print("=" * 80)
    print("完整策略对比分析 - 老策略 vs 新策略")
    print("=" * 80)

    STOCK_CODES = ["000001", "600000", "000002"]
    DAYS = 120
    INITIAL_CAPITAL = 100000

    collector = PriceCollector()

    # 获取数据
    price_data = {}
    for code in STOCK_CODES:
        df = collector.get_kline(code, period="daily", limit=DAYS)
        if df is not None and not df.empty:
            price_data[code] = df
            print(f"[OK] {code}: {len(df)} 条数据")

    print("\n" + "=" * 80)

    # 运行老策略回测
    print("\n运行老策略回测...")
    old_result = run_old_strategy_backtest(price_data, INITIAL_CAPITAL)
    print(f"老策略完成：收益率={old_result['total_return']:.1%}, 交易={old_result['total_trades']}笔")

    # 运行新策略回测
    print("运行新策略回测...")
    new_result = run_new_strategy_backtest(price_data, INITIAL_CAPITAL)
    print(f"新策略完成：收益率={new_result['total_return']:.1%}, 交易={new_result['total_trades']}笔")

    # 对比输出
    print("\n" + "=" * 80)
    print("策略对比结果")
    print("=" * 80)

    print(f"\n{'指标':<20} {'老策略':>15} {'新策略':>15} {'变化':>15}")
    print("-" * 65)

    metrics = [
        ("总收益率", "total_return"),
        ("最终资金", "final_capital"),
        ("胜率", "win_rate"),
        ("平均盈利", "avg_win"),
        ("平均亏损", "avg_loss"),
        ("盈亏比", "profit_loss_ratio"),
        ("最大回撤", "max_drawdown"),
        ("交易次数", "total_trades"),
        ("盈利次数", "winning_trades"),
        ("亏损次数", "losing_trades"),
    ]

    for name, key in metrics:
        old_val = old_result[key]
        new_val = new_result[key]
        if isinstance(old_val, float):
            change = f"{((new_val - old_val) / abs(old_val) * 100) if old_val != 0 else 0:+.1f}%"
            old_str = f"{old_val:.2%}" if key in ["total_return", "win_rate", "avg_win", "avg_loss", "max_drawdown"] else f"{old_val:,.0f}"
            new_str = f"{new_val:.2%}" if key in ["total_return", "win_rate", "avg_win", "avg_loss", "max_drawdown"] else f"{new_val:,.0f}"
        else:
            change = f"{new_val - old_val:+d}"
            old_str = str(old_val)
            new_str = str(new_val)
        print(f"{name:<20} {old_str:>15} {new_str:>15} {change:>15}")

    print("\n" + "=" * 80)
    print("优劣势分析")
    print("=" * 80)

    print("\n[新策略优势]")
    if new_result["profit_loss_ratio"] > old_result["profit_loss_ratio"]:
        print(f"  + 盈亏比提升：{old_result['profit_loss_ratio']:.2f} -> {new_result['profit_loss_ratio']:.2f}")
    if new_result["avg_win"] > old_result["avg_win"]:
        print(f"  + 平均盈利提升：{old_result['avg_win']:.1%} -> {new_result['avg_win']:.1%}")
    if new_result["total_trades"] < old_result["total_trades"]:
        reduction = 100 * (old_result['total_trades'] - new_result['total_trades']) / old_result['total_trades']
        print(f"  + 交易频率降低：{old_result['total_trades']} -> {new_result['total_trades']} (-{reduction:.0f}%)")
    if new_result["win_rate"] > old_result["win_rate"]:
        print(f"  + 胜率提升：{old_result['win_rate']:.1%} -> {new_result['win_rate']:.1%}")
    if new_result["avg_loss"] < old_result["avg_loss"]:
        print(f"  + 平均亏损减少：{old_result['avg_loss']:.1%} -> {new_result['avg_loss']:.1%}")
    if new_result["max_drawdown"] < old_result["max_drawdown"]:
        print(f"  + 回撤更小：{old_result['max_drawdown']:.1%} -> {new_result['max_drawdown']:.1%}")

    print("\n[新策略劣势]")
    if new_result["total_return"] < old_result["total_return"]:
        print(f"  - 总收益率下降：{old_result['total_return']:.1%} -> {new_result['total_return']:.1%}")
    if new_result["max_drawdown"] > old_result["max_drawdown"]:
        print(f"  - 回撤增大：{old_result['max_drawdown']:.1%} -> {new_result['max_drawdown']:.1%}")
    if new_result["win_rate"] < old_result["win_rate"]:
        print(f"  - 胜率下降：{old_result['win_rate']:.1%} -> {new_result['win_rate']:.1%}")

    # 综合评价
    print("\n" + "=" * 80)
    print("综合评价")
    print("=" * 80)

    print("\n[老策略特点]")
    print(f"  - 交易频率：{old_result['total_trades']}笔/120 天，约{old_result['total_trades']/4:.1f}笔/月")
    print(f"  - 胜率：{old_result['win_rate']:.1%}")
    print(f"  - 盈亏比：{old_result['profit_loss_ratio']:.2f}")
    print(f"  - 总收益：{old_result['total_return']:.1%}")
    print(f"  - 最大回撤：{old_result['max_drawdown']:.1%}")

    print("\n[新策略特点]")
    print(f"  - 交易频率：{new_result['total_trades']}笔/120 天，约{new_result['total_trades']/4:.1f}笔/月")
    print(f"  - 胜率：{new_result['win_rate']:.1%}")
    print(f"  - 盈亏比：{new_result['profit_loss_ratio']:.2f}")
    print(f"  - 总收益：{new_result['total_return']:.1%}")
    print(f"  - 最大回撤：{new_result['max_drawdown']:.1%}")

    # 结论
    print("\n" + "=" * 80)
    print("最终结论")
    print("=" * 80)

    # 计算综合得分
    old_score = old_result['total_return'] * 0.4 + old_result['win_rate'] * 0.2 + old_result['profit_loss_ratio'] * 0.2 - old_result['max_drawdown'] * 0.2
    new_score = new_result['total_return'] * 0.4 + new_result['win_rate'] * 0.2 + new_result['profit_loss_ratio'] * 0.2 - new_result['max_drawdown'] * 0.2

    print(f"\n综合得分 (收益*0.4 + 胜率*0.2 + 盈亏比*0.2 - 回撤*0.2):")
    print(f"  老策略：{old_score:.4f}")
    print(f"  新策略：{new_score:.4f}")

    if new_score > old_score:
        print("\n[结论] 新策略综合得分更高！")
        print("       新策略是'少而精'的类型，适合稳健型投资者。")
    else:
        print("\n[结论] 老策略综合得分更高。")
        print("       建议：继续使用老策略，或进一步优化新策略参数。")

    print("\n" + "=" * 80)
    print("免责声明：回测结果仅供参考，不构成投资建议")
    print("=" * 80)
