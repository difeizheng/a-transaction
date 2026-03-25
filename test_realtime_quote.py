"""
测试新浪财经和腾讯财经实时行情
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.collectors.price_collector import PriceCollector
from src.config.settings import get_config

# 获取 Tushare token
tushare_token = get_config().get('data_sources', {}).get('tushare', {}).get('token')
collector = PriceCollector(tushare_token=tushare_token)

print("=" * 70)
print("实时行情数据源测试 - 新浪/腾讯/东方财富")
print("=" * 70)

test_stocks = ["000948", "601360", "300459"]

for code in test_stocks:
    print(f"\n【{code}】实时行情测试:")
    print("-" * 50)

    # 测试新浪财经
    data = collector._get_from_sina(code)
    if data:
        print(f"  新浪财经 [OK]: {data['name']} - 最新价：{data['price']:.2f}, 涨跌幅：{data['change_pct']:.2f}%")
    else:
        print(f"  新浪财经 [FAIL]")

    # 测试腾讯财经
    data = collector._get_from_tencent(code)
    if data:
        print(f"  腾讯财经 [OK]: {data['name']} - 最新价：{data['price']:.2f}, 涨跌幅：{data['change_pct']:.2f}%")
    else:
        print(f"  腾讯财经 [FAIL]")

    # 测试东方财富
    data = collector._get_from_em_api(code)
    if data:
        print(f"  东方财富 [OK]: {data['name']} - 最新价：{data['price']:.2f}, 涨跌幅：{data['change_pct']:.2f}%")
    else:
        print(f"  东方财富 [FAIL]")

    # 测试完整方法（优先级）
    data = collector.get_realtime_quote(code)
    if data:
        print(f"  >>> 最终采用 [{data.get('source', 'Unknown')}]: {data['price']:.2f} ({data['change_pct']:.2f}%)")
    else:
        print(f"  >>> 所有数据源失败")

print("\n" + "=" * 70)
print("测试完成")
print("=" * 70)
