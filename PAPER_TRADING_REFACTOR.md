# Paper Trading 重构方案

**目标**: 将现有信号生成系统升级为具备闭环验证能力的模拟实盘交易系统
**日期**: 2026-03-30
**当前问题**: 系统只生成信号，从不执行和记录模拟交易；DB 表存在但从未写入

---

## 一、现状诊断

### 根本问题

```
当前架构（断链）:
数据采集 → 多因子分析 → 信号生成 → 控制台/通知  ← 链路在此中断

目标架构（闭环）:
数据采集 → 多因子分析 → 信号生成 → Paper Trading Engine → DB 持久化
     ↑                                      ↓                    ↓
  每300秒市价更新                       止盈止损执行           Web 实时 P&L
```

### 已确认的具体缺陷

| 缺陷 | 位置 | 说明 |
|------|------|------|
| 持仓仅在内存 | `improved_strategy.py:124` | `self.positions` 是普通 dict，重启即丢失 |
| 信号从不写 DB | `main.py` run_once() | `db.add_signal()` 已定义但从未调用 |
| 模拟持仓表为空 | `db.py` | `simulated_positions` 表存在，INSERT 为 0 |
| 模拟交易表为空 | `db.py` | `simulated_trades` 表存在，INSERT 为 0 |
| 止损仅内存计算 | `improved_strategy.py:477` | `check_exit()` 结果不持久化 |
| Web 显示空数据 | `web_dashboard_unified.py:294` | SELECT 返回空列表 |

---

## 二、重构范围

### 新建文件

| 文件 | 职责 |
|------|------|
| `src/engine/paper_trader.py` | 核心撮合引擎：虚拟账户、下单、持仓更新 |
| `src/engine/forward_validator.py` | 前向验证统计：实时胜率、夏普、回撤等 |
| `src/utils/benchmark.py` | 沪深300基准对比 |

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `src/utils/db.py` | 激活写入逻辑；新增 `equity_curve` 表 |
| `main.py` | `run_once()` 接入 PaperTrader；写入信号记录 |
| `web/pages/simulation.py` 或对应页面 | 激活模拟交易 Web 展示 |
| `web_dashboard_unified.py` | 净值曲线、前向统计面板 |

### 不修改（复用）

- `src/collectors/` — 数据采集层（稳定）
- `src/analyzers/` — 分析层（稳定）
- `src/engine/signal_fusion.py` — 信号融合（稳定）
- `src/engine/risk_manager.py` — 风险管理（稳定）
- `src/engine/decision_engine.py` — 决策引擎（稳定）
- `src/utils/notification.py` — 通知系统（稳定）

---

## 三、执行计划

### P0：核心链路（预计 1-2 天）

#### P0-1：新建 `src/engine/paper_trader.py`

**数据结构**:
```python
@dataclass
class VirtualPosition:
    stock_code: str
    stock_name: str
    quantity: int           # 持股数量（100的整数倍）
    avg_cost: float         # 平均成本（含手续费）
    entry_price: float      # 入场价（含滑点）
    entry_time: datetime
    stop_loss_price: float  # 当前止损价（动态更新）
    take_profit_price: float
    highest_price: float    # 持仓期最高价（用于追踪止损）
    signal_type: str        # buy / strong_buy
    signal_score: float
    db_id: int              # 对应 simulated_positions.id

@dataclass
class VirtualAccount:
    initial_capital: float
    cash: float
    positions: Dict[str, VirtualPosition]
    total_equity: float     # cash + 持仓市值
    peak_equity: float      # 历史最高净值
```

