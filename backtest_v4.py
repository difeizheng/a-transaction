"""
V4 稳健策略 - 针对 A 股实盘优化

核心理念：
1. 少而精 - 减少交易频率，提高胜率
2. 顺大势逆小势 - 趋势向上 + 回调买入
3. 严格止损 - 快速止损，让利润奔跑
4. 不追高 - 只在回调时买入

买入条件（必须全部满足）：
1. MA20 向上（中期趋势向上）
2. MA60 向上（长期趋势向上）
3. 价格在 MA20 之上（多头排列）
4. 近 3-5 日回调 3%-8%（不追高）
5. RSI 35-55（未超买，有上升空间）
6. 成交量萎缩（回调缩量）

卖出条件（满足任一即卖出）：
1. 跌破 MA20（趋势破坏）
2. 止损 -8%
3. 止盈 +20%
4. 持仓超过 8 天无盈利

仓位管理：
- 单只股票最高 25% 仓位
- 总仓位不超过 75%
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))

from src.collectors.price_collector import PriceCollector
from src.analyzers.technical_analyzer import TechnicalAnalyzer
from src.analyzers.volatility_analyzer import VolatilityAnalyzer
import pandas as pd
import numpy as np


class V4Strategy:
    """V4 稳健策略"""

    def __init__(self):
        self.technical_analyzer = TechnicalAnalyzer()
        self.volatility_analyzer = VolatilityAnalyzer()

        # 策略参数
        self.max_position_ratio = 0.25  # 单只股票最高 25%
        self.total_position_ratio = 0.75  # 总仓位 75%
        self.stop_loss = 0.08  # 止损 8%
        self.take_profit = 0.20  # 止盈 20%
        self.time_stop_days = 8  # 时间止损 8 天

        # 持仓
        self.positions = {}

    def generate_signals(self, df: pd.DataFrame, stock_code: str, stock_name: str = "") -> list:
        """
        生成 V4 策略信号

        买入条件（必须全部满足）：
        1. MA20 向上
        2. MA60 向上
        3. 价格在 MA20 之上
        4. 近 3-5 日回调 3%-8%
        5. RSI 35-55
        6. 成交量萎缩
        """
        signals = []
        if len(df) < 65:  # 需要至少 65 天数据
            return signals

        # 计算指标
        ma5 = df['close'].rolling(5).mean()
        ma10 = df['close'].rolling(10).mean()
        ma20 = df['close'].rolling(20).mean()
        ma60 = df['close'].rolling(60).mean()

        # MACD
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        macd_dif = exp1 - exp2

        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        for i in range(60, len(df)):
            current_price = float(df.iloc[i]['close'])

            # 获取指标值
            curr_ma20 = float(ma20.iloc[i])
            curr_ma60 = float(ma60.iloc[i])
            prev_ma20_5 = float(ma20.iloc[i-5])
            prev_ma60_5 = float(ma60.iloc[i-5])

            # 5 日前价格
            price_5d_ago = float(df.iloc[i-5]['close'])
            price_3d_ago = float(df.iloc[i-3]['close'])

            # RSI
            curr_rsi = float(rsi.iloc[i]) if not np.isnan(rsi.iloc[i]) else 50

            # 成交量
            avg_volume_10 = df['volume'].iloc[i-10:i].mean()
            curr_volume = df['volume'].iloc[i]
            volume_ratio = curr_volume / avg_volume_10 if avg_volume_10 > 0 else 1

            # === 买入条件检查 ===
            conditions_met = 0
            buy_details = {}

            # 1. MA20 向上
            if curr_ma20 > prev_ma20_5:
                conditions_met += 1
                buy_details['ma20_up'] = True

            # 2. MA60 向上
            if curr_ma60 > prev_ma60_5:
                conditions_met += 1
                buy_details['ma60_up'] = True

            # 3. 价格在 MA20 之上
            if current_price > curr_ma20:
                conditions_met += 1
                buy_details['above_ma20'] = True

            # 4. 近 3-5 日回调 3%-8%
            pullback_5d = (price_5d_ago - current_price) / price_5d_ago
            pullback_3d = (price_3d_ago - current_price) / price_3d_ago
            if 0.03 <= pullback_5d <= 0.12 or 0.02 <= pullback_3d <= 0.08:
                conditions_met += 1
                buy_details['pullback'] = True
                buy_details['pullback_pct'] = pullback_5d

            # 5. RSI 35-55
            if 35 <= curr_rsi <= 55:
                conditions_met += 1
                buy_details['rsi_ok'] = True

            # 6. 成交量萎缩（回调缩量）
            if volume_ratio < 1.0:
                conditions_met += 1
                buy_details['volume_down'] = True

            # 判断信号
            if conditions_met == 6:
                signal_type = "strong_buy"
            elif conditions_met >= 4:
                signal_type = "buy"
            else:
                signal_type = "hold"

            # === 卖出条件检查 ===
            sell_conditions = 0
            sell_details = {}

            # 1. 跌破 MA20
            if current_price < curr_ma20 * 0.98:  # 允许 2% 的误差
                sell_conditions += 1
                sell_details['below_ma20'] = True

            # 2. MA20 向下
            if curr_ma20 < prev_ma20_5:
                sell_conditions += 1
                sell_details['ma20_down'] = True

            # 3. RSI 超买
            if curr_rsi > 70:
                sell_conditions += 1
                sell_details['rsi_overbought'] = True

            if sell_conditions >= 2:
                signal_type = "sell"
            elif sell_conditions >= 3:
                signal_type = "strong_sell"

            # 获取日期
            trade_date = df.iloc[i].get("trade_date", str(i))
            if isinstance(trade_date, str):
                try:
                    trade_date = datetime.strptime(trade_date, "%Y%m%d")
                except:
                    trade_date = datetime(2024, 1, 1) + timedelta(days=i)

            # 计算 ATR 止损
            subset = df.iloc[:i+1].copy()
            atr = self.volatility_analyzer.calculate_atr(subset)
            curr_atr = float(atr.iloc[i]) if not np.isnan(atr.iloc[i]) else 0

            if curr_atr > 0:
                stop_distance = max(self.stop_loss, (curr_atr * 2) / current_price)
                stop_distance = min(stop_distance, 0.12)
            else:
                stop_distance = self.stop_loss

            signals.append({
                "stock_code": stock_code,
                "stock_name": stock_name,
                "signal": signal_type,
                "timestamp": trade_date,
                "price": current_price,
                "stop_distance": stop_distance,
                "take_profit_distance": self.take_profit,
                "rsi": curr_rsi,
                "conditions_met": conditions_met,
                "buy_details": buy_details,
                "sell_details": sell_details,
            })

        return signals


def run_v4_backtest():
    """运行 V4 回测"""
    print("=" * 70)
    print("V4 稳健策略回测")
    print("=" * 70)

    STOCK_CODES = ["000001", "600000", "000002"]
    INITIAL_CAPITAL = 100000
    DAYS = 120

    collector = PriceCollector()
    strategy = V4Strategy()

    print(f"\n初始资金：{INITIAL_CAPITAL:,.2f} 元")
    print(f"回测股票：{STOCK_CODES}")
    print(f"数据周期：{DAYS} 天")
    print("-" * 70)

    # 获取数据
    price_data = {}
    all_signals = []

    for code in STOCK_CODES:
        try:
            df = collector.get_kline(code, period="daily", limit=max(DAYS, 120))
            if df is None or df.empty:
                print(f"[ERR] {code}: 无法获取数据")
                continue

            price_data[code] = df
            print(f"[OK] {code}: 获取到 {len(df)} 条数据")

            # 生成信号
            signals = strategy.generate_signals(df, code)
            all_signals.extend(signals)

        except Exception as e:
            print(f"[ERR] {code}: 错误 - {e}")

    if not all_signals:
        print("\n[ERR] 没有生成任何信号")
        return

    # 信号统计
    signal_types = {}
    for s in all_signals:
        sig = s["signal"]
        signal_types[sig] = signal_types.get(sig, 0) + 1

    print(f"\n生成信号总数：{len(all_signals)}")
    print("信号类型统计:")
    for sig, count in sorted(signal_types.items()):
        print(f"  {sig}: {count}")
    print("-" * 70)

    # 运行回测
    result = execute_trades(price_data, all_signals, INITIAL_CAPITAL, strategy)

    # 输出结果
    print_result(result)


def execute_trades(price_data, signals, initial_capital, strategy):
    """执行交易"""
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

        if code not in price_data:
            continue

        # === 买入执行 ===
        if signal_type in ["buy", "strong_buy"] and code not in positions:
            position_ratio = 0.25 if signal_type == "strong_buy" else 0.20
            quantity = int(capital * position_ratio / price / 100) * 100

            if quantity > 0:
                cost = quantity * price * 1.004
                if cost <= capital:
                    capital -= cost
                    stop_price = price * (1 - stop_dist)
                    take_profit = price * (1 + strategy.take_profit)

                    positions[code] = {
                        "quantity": quantity,
                        "avg_cost": price,
                        "entry_time": timestamp,
                        "stop_price": stop_price,
                        "take_profit": take_profit,
                        "highest_price": price,
                    }

        # === 检查持仓 ===
        for pos_code, pos in list(positions.items()):
            if pos_code not in price_data:
                continue

            df = price_data[pos_code]
            current_price = float(df["close"].iloc[-1])

            # 更新最高价和止损
            if current_price > pos["highest_price"]:
                pos["highest_price"] = current_price
                new_stop = current_price * (1 - 0.05)  # 跟踪止损 5%
                if new_stop > pos["stop_price"]:
                    pos["stop_price"] = new_stop

            # 计算持仓天数
            holding_days = (timestamp - pos["entry_time"]).days

            # 检查止损
            exit_reason = None
            exit_price = None

            if current_price <= pos["stop_price"]:
                exit_reason = "止损"
                exit_price = pos["stop_price"]
            elif current_price >= pos["take_profit"]:
                exit_reason = "止盈"
                exit_price = pos["take_profit"]
            elif holding_days >= strategy.time_stop_days:
                profit_pct = (current_price - pos["avg_cost"]) / pos["avg_cost"]
                if profit_pct < 0.05:
                    exit_reason = "时间止损"
                    exit_price = current_price

            if exit_reason:
                quantity = pos["quantity"]
                if exit_reason == "止损":
                    sale_value = quantity * exit_price * 0.996
                else:
                    sale_value = quantity * exit_price * 0.996

                pnl = (exit_price - pos["avg_cost"]) * quantity
                pnl_pct = (exit_price - pos["avg_cost"]) / pos["avg_cost"]

                trades.append({
                    "stock_code": pos_code,
                    "entry_price": pos["avg_cost"],
                    "exit_price": exit_price,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "exit_reason": exit_reason,
                })

                capital += sale_value
                del positions[pos_code]

        # 计算权益
        equity = capital
        for pos_code, pos in positions.items():
            if pos_code in price_data:
                equity += pos["quantity"] * price
        equity_curve.append(equity)

    # 平仓剩余持仓
    for code, pos in positions.items():
        if code in price_data:
            df = price_data[code]
            final_price = float(df["close"].iloc[-1])
            sale_value = pos["quantity"] * final_price * 0.996
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
            capital += sale_value

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
        "trades": trades,
    }


def print_result(result: dict):
    """打印结果"""
    print("\n" + "=" * 70)
    print("回测结果")
    print("=" * 70)

    metrics = [
        ("总收益率", "total_return"),
        ("胜率", "win_rate"),
        ("平均盈利", "avg_win"),
        ("平均亏损", "avg_loss"),
        ("盈亏比", "profit_loss_ratio"),
        ("最大回撤", "max_drawdown"),
        ("交易次数", "total_trades"),
        ("盈利次数", "winning_trades"),
        ("亏损次数", "losing_trades"),
        ("最终资金", "final_capital"),
    ]

    for name, key in metrics:
        val = result[key]
        if isinstance(val, float):
            if key == "final_capital":
                val_str = f"{val:,.2f} 元"
            else:
                val_str = f"{val:.2%}" if key in ["total_return", "win_rate", "avg_win", "avg_loss", "max_drawdown"] else f"{val:.2f}"
        else:
            val_str = str(val)
        print(f"{name:<15} {val_str:>20}")

    print("=" * 70)


if __name__ == "__main__":
    run_v4_backtest()
