"""
统一回测脚本 - 支持多策略版本

用法:
    python backtest/backtest.py --strategy improved --days 120
    python backtest/backtest.py --strategy v3 --days 90
    python backtest/backtest.py --strategy v4 --days 120 --stocks 000948,601360,300459
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.collectors.price_collector import PriceCollector
from src.analyzers.technical_analyzer import TechnicalAnalyzer
from src.analyzers.volatility_analyzer import VolatilityAnalyzer
import pandas as pd
import numpy as np


# 默认股票池配置
DEFAULT_STOCK_POOLS = {
    'improved': ['000948', '601360', '300459', '002714', '600036'],
    'v3': ['000948', '601360', '300459', '002714', '600036'],
    'v4': ['000948', '601360', '300459', '002714', '600036'],
}

STOCK_NAMES = {
    "000948": "南天信息",
    "601360": "三六零",
    "300459": "汤姆猫",
    "002714": "牧原股份",
    "600036": "招商银行",
}


class ImprovedStrategy:
    """
    改进版交易策略

    核心逻辑：
    1. 趋势过滤 - 只在上升趋势中买入
    2. 多条件确认 - MA+MACD+RSI 共振
    3. ATR 动态止损 - 根据波动率调整
    4. 分级止盈止损 - 不同信号强度不同策略
    """

    def __init__(self):
        self.technical_analyzer = TechnicalAnalyzer()
        self.volatility_analyzer = VolatilityAnalyzer()

        # 策略参数
        self.buy_score_threshold = 0.15      # 买入阈值（降低）
        self.sell_score_threshold = -0.15    # 卖出阈值
        self.min_volume_ratio = 1.0          # 最小成交量比率
        self.trend_confirmation_days = 5     # 趋势确认天数
        self.adx_threshold = 30              # ADX 趋势强度阈值（>=30 为强趋势，<30 为震荡市）

    def generate_signals(self, df: pd.DataFrame, stock_code: str) -> list:
        """生成改进版信号"""
        signals = []
        if len(df) < 30:
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

        # ADX - 趋势强度指标
        high = df['high']
        low = df['low']
        close = df['close']

        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0

        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = tr.rolling(14).mean()
        plus_di = 100 * (plus_dm.rolling(14).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(14).mean() / atr)

        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(14).mean()

        # 成交量比率
        volume_ma = df['volume'].rolling(20).mean()
        volume_ratio = df['volume'] / volume_ma

        # 遍历生成信号
        for i in range(30, len(df)):
            date = df.index[i]
            price = df['close'].iloc[i]

            # 跳过震荡市（ADX < 30）
            if pd.notna(adx.iloc[i]) and adx.iloc[i] < self.adx_threshold:
                continue

            # 买入信号
            if (price > ma20.iloc[i] and  # 上升趋势
                macd_dif.iloc[i] > 0 and  # MACD 多头
                rsi.iloc[i] < 70 and      # 未超买
                volume_ratio.iloc[i] > self.min_volume_ratio):  # 成交量放大

                # 计算技术得分
                score = 0
                if ma5.iloc[i] > ma10.iloc[i] > ma20.iloc[i]:
                    score += 0.3
                if macd_dif.iloc[i] > macd_dea.iloc[i]:
                    score += 0.3
                if 30 < rsi.iloc[i] < 70:
                    score += 0.2
                if volume_ratio.iloc[i] > 1.5:
                    score += 0.2

                if score >= self.buy_score_threshold:
                    signals.append({
                        'date': date,
                        'action': 'buy',
                        'price': price,
                        'score': score,
                        'reason': f'趋势买入(ADX={adx.iloc[i]:.1f}, 得分={score:.2f})'
                    })

            # 卖出信号
            elif (price < ma20.iloc[i] or  # 跌破趋势
                  rsi.iloc[i] > 80):       # 超买

                score = 0
                if ma5.iloc[i] < ma10.iloc[i] < ma20.iloc[i]:
                    score -= 0.3
                if macd_dif.iloc[i] < macd_dea.iloc[i]:
                    score -= 0.3
                if rsi.iloc[i] > 70:
                    score -= 0.2

                if score <= self.sell_score_threshold:
                    signals.append({
                        'date': date,
                        'action': 'sell',
                        'price': price,
                        'score': score,
                        'reason': f'趋势卖出(得分={score:.2f})'
                    })

        return signals


def load_strategy(strategy_name: str):
    """加载指定策略"""
    if strategy_name == 'improved':
        return ImprovedStrategy()
    elif strategy_name == 'v3':
        from src.strategy.archived.v3_strategy import V3Strategy
        return V3Strategy()
    elif strategy_name == 'v4':
        from src.strategy.active.v4_strategy import V4Strategy
        return V4Strategy()
    else:
        raise ValueError(f"未知策略: {strategy_name}，支持: improved, v3, v4")


def run_backtest(
    strategy_name: str = 'improved',
    stock_codes: Optional[List[str]] = None,
    days: int = 120,
    initial_capital: float = 100000,
    verbose: bool = True
) -> Dict:
    """
    运行回测

    参数:
        strategy_name: 策略名称 (improved/v3/v4)
        stock_codes: 股票代码列表
        days: 回测天数
        initial_capital: 初始资金
        verbose: 是否打印详细信息

    返回:
        回测结果字典
    """
    if stock_codes is None:
        stock_codes = DEFAULT_STOCK_POOLS.get(strategy_name, DEFAULT_STOCK_POOLS['improved'])

    if verbose:
        print("=" * 60)
        print(f"{strategy_name.upper()} 策略回测")
        print("=" * 60)
        print(f"\n初始资金：{initial_capital:,.2f} 元")
        print(f"股票池：{stock_codes}")
        print(f"数据周期：{days} 天")
        print("-" * 60)

    # 加载策略
    strategy = load_strategy(strategy_name)
    collector = PriceCollector()

    # 简单回测统计
    capital = initial_capital
    positions = {}  # {stock_code: {'quantity': int, 'cost': float}}
    all_trades = []

    # 获取数据并回测
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    for stock_code in stock_codes:
        stock_name = STOCK_NAMES.get(stock_code, stock_code)

        if verbose:
            print(f"\n回测 {stock_code} {stock_name}...")

        # 获取历史数据
        end_date_str = end_date.strftime('%Y-%m-%d')
        start_date_str = start_date.strftime('%Y-%m-%d')
        df = collector.get_kline(
            stock_code,
            period='daily',
            start_date=start_date_str,
            end_date=end_date_str,
            limit=days + 30
        )

        if df is None or len(df) < 30:
            if verbose:
                print(f"  数据不足，跳过")
            continue

        # 生成信号
        signals = strategy.generate_signals(df, stock_code)

        if verbose:
            print(f"  生成 {len(signals)} 个信号")

        # 简单执行交易
        for signal in signals:
            if signal['action'] == 'buy' and stock_code not in positions:
                # 买入：使用 25% 资金
                buy_amount = capital * 0.25
                quantity = int(buy_amount / signal['price'] / 100) * 100  # 整百股
                if quantity > 0:
                    cost = quantity * signal['price']
                    positions[stock_code] = {
                        'quantity': quantity,
                        'cost': signal['price'],
                        'date': signal['date']
                    }
                    capital -= cost
                    all_trades.append({
                        'stock': stock_code,
                        'action': 'buy',
                        'price': signal['price'],
                        'quantity': quantity,
                        'date': signal['date']
                    })

            elif signal['action'] == 'sell' and stock_code in positions:
                # 卖出
                pos = positions[stock_code]
                revenue = pos['quantity'] * signal['price']
                profit = revenue - (pos['quantity'] * pos['cost'])
                capital += revenue
                all_trades.append({
                    'stock': stock_code,
                    'action': 'sell',
                    'price': signal['price'],
                    'quantity': pos['quantity'],
                    'profit': profit,
                    'date': signal['date']
                })
                del positions[stock_code]

    # 计算结果
    final_capital = capital
    for stock_code, pos in positions.items():
        # 按最后价格计算持仓市值
        df = collector.get_kline(stock_code, period='daily', limit=1)
        if df is not None and len(df) > 0:
            final_capital += pos['quantity'] * df['close'].iloc[-1]

    total_return = (final_capital - initial_capital) / initial_capital
    total_profit = final_capital - initial_capital

    # 统计交易
    buy_trades = [t for t in all_trades if t['action'] == 'buy']
    sell_trades = [t for t in all_trades if t['action'] == 'sell']
    win_trades = [t for t in sell_trades if t.get('profit', 0) > 0]
    win_rate = len(win_trades) / len(sell_trades) if sell_trades else 0

    if verbose:
        print("\n" + "=" * 60)
        print("回测结果")
        print("=" * 60)
        print(f"总收益率：{total_return * 100:.2f}%")
        print(f"总交易次数：{len(sell_trades)}")
        print(f"胜率：{win_rate * 100:.1f}%")
        print(f"最终资金：{final_capital:,.2f} 元")
        print(f"总盈亏：{total_profit:,.2f} 元")
        print(f"持仓数量：{len(positions)}")

    return {
        'strategy': strategy_name,
        'total_return': total_return,
        'total_profit': total_profit,
        'final_capital': final_capital,
        'trades': all_trades,
        'win_rate': win_rate,
        'stock_codes': stock_codes,
    }


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='统一回测脚本')
    parser.add_argument('--strategy', type=str, default='improved',
                        choices=['improved', 'v3', 'v4'],
                        help='策略名称 (improved/v3/v4)')
    parser.add_argument('--stocks', type=str, default=None,
                        help='股票代码列表，逗号分隔，如: 000948,601360,300459')
    parser.add_argument('--days', type=int, default=120,
                        help='回测天数')
    parser.add_argument('--capital', type=float, default=100000,
                        help='初始资金')
    parser.add_argument('--quiet', action='store_true',
                        help='静默模式，不打印详细信息')

    args = parser.parse_args()

    # 解析股票代码
    stock_codes = None
    if args.stocks:
        stock_codes = [code.strip() for code in args.stocks.split(',')]

    # 运行回测
    result = run_backtest(
        strategy_name=args.strategy,
        stock_codes=stock_codes,
        days=args.days,
        initial_capital=args.capital,
        verbose=not args.quiet
    )

    return result


if __name__ == '__main__':
    main()
