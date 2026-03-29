"""
简单回测脚本 - 评估系统盈利能力
"""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from src.collectors.price_collector import PriceCollector
from src.analyzers.technical_analyzer import TechnicalAnalyzer
from src.analyzers.volatility_analyzer import VolatilityAnalyzer
from src.engine.signal_fusion import SignalFusionEngine
from src.engine.backtest import BacktestEngine, Trade

def run_backtest():
    """运行简单回测"""
    print("=" * 60)
    print("A 股监控系统 - 简单回测评估")
    print("=" * 60)

    # 配置
    STOCK_CODES = ["000001", "600000", "000002"]  # 平安银行、浦发银行、万科
    INITIAL_CAPITAL = 100000
    DAYS = 60  # 获取 60 天数据

    collector = PriceCollector()
    technical_analyzer = TechnicalAnalyzer()
    volatility_analyzer = VolatilityAnalyzer()
    signal_fusion = SignalFusionEngine(
        news_weight=0.30,
        technical_weight=0.25,
        fund_weight=0.20,
        volatility_weight=0.15,
        sentiment_weight=0.10,
    )
    backtest_engine = BacktestEngine(
        initial_capital=INITIAL_CAPITAL,
        commission_rate=0.0003,
        slippage=0.001,
    )

    print(f"\n初始资金：{INITIAL_CAPITAL:,.2f} 元")
    print(f"回测股票：{STOCK_CODES}")
    print(f"数据周期：{DAYS} 天")
    print("-" * 60)

    # 获取数据并生成信号
    price_data = {}
    signals = []

    for code in STOCK_CODES:
        try:
            df = collector.get_kline(code, period="daily", limit=DAYS)
            if df is None or df.empty:
                print(f"⚠️  {code}: 无法获取数据")
                continue

            price_data[code] = df
            print(f"[OK] {code}: 获取到 {len(df)} 条数据")

            # 生成模拟信号（基于技术分析和波动率）
            for i in range(20, len(df)):  # 从第 20 天开始，确保有足够数据计算指标
                subset_df = df.iloc[:i+1].copy()
                tech_signal = technical_analyzer.analyze(subset_df)
                vol_signal = volatility_analyzer.analyze(subset_df)

                # 计算波动率得分
                volatility_score = -vol_signal.atr_ratio * 10
                volatility_score = max(-1.0, min(1.0, volatility_score))

                # 简化信号逻辑：直接使用技术分析得分
                # 得分 > 0.2 买入，< -0.2 卖出
                tech_score = tech_signal.score
                current_price = float(subset_df["close"].iloc[-1])

                # 根据技术得分确定信号
                if tech_score > 0.2:
                    signal_type = "buy"
                elif tech_score < -0.2:
                    signal_type = "sell"
                else:
                    signal_type = "hold"

                # 记录信号
                trade_date = df.iloc[i].get("trade_date", str(i))
                if isinstance(trade_date, str):
                    try:
                        trade_date = datetime.strptime(trade_date, "%Y%m%d")
                    except:
                        trade_date = datetime.now()
                elif isinstance(trade_date, (int, float)):
                    # 如果是数字，使用索引作为天数偏移
                    from datetime import timedelta
                    base_date = datetime(2024, 1, 1)
                    trade_date = base_date + timedelta(days=int(i))

                signals.append({
                    "stock_code": code,
                    "signal": signal_type,
                    "timestamp": trade_date,
                    "price": current_price,
                    "tech_score": tech_score,
                })

            # 为每个股票添加一个最终的卖出信号来平仓
            if len(df) > 0:
                final_price = float(df["close"].iloc[-1])
                final_date = df.iloc[-1].get("trade_date", str(len(df)))
                if isinstance(final_date, str):
                    try:
                        final_date = datetime.strptime(final_date, "%Y%m%d")
                    except:
                        final_date = datetime.now()
                signals.append({
                    "stock_code": code,
                    "signal": "sell",  # 强制平仓
                    "timestamp": final_date,
                    "price": final_price,
                    "tech_score": 0,
                })

        except Exception as e:
            print(f"[ERR] {code}: 错误 - {e}")

    print(f"\n生成信号数：{len(signals)}")
    print("-" * 60)

    # 显示信号统计
    signal_types = {}
    for s in signals:
        sig = s["signal"]
        signal_types[sig] = signal_types.get(sig, 0) + 1
    print("信号类型统计:")
    for sig, count in signal_types.items():
        print(f"  {sig}: {count}")

    if not signals:
        print("⚠️  没有生成任何信号，无法回测")
        return

    # 运行回测
    from src.engine.decision_engine import DecisionEngine
    decision_engine = DecisionEngine(
        initial_capital=INITIAL_CAPITAL,
        stop_loss=0.08,
        take_profit=0.20,
    )

    result = backtest_engine.run(
        price_data=price_data,
        signals=signals,
        decision_engine=decision_engine,
        start_date=min(s["timestamp"] for s in signals),
        end_date=max(s["timestamp"] for s in signals),
    )

    # 输出结果
    print("\n" + "=" * 60)
    print("回测结果")
    print("=" * 60)

    metrics = result.to_dict()
    for key, value in metrics.items():
        print(f"  {key}: {value}")

    # 评估
    print("\n" + "=" * 60)
    print("评估结论")
    print("=" * 60)

    issues = []

    if result.win_rate < 0.4:
        issues.append(f"[!] 胜率偏低 ({result.win_rate:.1%})，建议优化信号生成逻辑")
    if result.profit_loss_ratio < 1.0:
        issues.append(f"[!] 盈亏比偏低 ({result.profit_loss_ratio:.2f})，建议调整止盈止损")
    if result.max_drawdown > 0.2:
        issues.append(f"[!] 最大回撤过大 ({result.max_drawdown:.1%})，建议加强风控")
    if result.sharpe_ratio < 0:
        issues.append(f"[!] 夏普比率为负 ({result.sharpe_ratio:.2f})，系统可能无法稳定盈利")

    if issues:
        print("\n需要改进的地方:")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("\n[OK] 系统表现良好，各项指标在合理范围内")

    if result.total_return > 0:
        print(f"\n[盈利] 回测盈利：{result.total_return:.2%}")
    else:
        print(f"\n[亏损] 回测亏损：{result.total_return:.2%}")

    # 保存交易明细
    if result.trade_details:
        print(f"\n交易明细 (共 {len(result.trade_details)} 笔):")
        print(f"  {'股票代码':<10} {'入场价':>8} {'出场价':>8} {'盈亏':>10} {'盈亏率':>10}")
        print("  " + "-" * 50)
        for trade in result.trade_details[:20]:  # 只显示前 20 笔
            print(f"  {trade.stock_code:<10} {trade.entry_price:>8.2f} {trade.exit_price:>8.2f} "
                  f"{trade.pnl:>10.2f} {trade.pnl_pct:>10.2%}")
        if len(result.trade_details) > 20:
            print(f"  ... 还有 {len(result.trade_details) - 20} 笔交易")

    print("\n" + "=" * 60)
    print("[!] 免责声明：回测结果仅供参考，不构成投资建议")
    print("   历史表现不代表未来收益，实盘交易需谨慎")
    print("=" * 60)


if __name__ == "__main__":
    run_backtest()
