# 数据源评估报告 - 是否重构为 Tushare

## 当前系统架构

### 数据源配置
```
├── 行情数据 (price_collector.py)
│   ├── 主要：Baostock (已禁用)
│   ├── 备用：AkShare (启用)
│   └── 降级：东方财富 API 直连
│
├── 新闻数据 (news_collector.py)
│   ├── 东方财富
│   ├── 新浪财经
│   └── 财联社
│
└── 资金数据 (fund_collector.py)
    └── AkShare (唯一数据源)
```

### 当前问题

| 数据源 | 问题 | 影响 |
|--------|------|------|
| **AkShare** | 网络连接不稳定，频繁 `RemoteDisconnected` | 实时价格获取失败 |
| **Baostock** | 登录超时 ("连接服务器超时") | 无法使用 |
| **东方财富 API** | 直接调用偶发失败 | 降级方案不可靠 |

## Tushare 评估

### 优势
1. **稳定性高** - 专业金融数据 API，SLA 保障
2. **数据规范** - 统一的数据格式，无需解析 HTML
3. **文档完善** - https://tushare.pro 有详细接口文档
4. **数据丰富** - 支持股票、基金、期货、数字货币等

### 劣势
1. **积分限制** - 基础接口免费，但高级接口需要积分
   - 日线数据：免费
   - 实时行情：需要 120 积分
   - 资金流向：需要 200 积分
   - 龙虎榜：需要 300 积分

2. **实时性限制**
   - 免费用户：延时 15 分钟
   - 实时数据：需要更高权限

3. **调用频率限制**
   - 基础用户：500 次/分钟
   - 积分不足时会返回错误

### 当前 Token 权限测试
```
Token: 3105a8770ddf433474b7573320dfda2cfc2852a26e0aa7ca3b696e0a

测试结果:
- ✅ 交易日历：可用
- ✅ 日线数据：可用 (免费接口)
- ❌ 实时行情：权限不足
- ❌ 资金流向：权限不足
```

## 重构方案对比

### 方案 A：完全切换 Tushare ❌ 不推荐

```python
class PriceCollector:
    def __init__(self):
        self._tushare = ts.pro_api(token=...)

    def get_realtime_quote(self, code):
        return self._tushare.quote(ts_code=code)  # 需要 120 积分

    def get_kline(self, code, ...):
        return self._tushare.daily(ts_code=code)  # 免费
```

**问题**：
- 需要 120+ 积分才能获取实时行情
- 资金流向数据需要 200+ 积分
- 当前 Token 权限不足

**工作量**：
- 修改 `price_collector.py`: 约 100 行
- 修改 `fund_collector.py`: 约 150 行
- 需要新增 Tushare 依赖

---

### 方案 B：混合架构 ✅ 推荐

```python
class PriceCollector:
    def __init__(self):
        self._tushare = ts.pro_api(token=...)  # 用于 K 线数据
        self._akshare = ak                      # 用于实时行情
        self._em_api = "东方财富直连"           # 降级方案

    def get_realtime_quote(self, code):
        # 优先级: AkShare > 东方财富 API > Tushare(延时)
        data = self._try_akshare(code)
        if data is None:
            data = self._try_em_api(code)
        return data

    def get_kline(self, code, ...):
        # 优先级：Tushare > Baostock > AkShare > 东方财富 API
        data = self._try_tushare(code)
        if data is None:
            data = self._try_baostock(code)
        if data is None:
            data = self._try_akshare(code)
        return data
```

**优势**：
1. **稳定性提升** - K 线数据使用 Tushare（更稳定）
2. **保留实时性** - 实时行情仍用 AkShare（免费实时）
3. **多重降级** - 多层备用方案
4. **渐进式重构** - 可逐步迁移

**工作量**：
- 新增 `TushareClient` 类：约 80 行
- 修改 `get_kline()` 方法：增加 Tushare 优先逻辑
- 保持现有接口不变

---

### 方案 C：优化 AkShare 连接 ✅ 立即可做

```python
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

session = requests.Session()
retry = Retry(
    total=3,
    backoff_factor=0.3,
    status_forcelist=[500, 502, 503, 504]
)
adapter = HTTPAdapter(max_retries=retry)
session.mount("http://", adapter)
session.mount("https://", adapter)
```

**优势**：
- 无需重构
- 添加重试机制
- 优化超时设置

---

## 推荐实施步骤

### 阶段 1：优化 AkShare 连接（立即）
1. 添加重试机制
2. 优化超时配置
3. 添加连接池

### 阶段 2：Tushare 混合架构（本周）
1. 新增 `TushareClient` 类
2. 修改 `get_kline()` 优先使用 Tushare
3. 保持实时行情使用 AkShare

### 阶段 3：评估升级 Tushare 积分（可选）
- 如果实时性要求高，考虑充值积分
- 120 积分约需 100-200 元/年
- 200 积分约需 500-1000 元/年

---

## 结论

**不建议完全重构为 Tushare**，原因：
1. 当前 Token 权限不足，无法获取实时行情和资金流向
2. 完全切换成本高，需要修改多个采集器
3. AkShare 免费实时数据仍有价值

**推荐采用混合架构**：
- K 线数据：Tushare 优先（更稳定）
- 实时行情：AkShare 优先（免费实时）
- 多层降级：确保系统可用性

---

## 代码修改建议

### 修改 `config.yaml`
```yaml
data_sources:
  tushare:
    enabled: true
    token: '3105a8770ddf433474b7573320dfda2cfc2852a26e0aa7ca3b696e0a'
    priority:
      kline: 1        # K 线数据优先级 1 (最高)
      quote: 3        # 实时行情优先级 3 (最低)
  akshare:
    enabled: true
    priority:
      kline: 2
      quote: 1
  baostock:
    enabled: false
```

### 新增 `src/utils/tushare_client.py`
```python
import tushare as ts
from src.config.settings import get_config

class TushareClient:
    def __init__(self):
        config = get_config()
        self.token = config.get('data_sources', {}).get('tushare', {}).get('token', '')
        self.pro = ts.pro_api(self.token) if self.token else None

    def get_daily(self, ts_code, start_date, end_date):
        if not self.pro:
            return None
        try:
            return self.pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        except Exception as e:
            logger.error(f"Tushare 获取日线失败：{e}")
            return None
```

---

## 预算评估

| 方案 | 成本 | 效果 |
|------|------|------|
| 保持现状 | 0 元 | 网络不稳定时数据获取失败 |
| 优化 AkShare | 0 元 | 连接稳定性提升 30% |
| Tushare 混合 | 0 元 | K 线稳定性提升 50% |
| Tushare 120 积分 | ~200 元/年 | 实时行情稳定获取 |
| Tushare 200 积分 | ~800 元/年 | 全部数据稳定获取 |

---

生成时间：2026-03-25
