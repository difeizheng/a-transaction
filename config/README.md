# 配置管理

## 目录结构

```
config/
├── base.yaml         # 基础配置（所有环境共享）
├── development.yaml  # 开发环境覆盖配置
├── production.yaml   # 生产环境覆盖配置
├── schema.yaml       # 配置验证规则（JSON Schema）
└── README.md         # 本文档
```

## 使用方法

### 基本用法

```python
from src.config.config_loader import load_config, get_config

# 加载配置（自动检测环境）
config = load_config()

# 指定环境
config = load_config(env='production')

# 获取配置值
initial_capital = get_config('trading.initial_capital')
log_level = get_config('system.log_level')

# 获取嵌套配置
stock_codes = get_config('stock_pool.custom_codes')
```

### 环境变量

配置支持环境变量，使用 `${VAR_NAME}` 或 `${VAR_NAME:default}` 格式：

```yaml
# config/base.yaml
data_sources:
  tushare:
    token: ${TUSHARE_TOKEN}  # 从环境变量读取

notification:
  dingtalk_webhook: ${DINGTALK_WEBHOOK}
  # 带默认值
  hook_url: ${HOOK_URL:}
```

设置环境变量：

```bash
# Linux/Mac
export TUSHARE_TOKEN="your_token_here"
export DINGTALK_WEBHOOK="https://..."

# Windows
set TUSHARE_TOKEN=your_token_here

# 或通过 .env 文件（需要安装 python-dotenv）
echo "TUSHARE_TOKEN=your_token" > .env
```

### 环境切换

方式 1：通过环境变量
```bash
export ENV=production
python main.py
```

方式 2：通过代码指定
```python
load_config(env='production')
```

## 配置说明

### 基础配置 (base.yaml)
- 所有环境共享的默认配置
- 包含完整的配置项默认值

### 开发环境 (development.yaml)
- 覆盖 base.yaml 中的配置
- 特点：
  - 日志级别：DEBUG
  - 监控间隔：60 秒
  - 通知只输出到控制台
  - 使用较小资金和股票池

### 生产环境 (production.yaml)
- 覆盖 base.yaml 中的配置
- 特点：
  - 日志级别：INFO
  - 监控间隔：300 秒
  - 完整通知配置
  - 使用正式资金和股票池

## 配置验证

加载配置时会自动验证：
- 必需项检查：system, data_sources, trading, stock_pool, monitor, notification
- 类型检查：数值范围、字符串格式
- 股票代码格式：必须为 6 位数字

验证失败会抛出异常：
```python
try:
    config = load_config('production')
except ValueError as e:
    print(f"配置错误: {e}")
```

## 配置热更新

运行时修改配置：

```python
from src.config.config_loader import load_config, set_config

# 加载配置
config = load_config()

# 运行时修改配置
set_config('monitor.interval', 60)
set_config('trading.initial_capital', 50000)

# 立即生效
print(get_config('monitor.interval'))  # 60
```

## 迁移旧配置

旧 `config.yaml` 中的所有配置项已被拆分到：
- `config/base.yaml` - 基础配置
- `config/development.yaml` - 开发环境
- `config/production.yaml` - 生产环境

建议：
1. 先保留旧的 `config.yaml` 作为参考
2. 逐项迁移到新的分层配置
3. 测试通过后删除旧配置

## 常用配置项

| 配置项 | 说明 | 示例 |
|--------|------|------|
| system.log_level | 日志级别 | DEBUG/INFO/WARNING |
| system.db_path | 数据库路径 | data/trading.db |
| trading.initial_capital | 初始资金 | 20000 |
| trading.max_position_per_stock | 单股最大仓位 | 0.25 |
| trading.stop_loss | 止损比例 | 0.08 |
| trading.take_profit | 止盈比例 | 0.2 |
| stock_pool.custom_codes | 股票代码 | ['000948', '300459'] |
| monitor.interval | 监控间隔(秒) | 300 |
| notification.enabled | 是否启用通知 | true |
| data_sources.tushare.enabled | 启用 Tushare | true |