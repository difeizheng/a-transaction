"""
V3 实战策略回测 - 针对 A 股实盘优化

核心改进：
1. 大盘环境过滤 - 只在市场环境好时操作
2. 核心条件 + 加分条件分层设计
3. 动态仓位管理 - 轻仓 15%/中仓 25%/重仓 35%
4. 时间止损 - 持仓 10 天无盈利退出
5. 跟踪止损 - 从最高点回撤 5% 自动止损
6. 阶梯式止盈 - 更灵活的止盈策略
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))

from src.collectors.price_collector import PriceCollector
from src.strategy.v3_strategy import V3Strategy, StrategySignal
import pandas as pd
import numpy as np


class V3BacktestEngine:
    """V3 策略回测引擎"""

    def __init__(self, initial_capital=100000):
        self.initial_capital = initial_capital
        self.strategy = V3Strategy(
            atr_multiplier=2.0,
            initial_stop=0.08,
            trailing_stop=0.05,
            time_stop_days=10,
        )

    def get_market_data(self, price_data: dict) -> pd.DataFrame:
        """获取大盘数据用于环境判断"""
        # 使用第一只股票作为大盘代理（简化处理）
        # 实际应该使用沪深 300 指数
        for code, df in price_data.items():
            return df
        return None

    def run(self, price_data: dict, use_market_filter: bool = True) -> dict:
        """
        运行回测

        Args:
            price_data: {stock_code: df} 价格数据字典
            use_market_filter: 是否使用大盘环境过滤

        Returns:
            回测结果字典
        """
        capital = self.initial_capital
        all_trades = []
        equity_curve = [capital]

        # 获取大盘环境判断
        market_df = self.get_market_data(price_data)
        is_market_ok = True
        if use_market_filter and market_df is not None and len(market_df) >= 20:
            is_market_ok = self.strategy.check_market_condition(market_df)
            print(f"大盘环境判断：{'可操作' if is_market_ok else '观望'}")
        else:
            if use_market_filter:
                print("大盘环境判断：跳过（数据不足）")
            else:
                print("大盘环境过滤：已关闭")

        # 收集所有信号
        all_signals = []
        for code, df in price_data.items():
            signals = self._generate_signals_for_stock(df, code, is_market_ok)
            all_signals.extend(signals)

        # 按时间排序
        signals_sorted = sorted(all_signals, key=lambda x: x.get("timestamp", datetime.now()))

        # 执行交易
        for signal in signals_sorted:
            code = signal["stock_code"]
            signal_type = signal["signal"]
            timestamp = signal["timestamp"]
            price = signal["price"]

            if code not in price_data:
                continue

            # 买入
            if signal_type in ["buy", "strong_buy"] and code not in self.strategy.positions:
                quantity = self.strategy.get_position_size(
                    signal=type('obj', (object,), {
                        'position_level': signal["position_level"],
                        'price': price,
                    })(),
                    capital=capital,
                )

                if quantity > 0:
                    cost = quantity * price * 1.004  # 包含手续费
                    if cost <= capital:
                        capital -= cost
                        # 创建策略信号对象用于建仓
                        v3_signal = type('obj', (object,), {
                            'stock_code': code,
                            'stock_name': signal.get("stock_name", ""),
                            'signal': signal_type,
                            'price': price,
                            'timestamp': timestamp,
                            'stop_distance': signal["stop_distance"],
                            'take_profit_distance': signal["take_profit_distance"],
                            'position_level': signal["position_level"],
                        })()
                        self.strategy.update_position(v3_signal, quantity)

            # 检查持仓退出
            for pos_code in list(self.strategy.positions.keys()):
                if pos_code not in price_data:
                    continue

                pos_df = price_data[pos_code]
                current_price = float(pos_df["close"].iloc[-1])
                holding_days = (timestamp - self.strategy.positions[pos_code].entry_time).days

                # 更新跟踪止损
                self.strategy.update_trailing_stop(pos_code, current_price)

                # 检查退出条件
                exit_result = self.strategy.check_exit(
                    stock_code=pos_code,
                    current_price=current_price,
                    timestamp=timestamp,
                    holding_days=holding_days,
                )

                if exit_result:
                    position, exit_reason, exit_price = exit_result
                    # 计算盈亏
                    quantity = position.quantity
                    sale_value = quantity * exit_price * 0.996  # 扣除手续费
                    pnl = (exit_price - position.avg_cost) * quantity
                    pnl_pct = (exit_price - position.avg_cost) / position.avg_cost

                    all_trades.append({
                        "stock_code": pos_code,
                        "entry_price": position.avg_cost,
                        "exit_price": exit_price,
                        "pnl": pnl,
                        "pnl_pct": pnl_pct,
                        "exit_reason": exit_reason,
                        "entry_date": position.entry_time,
                        "exit_date": timestamp,
                    })

                    capital += sale_value
                    self.strategy.remove_position(pos_code)

            # 计算权益
            equity = capital
            for pos_code, pos in self.strategy.positions.items():
                if pos_code in price_data:
                    equity += pos.quantity * price
            equity_curve.append(equity)

        # 平仓所有剩余持仓
        for code, position in self.strategy.positions.items():
            if code in price_data:
                df = price_data[code]
                final_price = float(df["close"].iloc[-1])
                sale_value = position.quantity * final_price * 0.996
                pnl = (final_price - position.avg_cost) * position.quantity
                pnl_pct = (final_price - position.avg_cost) / position.avg_cost

                all_trades.append({
                    "stock_code": code,
                    "entry_price": position.avg_cost,
                    "exit_price": final_price,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "exit_reason": "平仓",
                    "entry_date": position.entry_time,
                    "exit_date": datetime.now(),
                })
                capital += sale_value

        # 计算回测指标
        return self._calculate_metrics(all_trades, equity_curve, capital)

    def _generate_signals_for_stock(self, df: pd.DataFrame, code: str, is_market_ok: bool) -> list:
        """为单只股票生成信号"""
        signals = []
        if len(df) < 35:
            return signals

        for i in range(30, len(df)):
            subset = df.iloc[:i+1].copy()
            signal = self.strategy.generate_signal(
                df=subset,
                stock_code=code,
                stock_name="",
                is_market_ok=is_market_ok,
            )

            if signal.signal != "hold":
                trade_date = df.iloc[i].get("trade_date", str(i))
                if isinstance(trade_date, str):
                    try:
                        trade_date = datetime.strptime(trade_date, "%Y%m%d")
                    except:
                        trade_date = datetime(2024, 1, 1) + timedelta(days=i)
                elif isinstance(trade_date, (int, float)):
                    trade_date = datetime(2024, 1, 1) + timedelta(days=int(i))

                signals.append({
                    "stock_code": code,
                    "signal": signal.signal,
                    "timestamp": trade_date,
                    "price": signal.price,
                    "stop_distance": signal.stop_distance,
                    "take_profit_distance": signal.take_profit_distance,
                    "position_level": signal.position_level,
                    "stock_name": signal.stock_name,
                })

        return signals

    def _calculate_metrics(self, trades: list, equity_curve: list, final_capital: dict) -> dict:
        """计算回测指标"""
        winning = [t for t in trades if t["pnl"] > 0]
        losing = [t for t in trades if t["pnl"] <= 0]

        win_rate = len(winning) / len(trades) if trades else 0
        avg_win = np.mean([t["pnl_pct"] for t in winning]) if winning else 0
        avg_loss = abs(np.mean([t["pnl_pct"] for t in losing])) if losing else 0
        profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0

        # 计算最大回撤
        max_dd = 0
        peak = equity_curve[0]
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak
            if dd > max_dd:
                max_dd = dd

        total_return = (final_capital - self.initial_capital) / self.initial_capital

        # 计算年化收益率（假设 120 天）
        days = 120
        annual_return = (1 + total_return) ** (365 / days) - 1

        # 计算夏普比率（简化）
        if len(equity_curve) > 1:
            returns = np.diff(equity_curve) / equity_curve[:-1]
            sharpe = np.sqrt(252) * np.mean(returns) / np.std(returns) if np.std(returns) > 0 else 0
        else:
            sharpe = 0

        return {
            "total_return": total_return,
            "annual_return": annual_return,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_loss_ratio": profit_loss_ratio,
            "max_drawdown": max_dd,
            "total_trades": len(trades),
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "sharpe_ratio": sharpe,
            "final_capital": final_capital,
            "trades": trades,
            "equity_curve": equity_curve,
        }


def print_result(result: dict):
    """打印回测结果"""
    print("\n" + "=" * 70)
    print("V3 实战策略回测结果")
    print("=" * 70)

    metrics = [
        ("总收益率", "total_return", True),
        ("年化收益率", "annual_return", True),
        ("胜率", "win_rate", True),
        ("平均盈利", "avg_win", True),
        ("平均亏损", "avg_loss", True),
        ("盈亏比", "profit_loss_ratio", False),
        ("最大回撤", "max_drawdown", True),
        ("夏普比率", "sharpe_ratio", False),
        ("交易次数", "total_trades", False),
        ("盈利次数", "winning_trades", False),
        ("亏损次数", "losing_trades", False),
        ("最终资金", "final_capital", False),
    ]

    for name, key, is_pct in metrics:
        val = result[key]
        if isinstance(val, float):
            if key == "final_capital":
                val_str = f"{val:,.2f} 元"
            elif is_pct:
                val_str = f"{val:.2%}"
            else:
                val_str = f"{val:.2f}"
        else:
            val_str = str(val)

        print(f"{name:<15} {val_str:>20}")

    print("=" * 70)


def main():
    """主函数"""
    print("=" * 70)
    print("V3 实战策略回测 - 针对 A 股实盘优化")
    print("=" * 70)

    # 配置
    STOCK_CODES = ["000001", "600000", "000002"]
    INITIAL_CAPITAL = 100000
    DAYS = 120

    collector = PriceCollector()

    print(f"\n初始资金：{INITIAL_CAPITAL:,.2f} 元")
    print(f"回测股票：{STOCK_CODES}")
    print(f"数据周期：{DAYS} 天")
    print("-" * 70)

    # 获取数据
    price_data = {}
    for code in STOCK_CODES:
        try:
            df = collector.get_kline(code, period="daily", limit=DAYS)
            if df is None or df.empty:
                print(f"[ERR] {code}: 无法获取数据")
                continue

            price_data[code] = df
            print(f"[OK] {code}: 获取到 {len(df)} 条数据")

        except Exception as e:
            print(f"[ERR] {code}: 错误 - {e}")

    if not price_data:
        print("\n[ERR] 没有获取到任何数据")
        return

    print("-" * 70)

    # 运行回测 - 先测试关闭大盘过滤的情况
    print("\n>>> 测试 1: 关闭大盘环境过滤")
    engine = V3BacktestEngine(initial_capital=INITIAL_CAPITAL)
    result = engine.run(price_data, use_market_filter=False)

    # 输出结果
    print_result(result)

    # 运行第二次 - 开启大盘过滤
    print("\n>>> 测试 2: 开启大盘环境过滤")
    engine2 = V3BacktestEngine(initial_capital=INITIAL_CAPITAL)
    result2 = engine2.run(price_data, use_market_filter=True)
    print_result(result2)

    # 与 V2 对比
    print("\n" + "=" * 70)
    print("V3 vs V2 对比参考")
    print("=" * 70)
    print("V2 策略 120 天回测参考:")
    print("  - 总收益率：约 156%")
    print("  - 胜率：约 46%")
    print("  - 盈亏比：约 3.6")
    print("  - 最大回撤：约 15%")
    print("\nV3 策略特点:")
    print("  + 增加大盘环境过滤，避免逆势操作")
    print("  + 动态仓位管理，风险更可控")
    print("  + 时间止损，减少资金占用")
    print("  + 阶梯式止盈，更灵活")
    print("=" * 70)


if __name__ == "__main__":
    main()