**核心方法**:
```python
class PaperTrader:
    def execute_buy(stock_code, stock_name, signal_price, signal_type,
                    signal_score, quantity, stop_loss_price,
                    take_profit_price, reason) -> bool
        # 1. 检查现金是否足够（含手续费）
        # 2. 计算实际买入价：signal_price * (1 + SLIPPAGE_BUY)
        # 3. 计算手续费：max(amount * 0.0003, 5.0)
        # 4. 更新 cash，创建 VirtualPosition
        # 5. 写 DB：INSERT simulated_positions，INSERT simulated_trades
        # 6. 返回成功/失败

    def execute_sell(stock_code, current_price, reason) -> float
        # 1. 获取持仓
        # 2. 计算实际卖出价：current_price * (1 - SLIPPAGE_SELL)
        # 3. 计算费用：手续费 + 印花税(0.001) + 过户费(沪市0.00006)
        # 4. 计算实现 PnL
        # 5. 更新 cash，删除 VirtualPosition
        # 6. 写 DB：UPDATE simulated_positions(status=closed)，INSERT simulated_trades
        # 7. 返回 realized_pnl

    def update_prices(price_dict: Dict[str, float])
        # 更新所有持仓的 current_price，highest_price
        # 更新追踪止损价（若最高价上涨则上移止损）
        # 计算 total_equity，更新 peak_equity

    def check_stops() -> List[str]
        # 遍历所有持仓：
        #   - current_price <= stop_loss_price → execute_sell(reason='stop_loss')
        #   - current_price >= take_profit_price → execute_sell(reason='take_profit')
        # 返回触发止损的股票列表

    def apply_signal_sell(stock_code, current_price, signal_score)
        # 策略发出 sell 信号时调用
        # execute_sell(reason='signal')

    def save_equity_snapshot()
        # 写 DB：INSERT equity_curve (timestamp, total_equity, cash, position_value)

    def get_stats() -> Dict
        # 从 DB 读取所有已平仓交易，计算：
        # 胜率、平均盈亏、盈亏比、期望值、夏普、最大回撤
```

**成本模型常量**:
```python
SLIPPAGE_BUY    = 0.0005   # 买入滑点 0.05%
SLIPPAGE_SELL   = 0.0005   # 卖出滑点 0.05%
COMMISSION_RATE = 0.0003   # 手续费率万三
COMMISSION_MIN  = 5.0      # 最低手续费 5元
STAMP_TAX       = 0.001    # 印花税千一（卖出）
TRANSFER_FEE    = 0.00006  # 过户费（沪市，双向）
```

#### P0-2：修改 `src/utils/db.py`

新增方法和表：

```sql
-- 新增净值曲线表
CREATE TABLE IF NOT EXISTS equity_curve (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    total_equity REAL NOT NULL,
    cash        REAL NOT NULL,
    position_value REAL NOT NULL,
    daily_return REAL DEFAULT 0.0
);

-- 激活已存在的表写入：
-- simulated_positions: 现有表结构已满足需求
-- simulated_trades: 现有表结构已满足需求，需增加 commission 字段
```

新增 DB 方法：
- `insert_simulated_position(...)` → 写入持仓记录，返回 id
- `update_simulated_position_exit(id, exit_price, exit_date, exit_reason, profit_loss)` → 平仓更新
- `insert_simulated_trade(...)` → 写入交易流水
- `insert_equity_snapshot(...)` → 写入净值快照
- `get_closed_trades()` → 读取所有已平仓记录用于统计
- `get_open_positions()` → 读取当前持仓

#### P0-3：修改 `main.py`

在 `AStockMonitor.__init__()` 中初始化 PaperTrader：
```python
from src.engine.paper_trader import PaperTrader
self.paper_trader = PaperTrader(
    initial_capital=self.settings.initial_capital,
    db=self.db
)
```

