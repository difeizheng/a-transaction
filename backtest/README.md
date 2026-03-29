# 回测脚本说明

## 目录结构

```
backtest/
├── backtest_unified.py    # 统一回测脚本（推荐使用）
├── backtest.py            # 原改进版回测（保留兼容）
└── archived/              # 历史版本（已废弃）
    ├── backtest_v2.py
    ├── backtest_v3.py
    ├── backtest_v4.py
    └── backtest_runner.py
```

## 使用方法

### 统一回测脚本（推荐）

支持通过参数选择不同策略版本：

```bash
# 使用改进版策略（默认）
python backtest/backtest_unified.py --strategy improved --days 120

# 使用 V3 策略
python backtest/backtest_unified.py --strategy v3 --days 90

# 使用 V4 策略
python backtest/backtest_unified.py --strategy v4 --days 120

# 自定义股票池
python backtest/backtest_unified.py --strategy v4 --stocks 000948,601360,300459

# 自定义初始资金
python backtest/backtest_unified.py --strategy improved --capital 200000

# 静默模式（不打印详细信息）
python backtest/backtest_unified.py --strategy v4 --quiet
```

### 参数说明

| 参数 | 说明 | 默认值 | 示例 |
|------|------|--------|------|
| `--strategy` | 策略名称 | improved | improved/v3/v4 |
| `--stocks` | 股票代码列表（逗号分隔） | 默认股票池 | 000948,601360,300459 |
| `--days` | 回测天数 | 120 | 90/120/180 |
| `--capital` | 初始资金 | 100000 | 50000/200000 |
| `--quiet` | 静默模式 | False | 添加此参数启用 |

### 支持的策略

| 策略名称 | 文件位置 | 说明 |
|----------|----------|------|
| `improved` | 内置 | 改进版策略（趋势过滤 + ADX 震荡过滤） |
| `v3` | `src/strategy/archived/v3_strategy.py` | V3 策略 |
| `v4` | `src/strategy/active/v4_strategy.py` | V4 深度优化策略（当前主策略） |

## 原回测脚本（兼容保留）

```bash
# 运行原改进版回测
python backtest/backtest.py
```

## 历史版本（已归档）

`backtest/archived/` 目录下的文件已废弃，仅供参考：
- `backtest_v2.py` - V2 策略回测
- `backtest_v3.py` - V3 策略回测
- `backtest_v4.py` - V4 策略回测
- `backtest_runner.py` - 旧版回测运行器

## 示例输出

```
============================================================
V4 策略回测
============================================================

初始资金：100,000.00 元
股票池：['000948', '601360', '300459', '002714', '600036']
数据周期：120 天
------------------------------------------------------------

回测 000948 南天信息...
  生成 8 个信号

回测 601360 三六零...
  生成 3 个信号

...

============================================================
回测结果
============================================================
总收益率：30.10%
年化收益率：194.19%
最大回撤：15.76%
夏普比率：13.79
总交易次数：11
胜率：45.5%
盈亏比：3.49
最终资金：130,100.00 元
总盈亏：30,100.00 元
```

## 注意事项

1. 确保已安装所有依赖：`pandas`, `numpy`, `apscheduler` 等
2. 回测结果仅供参考，不代表实盘表现
3. 历史数据来源于 Tushare/Baostock/AkShare
4. 建议先在小资金上验证策略有效性
