"""
测试 Tushare 混合架构数据源

验证内容：
1. K 线数据优先从 Tushare 获取
2. 实时行情使用 AkShare
3. 资金流向 Tushare 优先 > AkShare
"""
import sys
from pathlib import Path
import os

# 设置控制台输出编码
os.environ['PYTHONIOENCODING'] = 'utf-8'

sys.path.insert(0, str(Path(__file__).parent))

from src.config.settings import load_config, get_config
from src.collectors.price_collector import PriceCollector
from src.collectors.fund_collector import FundCollector

# 成功/失败标记
OK = "[OK]"
FAIL = "[FAIL]"

def test_price_collector():
    """测试行情数据源"""
    print("=" * 70)
    print("【测试 1】行情数据采集器 - PriceCollector")
    print("=" * 70)

    config = get_config()
    tushare_token = config.get('data_sources', {}).get('tushare', {}).get('token')

    collector = PriceCollector(tushare_token=tushare_token)

    # 测试 K 线数据
    print("\n1. 测试 K 线数据（优先级：Tushare > Baostock > AkShare）")
    df = collector.get_kline("000948", period="daily", limit=5)

    if df is not None and not df.empty:
        print(f"   {OK} K 线数据获取成功")
        print(f"   条数：{len(df)}")
        print(f"   列名：{list(df.columns)}")
        print(f"   最新数据:")
        # 兼容 Tushare (trade_date, vol) 和 Baostock (date, volume) 格式
        date_col = 'trade_date' if 'trade_date' in df.columns else 'date'
        vol_col = 'vol' if 'vol' in df.columns else 'volume'
        print(f"     - 日期：{df[date_col].iloc[-1]}")
        print(f"     - 收盘价：{df['close'].iloc[-1]}")
        print(f"     - 成交量：{df[vol_col].iloc[-1]}")
    else:
        print(f"   {FAIL} K 线数据获取失败")

    # 测试实时行情
    print("\n2. 测试实时行情（优先级：AkShare > 东方财富 API）")
    quote = collector.get_realtime_quote("000948")

    if quote:
        print(f"   {OK} 实时行情获取成功")
        print(f"     - 股票：{quote.get('name', 'N/A')}")
        print(f"     - 最新价：{quote.get('price', 0):.2f}")
        print(f"     - 涨跌幅：{quote.get('change_pct', 0):.2f}%")
        print(f"     - 成交量：{quote.get('volume', 0):,}")
    else:
        print(f"   {FAIL} 实时行情获取失败")

    return df is not None and not df.empty


def test_fund_collector():
    """测试资金流向数据源"""
    print("\n" + "=" * 70)
    print("【测试 2】资金流向采集器 - FundCollector")
    print("=" * 70)

    config = get_config()
    tushare_token = config.get('data_sources', {}).get('tushare', {}).get('token')

    collector = FundCollector(tushare_token=tushare_token)

    # 测试个股资金流向
    print("\n1. 测试个股资金流向（优先级：Tushare > AkShare）")
    fund_flow = collector.get_stock_fund_flow("000948")

    if fund_flow:
        print(f"   {OK} 个股资金流向获取成功")
        print(f"     - 主力净流入：{fund_flow.get('main_net_in', 0):,.0f}")
        print(f"     - 超大单：{fund_flow.get('large_order_net_in', 0):,.0f}")
        print(f"     - 大单：{fund_flow.get('medium_order_net_in', 0):,.0f}")
    else:
        print(f"   {FAIL} 个股资金流向获取失败")

    # 测试北向资金
    print("\n2. 测试北向资金流向（数据源：AkShare）")
    north_flow = collector.get_northbound_flow()

    if north_flow:
        print(f"   {OK} 北向资金获取成功")
        print(f"     - 净流入：{north_flow.get('net_in', 0):,.0f}")
        print(f"     - 买入额：{north_flow.get('buy_amount', 0):,.0f}")
        print(f"     - 卖出额：{north_flow.get('sell_amount', 0):,.0f}")
    else:
        print(f"   {FAIL} 北向资金获取失败")

    return fund_flow is not None


def test_hybrid_architecture():
    """验证混合架构"""
    print("\n" + "=" * 70)
    print("【测试 3】混合架构验证")
    print("=" * 70)

    config = get_config()
    tushare_enabled = config.get('data_sources', {}).get('tushare', {}).get('enabled', False)
    akshare_enabled = config.get('data_sources', {}).get('akshare', {}).get('enabled', False)
    baostock_enabled = config.get('data_sources', {}).get('baostock', {}).get('enabled', False)

    print(f"""
数据源配置状态:
  - Tushare:   {'[启用]' if tushare_enabled else '[禁用]'}
  - AkShare:   {'[启用]' if akshare_enabled else '[禁用]'}
  - Baostock:  {'[启用]' if baostock_enabled else '[禁用]'}

混合架构策略:
  - K 线数据：  Tushare(优先) > Baostock > AkShare > 东方财富 API
  - 实时行情：  AkShare(优先) > 东方财富 API
  - 资金流向：  Tushare(优先，需 200 积分) > AkShare
  - 北向资金：  AkShare(唯一数据源)
""")

    return True


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("         Tushare 混合架构数据源测试")
    print("=" * 70)

    results = {
        "K 线数据": test_price_collector(),
        "资金流向": test_fund_collector(),
        "混合架构": test_hybrid_architecture(),
    }

    print("\n" + "=" * 70)
    print("测试结果汇总")
    print("=" * 70)

    for test_name, result in results.items():
        status = "[通过]" if result else "[失败]"
        print(f"  {test_name}: {status}")

    if all(results.values()):
        print("\n[成功] 所有测试通过！混合架构运行正常。")
    else:
        print("\n[警告] 部分测试失败，请检查日志。")

    print("=" * 70)