在 `run_once()` 中：
```python
# 1. 信号生成后，替换原来的内存操作
for fusion_result in fusion_results:
    signal = fusion_result.signal

    # 写入信号记录（当前从未调用）
    self.db.add_signal(stock_code, signal, fusion_result.total_score, ...)

    if signal in ["buy", "strong_buy"]:
        quantity = self._calc_quantity(fusion_result.current_price, signal)
        if quantity > 0 and stock_code not in self.paper_trader.positions:
            self.paper_trader.execute_buy(
                stock_code=stock_code,
                stock_name=fusion_result.stock_name,
                signal_price=fusion_result.current_price,
                signal_type=signal,
                signal_score=fusion_result.total_score,
                quantity=quantity,
                stop_loss_price=stop_loss,
                take_profit_price=take_profit,
                reason=reason_text
            )

    elif signal in ["sell", "strong_sell"]:
        if stock_code in self.paper_trader.positions:
            self.paper_trader.apply_signal_sell(
                stock_code, fusion_result.current_price, fusion_result.total_score
            )

# 2. 每轮结束：更新价格，检查止损，保存净值快照
current_prices = {r.stock_code: r.current_price for r in fusion_results}
self.paper_trader.update_prices(current_prices)
triggered = self.paper_trader.check_stops()
self.paper_trader.save_equity_snapshot()
```

---

### P1：前向验证统计（预计 0.5 天）

#### P1-1：新建 `src/engine/forward_validator.py`

```python
class ForwardValidator:
    def compute_stats(closed_trades: List[Dict]) -> ForwardStats:
        # 基于 DB 中所有 simulated_trades(type=sell) 计算：
        # - total_trades, win_trades, loss_trades
        # - win_rate（对比回测 50.4%）
        # - avg_win, avg_loss, profit_loss_ratio
        # - expectancy = win_rate * avg_win - (1-win_rate) * avg_loss
        # - max_consecutive_wins, max_consecutive_losses
        # - 持仓时间分布

    def compute_sharpe(equity_curve: List[Dict]) -> float:
        # 基于 equity_curve 表计算日收益率序列
        # Sharpe = mean(returns) / std(returns) * sqrt(252)

    def compute_max_drawdown(equity_curve: List[Dict]) -> float:
        # 基于净值曲线计算最大回撤

    def compare_with_backtest(forward_stats, backtest_stats) -> Dict:
        # 对比前向测试 vs 历史回测的关键指标差异
        # 预警：若实际胜率 < 回测胜率 * 0.8，触发告警
```

---

### P2：真实成本模型（含 P0 实现，无需额外文件）

已在 P0-1 的 `PaperTrader` 中包含：
- 买卖滑点（各 0.05%）
- A 股真实费率（手续费万三、印花税千一、过户费）
- 涨跌停处理：买入信号若当日涨停则跳过，记录 `skipped_due_to_limit_up`

---

### P3：Web 面板激活（预计 0.5 天）

修改 `web_dashboard_unified.py` 模拟交易页面，展示：

```
┌─────────────────────────────────────────────────────────┐
│  虚拟账户概览                                              │
│  初始资金 ¥20,000 | 当前净值 ¥21,340 | 累计收益 +6.7%    │
│  现金 ¥12,500     | 持仓市值 ¥8,840  | 今日盈亏 +¥120    │
└─────────────────────────────────────────────────────────┘

左：当前持仓表（股票/成本/现价/盈亏%/止损价/持仓天数）
右：净值曲线折线图（策略净值 vs 沪深300基准，起始100化）

┌──────────────────────────────────────────────────────────┐
│  前向验证统计（真实交易数据，非历史回测）                     │
│  实际胜率 53.2% | 回测胜率 50.4% | 差异 +2.8%             │
│  交易次数 28    | 盈利 15       | 亏损 13                 │
│  最大回撤 4.2%  | 夏普比率 1.21 | 期望值 0.0032           │
└──────────────────────────────────────────────────────────┘

历史交易记录表（可按盈亏/日期/股票筛选）
```

---

## 四、关键执行检查点

### 检查点 1：DB 写入验证（P0 完成后）

