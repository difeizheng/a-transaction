"""
验证 Tushare 混合架构 - 简单测试
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.utils.tushare_client import TushareClient

# 测试 Tushare Client
token = "3105a8770ddf433474b7573320dfda2cfc2852a26e0aa7ca3b696e0a"
client = TushareClient(token=token)

print("=" * 60)
print("Tushare Client 测试")
print("=" * 60)

# 测试日线数据
print("\n1. 测试日线数据 (000948.SZ)...")
df = client.get_daily_kline("000948.SZ", limit=5)

if df is not None and not df.empty:
    print(f"   成功！获取到 {len(df)} 条数据")
    print(f"   列名：{list(df.columns)}")
    print(f"   最新数据：{df.iloc[-1]['trade_date']} - 收盘 {df.iloc[-1]['close']}")
else:
    print("   失败！返回空数据")

# 测试标准化代码
print("\n2. 测试代码标准化...")
print(f"   000948 -> {client._normalize_ts_code('000948')}")
print(f"   600000 -> {client._normalize_ts_code('600000')}")
print(f"   000948.SZ -> {client._normalize_ts_code('000948.SZ')}")

print("\n" + "=" * 60)