```bash
# 运行一轮监控后，验证数据库写入
python -c "
import sqlite3
conn = sqlite3.connect('data/trading.db')
# 验证模拟持仓有记录
print('持仓记录数:', conn.execute('SELECT COUNT(*) FROM simulated_positions').fetchone()[0])
# 验证模拟交易有记录
print('交易记录数:', conn.execute('SELECT COUNT(*) FROM simulated_trades').fetchone()[0])
# 验证净值快照有记录
print('净值快照数:', conn.execute('SELECT COUNT(*) FROM equity_curve').fetchone()[0])
# 验证信号记录有记录
print('信号记录数:', conn.execute('SELECT COUNT(*) FROM trading_signals').fetchone()[0])
conn.close()
"
# 预期：4个数字均 > 0
```

### 检查点 2：账户状态一致性验证

```bash
python -c "
import sqlite3, json
conn = sqlite3.connect('data/trading.db')
# 验证账户余额 = 初始资金 - 买入支出 + 卖出收入
trades = conn.execute('SELECT trade_type, amount FROM simulated_trades').fetchall()
initial = 20000.0
cash = initial
for t_type, amount in trades:
    if t_type == 'buy':
        cash -= amount
    elif t_type == 'sell':
        cash += amount
print(f'理论现金: {cash:.2f}')
# 和 paper_trader.cash 比对
conn.close()
"
```

### 检查点 3：止损逻辑验证（手动触发）

```bash
# 在测试环境中，将某只持仓的止损价设置为高于当前价，验证是否触发卖出
python -c "
from src.engine.paper_trader import PaperTrader
from src.utils.db import Database
db = Database('data/trading.db')
pt = PaperTrader(initial_capital=20000, db=db)
pt.load_positions_from_db()  # 从DB恢复持仓

# 构造一个低于止损价的价格
test_prices = {}
for code, pos in pt.positions.items():
    test_prices[code] = pos.stop_loss_price * 0.99  # 模拟跌破止损
pt.update_prices(test_prices)
triggered = pt.check_stops()
print('触发止损的股票:', triggered)
# 预期：持仓股票均出现在 triggered 中
"
```

### 检查点 4：重启持久化验证

```bash
# 步骤1：运行一轮，记录持仓
python main.py --once
python -c "
import sqlite3
conn = sqlite3.connect('data/trading.db')
rows = conn.execute('SELECT stock_code, quantity, entry_price FROM simulated_positions WHERE status=\"holding\"').fetchall()
print('重启前持仓:', rows)
conn.close()
"
# 步骤2：再次运行，验证持仓恢复
python main.py --once
python -c "
import sqlite3
conn = sqlite3.connect('data/trading.db')
rows = conn.execute('SELECT stock_code, quantity, entry_price FROM simulated_positions WHERE status=\"holding\"').fetchall()
print('重启后持仓:', rows)
conn.close()
"
# 预期：两次输出一致（持仓未丢失）
```

### 检查点 5：成本计算精度验证

```bash
python -c "
# 验证手续费计算：买入 10000 元的股票
amount = 10000.0
commission = max(amount * 0.0003, 5.0)
print(f'手续费: {commission:.2f} 元')  # 预期: 3.0 → 实际: 5.0 (取最低值)

amount2 = 100000.0
commission2 = max(amount2 * 0.0003, 5.0)
print(f'手续费: {commission2:.2f} 元')  # 预期: 30.0

# 验证卖出总费用：卖出 10000 元的股票（沪市）
sell_amount = 10000.0
sell_commission = max(sell_amount * 0.0003, 5.0)
stamp_tax = sell_amount * 0.001
transfer_fee = sell_amount * 0.00006
total_cost = sell_commission + stamp_tax + transfer_fee
print(f'卖出总费用: {total_cost:.2f} 元')  # 预期: 5 + 10 + 0.6 = 15.6 元
"
```

### 检查点 6：前向统计合理性验证（P1 完成后）

```bash
python -c "
from src.engine.forward_validator import ForwardValidator
from src.utils.db import Database
db = Database('data/trading.db')
closed_trades = db.get_closed_trades()
if len(closed_trades) >= 10:
    stats = ForwardValidator.compute_stats(closed_trades)
    print(f'交易次数: {stats.total_trades}')
    print(f'实际胜率: {stats.win_rate:.1%}')
    print(f'期望值: {stats.expectancy:.4f}')
    print(f'盈亏比: {stats.profit_loss_ratio:.2f}')
    # 合理性检查
    assert 0 <= stats.win_rate <= 1, '胜率超出范围'
    assert stats.total_trades == stats.win_trades + stats.loss_trades, '交易次数不一致'
    print('统计验证通过')
else:
    print(f'交易样本不足: {len(closed_trades)} 笔（需>=10笔）')
"
```

### 检查点 7：Web 面板可见性验证（P3 完成后）

1. 启动 `streamlit run web_dashboard_unified.py --server.port 8701`
2. 进入"模拟交易"页面
3. 验证：
   - [ ] 账户概览数字非零
   - [ ] 持仓表有数据（如有持仓）
   - [ ] 净值曲线图可渲染（有 equity_curve 数据点）
   - [ ] 前向统计表显示（即使样本少也显示当前数据）
   - [ ] 历史交易记录表可点击筛选

---

## 五、风险与注意事项

### 数据一致性风险

- **风险**: PaperTrader 内存状态与 DB 状态不同步
- **对策**: 每次启动时从 DB 加载持仓（`load_positions_from_db()`），不依赖内存
- **校验**: 检查点 4

### 涨跌停处理

- **买入涨停**: 跳过该信号，记录 reason='skipped_limit_up'，不算入统计
- **卖出跌停**: 记录为"无法止损"，下一轮继续检查，不强行以跌停价成交

### 信号与执行的时间差

- 系统每 300 秒运行一次，信号价格是采集时的价格，非当前盘口
- 建议：若信号时间距当前 > 5 分钟，使用最新价格而非信号价格买入

### 重复建仓防护

- 同一股票已有持仓时，不再重复买入
- 检查：`if stock_code not in self.paper_trader.positions`

### 初始状态迁移

- 重构前 main.py 的内存持仓（若有）无法自动迁移
- 处理方式：重构上线时清空 simulated_positions 表，从零开始记录

---

## 六、执行顺序

```
Day 1:
  [x] 创建 PAPER_TRADING_REFACTOR.md（本文件）
  [x] P0-2: 修改 db.py（新增 equity_curve 表和写入方法；_migrate 补齐旧表字段）
  [x] P0-1: 新建 paper_trader.py（核心撮合引擎）
  [x] P0-3: 修改 main.py（接入 PaperTrader）
  [x] 运行检查点 1、2、4（DB写入验证）✅ 通过

Day 2:
  [x] P1-1: 新建 forward_validator.py（前向统计）✅ 通过
  [x] 运行检查点 3、5、6（止损和统计验证）✅ 通过

Day 3:
  [x] P3: 修改 web_dashboard_unified.py（激活展示）✅ 通过
  [ ] 运行检查点 7（Web 可见性验证 - 需启动 streamlit 目视确认）
  [ ] 真实市场数据运行：python main.py --once，确认全链路正常
```

---

## 七、成功标准

重构完成后，系统应满足：

1. **持久化**: 运行 `python main.py --once` 后，`data/trading.db` 中有新记录（信号、持仓或交易）
2. **重启不丢失**: 重启 main.py 后，持仓数据从 DB 恢复，账户余额正确
3. **止损可触发**: 测试场景下，价格跌破止损时自动执行卖出并记录
4. **成本真实**: 每笔交易的费用计算可溯源（手续费+印花税+过户费）
5. **统计可信**: 10 笔以上平仓后，胜率/期望值/盈亏比数据可查
6. **Web 可视**: 模拟交易页面显示真实数据，净值曲线可渲染

---

*本文件作为重构执行基准，完成一项后在对应的 `[ ]` 前标记 `[x]`*
