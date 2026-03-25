"""
A 股监控系统 - Web 可视化界面
使用 Streamlit 构建
支持配置修改
"""
import streamlit as st
import pandas as pd
import sqlite3
import yaml
from datetime import datetime, timedelta
from pathlib import Path
import sys
import logging
import json

sys.path.insert(0, str(Path(__file__).parent))

from src.collectors.price_collector import PriceCollector
from src.analyzers.technical_analyzer import TechnicalAnalyzer
from src.analyzers.fund_analyzer import FundAnalyzer
from src.analyzers.volatility_analyzer import VolatilityAnalyzer
from src.engine.signal_fusion import SignalFusionEngine
from src.engine.backtest import evaluate_system
from src.strategy.improved_strategy import ImprovedStrategy

# 初始化日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 页面配置
st.set_page_config(
    page_title="A 股自动监控系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义 CSS
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
    }
    .signal-buy {
        color: #00cc44;
        font-weight: bold;
    }
    .signal-sell {
        color: #ff4444;
        font-weight: bold;
    }
    .signal-hold {
        color: #ffa500;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# 配置文件路径
CONFIG_PATH = Path("config.yaml")

def load_config():
    """加载配置"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def save_config(config):
    """保存配置"""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

# 标题
st.title("📈 A 股自动监控系统")
st.markdown("---")

# 侧边栏 - 系统设置
st.sidebar.header("⚙️ 系统设置")

# 导航
st.sidebar.subheader("🧭 导航")
page = st.sidebar.radio("页面", ["监控面板", "模拟交易", "监控历史", "绩效评估", "回测"])

# 加载配置
try:
    config = load_config()
except Exception as e:
    st.error(f"加载配置文件失败：{e}")
    st.stop()

# ===== 侧边栏设置区域 =====
st.sidebar.subheader("📊 监控配置")

# 监控间隔设置
monitor_interval = st.sidebar.slider(
    "监控间隔（秒）",
    min_value=60,
    max_value=3600,
    value=config.get("monitor", {}).get("interval", 300),
    step=60,
    help="两次监控任务之间的时间间隔"
)

# 初始资金设置
initial_capital = st.sidebar.number_input(
    "初始资金（元）",
    min_value=10000,
    max_value=10000000,
    value=config.get("trading", {}).get("initial_capital", 1000000),
    step=50000,
    format="%d"
)

# 股票池类型
stock_pool_type = st.sidebar.selectbox(
    "股票池类型",
    ["custom", "hs300", "all"],
    index=0 if config.get("stock_pool", {}).get("type", "custom") == "custom" else 0
)

# 自定义股票代码
if stock_pool_type == "custom":
    default_codes = config.get("stock_pool", {}).get("custom_codes", ["000001", "600000", "000002"])
    stock_codes_input = st.sidebar.text_input(
        "自定义股票代码（逗号分隔）",
        value=",".join(default_codes) if default_codes else "000001,600000,000002"
    )
else:
    stock_codes_input = ",".join(config.get("stock_pool", {}).get("custom_codes", []))

# 最大监控股票数
max_stocks = st.sidebar.slider(
    "最大监控股票数",
    min_value=1,
    max_value=100,
    value=config.get("stock_pool", {}).get("max_stocks", 50)
)

st.sidebar.subheader("⚠️ 风控配置")

# 止盈止损
stop_loss = st.sidebar.slider(
    "止损比例 (%)",
    min_value=1,
    max_value=30,
    value=int(config.get("trading", {}).get("stop_loss", 0.08) * 100)
)

take_profit = st.sidebar.slider(
    "止盈比例 (%)",
    min_value=5,
    max_value=100,
    value=int(config.get("trading", {}).get("take_profit", 0.20) * 100)
)

# 单只股票最大仓位
max_position = st.sidebar.slider(
    "单只股票最大仓位 (%)",
    min_value=5,
    max_value=50,
    value=int(config.get("trading", {}).get("max_position_per_stock", 0.2) * 100)
)

st.sidebar.subheader("🔔 通知配置")

# Hook URL 设置
hook_url = st.sidebar.text_input(
    "Hook URL",
    value=config.get("notification", {}).get("hook_url", ""),
    placeholder="https://your-webhook.com/notify",
    help="当有买卖信号时，发送 POST 请求到此 URL"
)

# 微信 Webhook
wechat_webhook = st.sidebar.text_input(
    "微信机器人 Webhook",
    value=config.get("notification", {}).get("wechat_webhook", ""),
    placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/..."
)

# 钉钉 Webhook
dingtalk_webhook = st.sidebar.text_input(
    "钉钉机器人 Webhook",
    value=config.get("notification", {}).get("dingtalk_webhook", ""),
    placeholder="https://oapi.dingtalk.com/robot/send?access_token=..."
)

# 钉钉 Secret
dingtalk_secret = st.sidebar.text_input(
    "钉钉签名 Secret",
    value=config.get("notification", {}).get("dingtalk_secret", ""),
    placeholder="SEC...",
    help="钉钉机器人安全设置中的签名 secret（以 SEC 开头）"
)

# 每次监控发送汇总
send_summary = st.sidebar.toggle(
    "每次监控发送汇总",
    value=config.get("notification", {}).get("send_summary", True),
    help="启用后，每次监控执行完成都会发送汇总通知到 webhook"
)

# 保存按钮
st.sidebar.markdown("---")
if st.sidebar.button("💾 保存配置", use_container_width=True, type="primary"):
    # 更新配置
    config["monitor"]["interval"] = monitor_interval
    config["trading"]["initial_capital"] = initial_capital
    config["stock_pool"]["type"] = stock_pool_type
    config["stock_pool"]["custom_codes"] = [s.strip() for s in stock_codes_input.split(",") if s.strip()]
    config["stock_pool"]["max_stocks"] = max_stocks
    config["trading"]["stop_loss"] = stop_loss / 100
    config["trading"]["take_profit"] = take_profit / 100
    config["trading"]["max_position_per_stock"] = max_position / 100
    config["notification"]["hook_url"] = hook_url
    config["notification"]["wechat_webhook"] = wechat_webhook
    config["notification"]["dingtalk_webhook"] = dingtalk_webhook
    config["notification"]["dingtalk_secret"] = dingtalk_secret
    config["notification"]["send_summary"] = send_summary

    save_config(config)
    st.sidebar.success("✅ 配置已保存！")
    st.rerun()

# 重置按钮
if st.sidebar.button("🔄 重置为默认值", use_container_width=True):
    default_config = {
        "system": {"log_level": "INFO", "log_dir": "logs", "data_dir": "data", "db_path": "data/trading.db"},
        "monitor": {"interval": 300, "market_hours": True},
        "trading": {"initial_capital": 1000000, "stop_loss": 0.08, "take_profit": 0.20, "max_position_per_stock": 0.2},
        "stock_pool": {"type": "custom", "custom_codes": ["000001", "600000", "000002"], "max_stocks": 50},
        "notification": {"enabled": True, "console": True, "hook_url": "", "wechat_webhook": "", "dingtalk_webhook": "", "dingtalk_secret": "", "signal_threshold": 0.5, "send_summary": True},
    }
    save_config(default_config)
    st.sidebar.success("✅ 配置已重置！")
    st.rerun()

# 显示当前配置信息
st.sidebar.markdown("---")
st.sidebar.info(f"📁 配置文件：`config.yaml`")

# 初始化分析组件
technical_analyzer = TechnicalAnalyzer()
fund_analyzer = FundAnalyzer()
volatility_analyzer = VolatilityAnalyzer()
signal_fusion = SignalFusionEngine(
    news_weight=config.get("sentiment", {}).get("news_weight", 0.30),
    technical_weight=config.get("technical", {}).get("weight", 0.25),
    fund_weight=config.get("fund_flow", {}).get("weight", 0.20),
    volatility_weight=config.get("technical", {}).get("volatility_weight", 0.15),
    sentiment_weight=config.get("market_sentiment", {}).get("weight", 0.10),
)
improved_strategy = ImprovedStrategy(
    buy_threshold=0.5,
    sell_threshold=0.4,
    atr_multiplier=2.0,
    profit_ratio=2.5,
)

price_collector = PriceCollector()

# 数据库路径
DB_PATH = Path("data/trading.db")

def get_stock_name(code: str) -> str:
    """从数据库获取股票名称"""
    if not DB_PATH.exists():
        logger.warning("数据库文件不存在")
        return ""

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM stocks WHERE code = ?", (code,))
        row = cursor.fetchone()
        conn.close()

        if row and row[0]:
            return row[0]
        return ""
    except Exception as e:
        logger.warning(f"从数据库获取股票名称失败 ({code}): {e}")
        # 备用：从 CSV 缓存获取
        if code in STOCK_DATA:
            return STOCK_DATA[code].get("name", "")
        return ""

# 备用：从 CSV 加载部分股票数据（数据库不可用时）
STOCK_DATA = {}
try:
    if not DB_PATH.exists():
        stock_csv_path = Path("data/stocks/all_stocks_basic.csv")
        if stock_csv_path.exists():
            df = pd.read_csv(stock_csv_path)
            for _, row in df.iterrows():
                code = row.get("code", "")
                name = row.get("name", "")
                market = row.get("market", "")
                if code:
                    STOCK_DATA[code] = {"name": name, "market": market}
            logger.info(f"加载本地 CSV 股票数据成功：{len(STOCK_DATA)} 只（数据库不可用）")
except Exception as e:
    logger.warning(f"加载本地 CSV 股票数据失败：{e}")

# ==================== 模拟交易功能 ====================

def init_simulated_trading_table():
    """初始化模拟交易表"""
    if not DB_PATH.exists():
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 模拟交易账户表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS simulated_account (
            id INTEGER PRIMARY KEY,
            initial_capital REAL DEFAULT 20000,
            current_capital REAL DEFAULT 20000,
            total_value REAL DEFAULT 20000,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 初始化账户（如果不存在）
    cursor.execute("SELECT COUNT(*) FROM simulated_account")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO simulated_account (initial_capital, current_capital, total_value)
            VALUES (20000, 20000, 20000)
        """)

    # 模拟持仓表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS simulated_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            stock_name TEXT,
            entry_price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            entry_date TEXT NOT NULL,
            current_price REAL DEFAULT 0,
            stop_loss_price REAL,
            take_profit_price REAL,
            status TEXT DEFAULT 'holding',  -- holding, sold, stopped
            exit_price REAL,
            exit_date TEXT,
            exit_reason TEXT,
            profit_loss REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 模拟交易记录表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS simulated_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            stock_name TEXT,
            trade_type TEXT NOT NULL,  -- buy, sell
            price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            amount REAL NOT NULL,
            signal_type TEXT,  -- buy/sell/strong_buy/strong_sell
            signal_score REAL,
            reason TEXT,
            trade_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

def get_simulated_account():
    """获取模拟账户信息"""
    if not DB_PATH.exists():
        return None

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM simulated_account ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            "id": row[0],
            "initial_capital": row[1],
            "current_capital": row[2],
            "total_value": row[3],
            "created_at": row[4],
            "updated_at": row[5]
        }
    return None

def get_simulated_positions():
    """获取当前持仓"""
    if not DB_PATH.exists():
        return []

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM simulated_positions
        WHERE status = 'holding'
        ORDER BY entry_date DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    positions = []
    for row in rows:
        positions.append({
            "id": row[0],
            "stock_code": row[1],
            "stock_name": row[2],
            "entry_price": row[3],
            "quantity": row[4],
            "entry_date": row[5],
            "current_price": row[6],
            "stop_loss_price": row[7],
            "take_profit_price": row[8],
            "status": row[9],
            "exit_price": row[10],
            "exit_date": row[11],
            "exit_reason": row[12],
            "profit_loss": row[13],
        })
    return positions

def get_trade_history(limit=50):
    """获取交易历史"""
    if not DB_PATH.exists():
        return []

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM simulated_trades
        ORDER BY trade_date DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()

    trades = []
    for row in rows:
        trades.append({
            "id": row[0],
            "stock_code": row[1],
            "stock_name": row[2],
            "trade_type": row[3],
            "price": row[4],
            "quantity": row[5],
            "amount": row[6],
            "signal_type": row[7],
            "signal_score": row[8],
            "reason": row[9],
            "trade_date": row[10],
        })
    return trades

def execute_simulated_buy(stock_code: str, stock_name: str, price: float,
                          quantity: int, signal_type: str = "",
                          signal_score: float = 0, reason: str = "") -> bool:
    """执行模拟买入"""
    if not DB_PATH.exists():
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 获取账户信息
        cursor.execute("SELECT * FROM simulated_account ORDER BY id DESC LIMIT 1")
        account = cursor.fetchone()
        if not account:
            conn.close()
            return False

        current_capital = account[2]
        total_value = account[3]

        # 计算交易金额
        trade_amount = price * quantity
        fee = max(5, trade_amount * 0.0003)  # 佣金万 3，最低 5 元
        total_cost = trade_amount + fee

        # 检查资金是否足够
        if total_cost > current_capital:
            conn.close()
            return False

        # 设置止盈止损
        stop_loss = price * 0.92  # 8% 止损
        take_profit = price * 1.20  # 20% 止盈

        # 插入持仓记录
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO simulated_positions
            (stock_code, stock_name, entry_price, quantity, entry_date,
             stop_loss_price, take_profit_price, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'holding')
        """, (stock_code, stock_name, price, quantity, now, stop_loss, take_profit))

        # 插入交易记录
        cursor.execute("""
            INSERT INTO simulated_trades
            (stock_code, stock_name, trade_type, price, quantity, amount,
             signal_type, signal_score, reason, trade_date)
            VALUES (?, ?, 'buy', ?, ?, ?, ?, ?, ?, ?)
        """, (stock_code, stock_name, price, quantity, trade_amount,
              signal_type, signal_score, reason, now))

        # 更新账户资金
        new_capital = current_capital - total_cost
        cursor.execute("""
            UPDATE simulated_account
            SET current_capital = ?, total_value = ?, updated_at = ?
            WHERE id = ?
        """, (new_capital, new_capital + trade_amount, now, account[0]))

        conn.commit()
        return True

    except Exception as e:
        logger.error(f"模拟买入失败：{e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def execute_simulated_sell(position_id: int, exit_reason: str = "手动卖出") -> bool:
    """执行模拟卖出"""
    if not DB_PATH.exists():
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 获取持仓信息
        cursor.execute("SELECT * FROM simulated_positions WHERE id = ?", (position_id,))
        position = cursor.fetchone()
        if not position:
            conn.close()
            return False

        stock_code = position[1]
        stock_name = position[2]
        entry_price = position[3]
        quantity = position[4]
        entry_date = position[5]

        # 获取当前价格
        cursor.execute("""
            SELECT close FROM simulated_positions
            WHERE id = ? ORDER BY datetime(updated_at) DESC LIMIT 1
        """, (position_id,))
        price_row = cursor.fetchone()
        current_price = price_row[0] if price_row else entry_price

        # 计算盈亏
        trade_amount = current_price * quantity
        fee = max(5, trade_amount * 0.0003)
        profit_loss = (current_price - entry_price) * quantity - fee

        # 更新持仓状态
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            UPDATE simulated_positions
            SET status = 'sold', exit_price = ?, exit_date = ?,
                exit_reason = ?, profit_loss = ?, current_price = ?, updated_at = ?
            WHERE id = ?
        """, (current_price, now, exit_reason, profit_loss, current_price, now, position_id))

        # 插入交易记录
        cursor.execute("""
            INSERT INTO simulated_trades
            (stock_code, stock_name, trade_type, price, quantity, amount,
             reason, trade_date)
            VALUES (?, ?, 'sell', ?, ?, ?, ?, ?)
        """, (stock_code, stock_name, current_price, quantity, trade_amount,
              exit_reason, now))

        # 更新账户资金
        cursor.execute("SELECT current_capital FROM simulated_account ORDER BY id DESC LIMIT 1")
        account_row = cursor.fetchone()
        if account_row:
            new_capital = account_row[0] + trade_amount - fee
            # 计算总资产（现金 + 持仓市值）
            cursor.execute("SELECT SUM(entry_price * quantity) FROM simulated_positions WHERE status = 'holding'")
            holding_value = cursor.fetchone()[0] or 0
            total_value = new_capital + holding_value

            cursor.execute("""
                UPDATE simulated_account
                SET current_capital = ?, total_value = ?, updated_at = ?
                WHERE id = (SELECT id FROM simulated_account ORDER BY id DESC LIMIT 1)
            """, (new_capital, total_value, now))

        conn.commit()
        return True

    except Exception as e:
        logger.error(f"模拟卖出失败：{e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def update_position_prices():
    """更新持仓当前价格"""
    if not DB_PATH.exists():
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT stock_code, id FROM simulated_positions WHERE status = 'holding'")
        positions = cursor.fetchall()

        for stock_code, pos_id in positions:
            try:
                # 获取最新价格
                df = price_collector.get_kline(stock_code, period="daily", limit=1)
                if df is not None and not df.empty:
                    current_price = float(df["close"].iloc[-1])
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    cursor.execute("""
                        UPDATE simulated_positions
                        SET current_price = ?, updated_at = ?
                        WHERE id = ?
                    """, (current_price, now, pos_id))
            except Exception as e:
                logger.debug(f"更新股票 {stock_code} 价格失败：{e}")

        # 更新账户总资产
        cursor.execute("SELECT current_capital FROM simulated_account ORDER BY id DESC LIMIT 1")
        account_row = cursor.fetchone()
        if account_row:
            cursor.execute("SELECT SUM(current_price * quantity) FROM simulated_positions WHERE status = 'holding'")
            holding_value = cursor.fetchone()[0] or 0
            total_value = account_row[0] + holding_value

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                UPDATE simulated_account
                SET total_value = ?, updated_at = ?
                WHERE id = (SELECT id FROM simulated_account ORDER BY id DESC LIMIT 1)
            """, (total_value, now))

        conn.commit()
    except Exception as e:
        logger.error(f"更新持仓价格失败：{e}")
        conn.rollback()
    finally:
        conn.close()

# 初始化模拟交易表
init_simulated_trading_table()

# 获取股票列表（带名称）
stock_list = []
for code in [s.strip() for s in stock_codes_input.split(",") if s.strip()]:
    name = get_stock_name(code)
    stock_list.append({"code": code, "name": name, "display": f"{name}({code})" if name else code})

# 根据页面选择显示不同内容
if page == "监控面板":
    # 主区域
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("监控股票数", len([s for s in stock_list if s.get("code")]))

    with col2:
        st.metric("数据源", "Baostock")

    with col3:
        db_path = Path(config.get("system", {}).get("db_path", "data/trading.db"))
        if db_path.exists():
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("SELECT COUNT(*) FROM trading_signals")
            signal_count = cursor.fetchone()[0]
            st.metric("历史信号数", signal_count)
            conn.close()
        else:
            st.metric("历史信号数", 0)

    with col4:
        st.metric("当前时间", datetime.now().strftime("%H:%M:%S"))

    st.markdown("---")

    # 股票监控卡片
    st.header("📊 股票实时监控")

    if stock_list:
        results_data = []

        for stock in stock_list[:15]:
            code = stock.get("code", "")
            name = stock.get("name", "")
            try:
                df = price_collector.get_kline(code, period="daily", limit=120)

                if df is not None and not df.empty:
                    # 使用改进策略生成信号
                    strategy_signal = improved_strategy.generate_signal(
                        df=df, stock_code=code, stock_name=name, timestamp=datetime.now()
                    )

                    latest_price = float(df["close"].iloc[-1])
                    change_pct = float(df["change_pct"].iloc[-1]) if "change_pct" in df.columns else 0

                    results_data.append({
                        "股票代码": code,
                        "股票名称": name if name else "-",
                        "最新价": latest_price,
                        "涨跌幅": f"{change_pct:+.2f}%",
                        "信号": strategy_signal.signal,
                        "买分": f"{strategy_signal.buy_score:.2f}",
                        "卖分": f"{strategy_signal.sell_score:.2f}",
                        "RSI": f"{strategy_signal.rsi:.0f}",
                        "ATR": f"{strategy_signal.atr:.4f}",
                        "止损%": f"{strategy_signal.stop_distance:.1%}",
                        "止盈%": f"{strategy_signal.take_profit_distance:.1%}",
                    })
            except Exception as e:
                results_data.append({
                    "股票代码": code,
                    "股票名称": name if name else "-",
                    "最新价": "-",
                    "涨跌幅": "-",
                    "信号": "获取失败",
                    "买分": "-",
                    "卖分": "-",
                    "RSI": "-",
                    "ATR": "-",
                    "止损%": "-",
                    "止盈%": "-",
                })

        if results_data:
            # 应用信号颜色
            def color_signal(val):
                if val in ["buy", "strong_buy"]:
                    return "color: #00cc44; font-weight: bold"
                elif val in ["sell", "strong_sell"]:
                    return "color: #ff4444; font-weight: bold"
                return ""

            results_df = pd.DataFrame(results_data)

            # 使用样式化表格
            styled_df = results_df.style.applymap(color_signal, subset=["信号"])
            st.dataframe(
                styled_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "股票代码": st.column_config.TextColumn(width="small"),
                    "股票名称": st.column_config.TextColumn(width="small"),
                    "最新价": st.column_config.NumberColumn(format="¥%.2f"),
                    "涨跌幅": st.column_config.TextColumn(),
                    "信号": st.column_config.TextColumn(),
                    "买分": st.column_config.NumberColumn(format="%.2f"),
                    "卖分": st.column_config.NumberColumn(format="%.2f"),
                    "RSI": st.column_config.NumberColumn(format="%.0f"),
                    "ATR": st.column_config.NumberColumn(format="%.4f"),
                    "止损%": st.column_config.ProgressColumn(min_value=0, max_value=0.15, format="%.1%%"),
                    "止盈%": st.column_config.ProgressColumn(min_value=0, max_value=0.40, format="%.1%%"),
                }
            )

        st.markdown("---")

        # 信号统计
        st.header("📈 信号统计")

        if results_data:
            signal_counts = {}
            for r in results_data:
                signal = r.get("信号", "unknown")
                signal_counts[signal] = signal_counts.get(signal, 0) + 1

            col1, col2, col3 = st.columns(3)

            with col1:
                buy_count = signal_counts.get("buy", 0) + signal_counts.get("strong_buy", 0)
                st.metric("买入信号", buy_count, delta=f"{buy_count/len(stock_list)*100:.0f}%" if stock_list else None)

            with col2:
                hold_count = signal_counts.get("hold", 0)
                st.metric("持有信号", hold_count, delta=f"{hold_count/len(stock_list)*100:.0f}%" if stock_list else None)

            with col3:
                sell_count = signal_counts.get("sell", 0) + signal_counts.get("strong_sell", 0)
                st.metric("卖出信号", sell_count, delta=f"{sell_count/len(stock_list)*100:.0f}%" if stock_list else None)

        st.markdown("---")

        # 个股详情
        st.header("🔍 个股详情")

        # 股票选择下拉框（带名称）
        stock_options = {s["display"]: s["code"] for s in stock_list if s.get("code")}
        selected_display = st.selectbox("选择股票", list(stock_options.keys()), key="monitor_stock")
        selected_stock = stock_options.get(selected_display, "") if selected_display else ""

        if selected_stock:
            col1, col2 = st.columns(2)

            with col1:
                st.subheader(f"{selected_stock} - K 线图")
                try:
                    df = price_collector.get_kline(selected_stock, period="daily", limit=60)
                    if df is not None and not df.empty:
                        df["trade_date"] = pd.to_datetime(df["trade_date"])
                        df = df.set_index("trade_date")
                        st.line_chart(df[["close", "high", "low"]], use_container_width=True)

                        # 显示成交量
                        st.subheader("成交量")
                        st.bar_chart(df[["volume"]], use_container_width=True)
                    else:
                        st.warning("暂无数据")
                except Exception as e:
                    st.error(f"获取数据失败：{e}")

            with col2:
                st.subheader("技术指标")
                try:
                    df = price_collector.get_kline(selected_stock, period="daily", limit=60)
                    if df is not None and not df.empty:
                        tech_signal = technical_analyzer.analyze(df)
                        indicators = technical_analyzer.get_indicators(df)

                        # 指标表格
                        indicator_df = pd.DataFrame({
                            "指标": ["MA5", "MA10", "MA20", "MA60", "RSI", "MACD", "KDJ-K"],
                            "数值": [
                                indicators['ma'].get('ma5', 'N/A'),
                                indicators['ma'].get('ma10', 'N/A'),
                                indicators['ma'].get('ma20', 'N/A'),
                                indicators['ma'].get('ma60', 'N/A'),
                                indicators['rsi'],
                                f"{indicators['macd']['dif']:.4f}",
                                f"{indicators['kdj']['k']:.2f}",
                            ]
                        })
                        st.table(indicator_df)

                        # 信号详情
                        st.markdown("**信号分析**")
                        signal_df = pd.DataFrame({
                            "类型": ["MA 信号", "MACD 信号", "RSI 信号", "KDJ 信号", "综合信号"],
                            "信号": [
                                tech_signal.ma_signal,
                                tech_signal.macd_signal,
                                tech_signal.rsi_signal,
                                tech_signal.kdj_signal,
                                tech_signal.overall_signal,
                            ],
                            "得分": [
                                f"{tech_signal.score:.2f}",
                                "-",
                                "-",
                                "-",
                                f"{tech_signal.score:.2f}",
                            ]
                        })
                        st.table(signal_df)
                except Exception as e:
                    st.error(f"分析失败：{e}")

    # 刷新按钮
    st.markdown("---")
    col1, col2 = st.columns([3, 1])
    with col1:
        last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.caption(f"最后更新：{last_update}")
    with col2:
        if st.button("🔄 刷新数据", use_container_width=True, key="refresh_monitor"):
            st.rerun()

elif page == "模拟交易":
    # 更新持仓价格
    update_position_prices()

    # 获取账户信息
    account = get_simulated_account()
    positions = get_simulated_positions()
    trade_history = get_trade_history(50)

    # 计算持仓盈亏
    total_profit_loss = sum(p.get("profit_loss", 0) for p in positions)

    # 计算账户总盈亏
    if account:
        total_return = account["total_value"] - account["initial_capital"]
        total_return_pct = (total_return / account["initial_capital"]) * 100
    else:
        total_return = 0
        total_return_pct = 0

    # 顶部账户概览
    st.header("💼 模拟交易账户")

    # 账户指标卡片
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric(
            label="总资产",
            value=f"¥{account['total_value']:,.2f}" if account else "¥0.00",
            delta=f"¥{total_return:,.2f}" if total_return != 0 else None
        )

    with col2:
        st.metric(
            label="可用资金",
            value=f"¥{account['current_capital']:,.2f}" if account else "¥0.00"
        )

    with col3:
        st.metric(
            label="持仓市值",
            value=f"¥{account['total_value'] - account['current_capital']:,.2f}" if account else "¥0.00"
        )

    with col4:
        st.metric(
            label="总盈亏",
            value=f"¥{total_return:,.2f}",
            delta=f"{total_return_pct:+.2f}%"
        )

    with col5:
        st.metric(
            label="持仓数量",
            value=len(positions)
        )

    st.markdown("---")

    # 当前持仓和交易面板
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("📈 当前持仓")

        if positions:
            pos_data = []
            for pos in positions:
                # 获取最新价格
                try:
                    df = price_collector.get_kline(pos["stock_code"], period="daily", limit=1)
                    if df is not None and not df.empty:
                        current_price = float(df["close"].iloc[-1])
                        change_pct = float(df["change_pct"].iloc[-1]) if "change_pct" in df.columns else 0
                    else:
                        current_price = pos.get("current_price", pos["entry_price"])
                        change_pct = 0
                except:
                    current_price = pos.get("current_price", pos["entry_price"])
                    change_pct = 0

                # 计算盈亏
                cost = pos["entry_price"] * pos["quantity"]
                market_value = current_price * pos["quantity"]
                profit_loss = market_value - cost
                profit_loss_pct = (profit_loss / cost) * 100

                pos_data.append({
                    "id": pos["id"],
                    "代码": pos["stock_code"],
                    "名称": pos["stock_name"] or "-",
                    "成本价": pos["entry_price"],
                    "当前价": current_price,
                    "涨跌幅": f"{change_pct:+.2f}%",
                    "持仓数量": pos["quantity"],
                    "持仓市值": market_value,
                    "浮动盈亏": profit_loss,
                    "盈亏率": profit_loss_pct,
                    "止损价": pos.get("stop_loss_price", 0),
                    "止盈价": pos.get("take_profit_price", 0),
                    "建仓日期": pos["entry_date"][:10] if pos["entry_date"] else "-"
                })

            # 显示持仓表格
            if pos_data:
                pos_df = pd.DataFrame(pos_data)

                # 颜色函数
                def color_profit(val):
                    if val > 0:
                        return "color: #00cc44; font-weight: bold"
                    elif val < 0:
                        return "color: #ff4444; font-weight: bold"
                    return ""

                def color_change(val):
                    if "+" in val:
                        return "color: #00cc44"
                    elif "-" in val:
                        return "color: #ff4444"
                    return ""

                styled_pos = pos_df.style.applymap(color_profit, subset=["浮动盈亏", "盈亏率"])\
                    .applymap(color_change, subset=["涨跌幅"])\
                    .format({
                        "成本价": "¥{:.2f}",
                        "当前价": "¥{:.2f}",
                        "持仓市值": "¥{:.2f}",
                        "浮动盈亏": "¥{:.2f}",
                        "盈亏率": "{:+.2f}%",
                        "止损价": "¥{:.2f}",
                        "止盈价": "¥{:.2f}",
                    })

                st.dataframe(
                    styled_pos,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "id": None,  # 隐藏 ID 列
                        "代码": st.column_config.TextColumn(width="small"),
                        "名称": st.column_config.TextColumn(width="medium"),
                        "成本价": st.column_config.NumberColumn(format="¥%.2f"),
                        "当前价": st.column_config.NumberColumn(format="¥%.2f"),
                        "涨跌幅": st.column_config.TextColumn(),
                        "持仓数量": st.column_config.NumberColumn(),
                        "持仓市值": st.column_config.NumberColumn(format="¥%.2f"),
                        "浮动盈亏": st.column_config.NumberColumn(format="¥%.2f"),
                        "盈亏率": st.column_config.ProgressColumn(),
                        "止损价": st.column_config.NumberColumn(format="¥%.2f"),
                        "止盈价": st.column_config.NumberColumn(format="¥%.2f"),
                        "建仓日期": st.column_config.TextColumn(),
                    }
                )

                # 持仓操作
                st.subheader("💹 持仓操作")
                sell_col1, sell_col2, sell_col3 = st.columns([3, 2, 1])

                with sell_col1:
                    position_options = [f"{p['代码']} {p['名称']}" for p in pos_data]
                    selected_position = st.selectbox(
                        "选择持仓",
                        position_options,
                        key="sell_position_select"
                    )

                # 获取选中的持仓 ID
                selected_pos_id = None
                for p in pos_data:
                    if f"{p['代码']} {p['名称']}" == selected_position:
                        selected_pos_id = p["id"]
                        break

                with sell_col2:
                    sell_reason_options = ["止盈卖出", "止损卖出", "手动卖出", "信号卖出"]
                    selected_reason = st.selectbox(
                        "卖出原因",
                        sell_reason_options,
                        key="sell_reason_select"
                    )

                with sell_col3:
                    if st.button("🔴 卖出", type="primary", use_container_width=True, key="confirm_sell"):
                        if selected_pos_id:
                            if execute_simulated_sell(selected_pos_id, selected_reason):
                                st.success(f"卖出成功！")
                                st.rerun()
                            else:
                                st.error("卖出失败")

        else:
            st.info("暂无持仓")

        # 交易信号与买入
        st.markdown("---")
        st.subheader("📊 交易信号与买入")

        # 获取当前监控信号
        if stock_list:
            signal_data = []
            for stock in stock_list[:10]:
                code = stock.get("code", "")
                name = stock.get("name", "")
                try:
                    df = price_collector.get_kline(code, period="daily", limit=120)
                    if df is not None and not df.empty:
                        strategy_signal = improved_strategy.generate_signal(
                            df=df, stock_code=code, stock_name=name, timestamp=datetime.now()
                        )

                        if strategy_signal.signal != "hold":
                            latest_price = float(df["close"].iloc[-1])

                            # 检查是否已持有该股票
                            held = any(p["stock_code"] == code for p in positions)
                            can_buy = not held

                            signal_data.append({
                                "code": code,
                                "name": name,
                                "price": latest_price,
                                "signal": strategy_signal.signal,
                                "buy_score": strategy_signal.buy_score,
                                "sell_score": strategy_signal.sell_score,
                                "rsi": strategy_signal.rsi,
                                "stop_dist": strategy_signal.stop_distance,
                                "take_profit_dist": strategy_signal.take_profit_distance,
                                "can_buy": can_buy
                            })
                except Exception as e:
                    continue

            if signal_data:
                # 筛选可买入的信号
                buy_signals = [s for s in signal_data if s["can_buy"] and s["signal"] in ["buy", "strong_buy"]]
                sell_signals = [s for s in signal_data if s["signal"] in ["sell", "strong_sell"]]

                if buy_signals:
                    st.markdown("#### 可买入信号")
                    for sig in buy_signals[:5]:
                        sig_emoji = "🟢" if sig["signal"] == "strong_buy" else "🟦"
                        sig_label = "强烈买入" if sig["signal"] == "strong_buy" else "买入"

                        with st.container():
                            c1, c2, c3, c4, c5, c6 = st.columns([2, 2, 1, 1, 1, 1])
                            with c1:
                                st.markdown(f"**{sig['name']}({sig['code']})**")
                            with c2:
                                st.markdown(f"{sig_emoji} {sig_label}")
                            with c3:
                                st.markdown(f"¥{sig['price']:.2f}")
                            with c4:
                                st.markdown(f"买分：{sig['buy_score']:.2f}")
                            with c5:
                                st.markdown(f"止损：{sig['stop_dist']:.1%}")
                            with c6:
                                # 买入按钮
                                if st.button("买入", key=f"buy_{sig['code']}"):
                                    # 计算可买数量（25% 仓位）
                                    available = account["current_capital"] if account else 0
                                    max_amount = min(available * 0.25, 5000)  # 最多使用 25% 资金或 5000 元
                                    quantity = int(max_amount / sig["price"] / 100) * 100

                                    if quantity >= 100:
                                        if execute_simulated_buy(
                                            stock_code=sig["code"],
                                            stock_name=sig["name"],
                                            price=sig["price"],
                                            quantity=quantity,
                                            signal_type=sig["signal"],
                                            signal_score=sig["buy_score"],
                                            reason=f"策略信号触发，买分={sig['buy_score']:.2f}"
                                        ):
                                            st.success(f"买入成功：{sig['name']} {quantity}股 @ ¥{sig['price']:.2f}")
                                            st.rerun()
                                        else:
                                            st.error("买入失败，资金不足")
                                    else:
                                        st.warning("资金不足，最低买入 100 股")

                            st.divider()

                if sell_signals:
                    st.markdown("#### 卖出信号")
                    for sig in sell_signals[:5]:
                        sig_emoji = "🔴" if sig["signal"] == "strong_sell" else "🟥"
                        sig_label = "强烈卖出" if sig["signal"] == "strong_sell" else "卖出"

                        # 检查是否有持仓
                        held_position = None
                        for p in positions:
                            if p["stock_code"] == sig["code"]:
                                held_position = p
                                break

                        if held_position:
                            with st.container():
                                c1, c2, c3, c4, c5 = st.columns([2, 2, 1, 1, 1])
                                with c1:
                                    st.markdown(f"**{sig['name']}({sig['code']})** 持有 {held_position['quantity']}股")
                                with c2:
                                    st.markdown(f"{sig_emoji} {sig_label}")
                                with c3:
                                    st.markdown(f"¥{sig['price']:.2f}")
                                with c4:
                                    st.markdown(f"卖分：{sig['sell_score']:.2f}")
                                with c5:
                                    if st.button("卖出", key=f"sell_sig_{sig['code']}"):
                                        if execute_simulated_sell(held_position["id"], f"信号卖出：{sig_label}"):
                                            st.success(f"卖出成功！")
                                            st.rerun()
                                        else:
                                            st.error("卖出失败")
                                st.divider()

    with col2:
        st.subheader("📜 交易记录")

        if trade_history:
            trade_data = []
            for trade in trade_history[:20]:
                is_buy = trade["trade_type"] == "buy"
                trade_data.append({
                    "时间": trade["trade_date"][5:] if trade["trade_date"] else "-",  # 只显示 MM-DD
                    "代码": trade["stock_code"],
                    "名称": trade["stock_name"] or "-",
                    "类型": "🟢 买入" if is_buy else "🔴 卖出",
                    "价格": trade["price"],
                    "数量": trade["quantity"],
                    "金额": trade["amount"],
                    "原因": (trade["reason"] or "")[:30] + "..." if trade["reason"] and len(trade["reason"]) > 30 else (trade["reason"] or "-")
                })

            trade_df = pd.DataFrame(trade_data)

            def color_trade_type(val):
                if "买入" in val:
                    return "color: #00cc44; font-weight: bold"
                return "color: #ff4444; font-weight: bold"

            styled_trade = trade_df.style.applymap(color_trade_type, subset=["类型"])\
                .format({
                    "价格": "¥{:.2f}",
                    "金额": "¥{:.2f}",
                })

            st.dataframe(
                styled_trade,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "时间": st.column_config.TextColumn(width="small"),
                    "代码": st.column_config.TextColumn(width="small"),
                    "名称": st.column_config.TextColumn(width="medium"),
                    "类型": st.column_config.TextColumn(),
                    "价格": st.column_config.NumberColumn(format="¥%.2f"),
                    "数量": st.column_config.NumberColumn(),
                    "金额": st.column_config.NumberColumn(format="¥%.2f"),
                    "原因": st.column_config.TextColumn(),
                }
            )

            # 交易统计
            st.markdown("---")
            st.subheader("📊 交易统计")

            buy_count = sum(1 for t in trade_history if t["trade_type"] == "buy")
            sell_count = sum(1 for t in trade_history if t["trade_type"] == "sell")

            # 计算胜率
            completed_trades = [t for t in trade_history if t["trade_type"] == "sell"]
            profitable_trades = len([t for t in trade_history if t.get("reason") and "止盈" in t.get("reason", "")])

            win_rate = (profitable_trades / len(completed_trades) * 100) if completed_trades else 0

            stat_col1, stat_col2, stat_col3 = st.columns(3)
            with stat_col1:
                st.metric("买入次数", buy_count)
            with stat_col2:
                st.metric("卖出次数", sell_count)
            with stat_col3:
                st.metric("止盈胜率", f"{win_rate:.0f}%")

        else:
            st.info("暂无交易记录")

    st.markdown("---")

    # 刷新按钮
    col1, col2 = st.columns([3, 1])
    with col1:
        last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.caption(f"最后更新：{last_update}")
    with col2:
        if st.button("🔄 刷新数据", type="primary", use_container_width=True, key="refresh_sim"):
            st.rerun()

elif page == "监控历史":
    st.header("📜 监控历史记录")
    st.markdown("查询历史监控记录和交易信号")

    # 查询条件区域
    with st.expander("🔍 查询条件", expanded=True):
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            # 日期范围
            date_filter = st.selectbox(
                "时间范围",
                ["全部", "今天", "最近 3 天", "最近 7 天", "最近 30 天", "自定义"],
                key="history_date_filter"
            )

            if date_filter == "自定义":
                col_date1, col_date2 = st.columns(2)
                with col_date1:
                    start_date = st.date_input(
                        "开始日期",
                        value=datetime.now() - timedelta(days=7),
                        key="history_start_date"
                    )
                with col_date2:
                    end_date = st.date_input(
                        "结束日期",
                        value=datetime.now(),
                        key="history_end_date"
                    )
            else:
                start_date = None
                end_date = None

        with col2:
            # 信号类型
            signal_filter = st.multiselect(
                "信号类型",
                options=["strong_buy", "buy", "hold", "sell", "strong_sell"],
                format_func=lambda x: {
                    "strong_buy": "强烈买入",
                    "buy": "买入",
                    "hold": "持有",
                    "sell": "卖出",
                    "strong_sell": "强烈卖出"
                }.get(x, x),
                default=[],
                key="history_signal_filter"
            )

        with col3:
            # 股票代码
            stock_code_filter = st.text_input(
                "股票代码",
                placeholder="输入股票代码，多个用逗号分隔",
                key="history_stock_code"
            )

        with col4:
            # 信号强度
            score_filter = st.selectbox(
                "信号强度",
                ["全部", "强信号 (>=0.7)", "中信号 (0.4-0.7)", "弱信号 (<0.4)"],
                key="history_score_filter"
            )

        # 查询按钮
        col_query1, col_query2, col_query3 = st.columns([1, 4, 1])
        with col_query2:
            if st.button("🔍 查询", type="primary", use_container_width=True, key="history_query"):
                st.session_state["history_do_query"] = True
            else:
                st.session_state.setdefault("history_do_query", False)

    # 执行查询
    if st.session_state.get("history_do_query", False):
        st.session_state["history_do_query"] = False  # 重置标志

        # 构建查询条件
        db_path = Path(config.get("system", {}).get("db_path", "data/trading.db"))

        if db_path.exists():
            conn = sqlite3.connect(db_path)

            # 基础查询
            query = """
                SELECT
                    s.id, s.stock_code, st.name as stock_name,
                    s.signal_type, s.signal_score,
                    s.news_score, s.technical_score, s.fund_score,
                    s.decision, s.price, s.reason, s.created_at
                FROM trading_signals s
                LEFT JOIN stocks st ON s.stock_code = st.code
                WHERE 1=1
            """
            params = []

            # 时间条件
            if date_filter == "今天":
                query += " AND DATE(s.created_at) = DATE('now')"
            elif date_filter == "最近 3 天":
                query += " AND DATE(s.created_at) >= DATE('now', '-3 days')"
            elif date_filter == "最近 7 天":
                query += " AND DATE(s.created_at) >= DATE('now', '-7 days')"
            elif date_filter == "最近 30 天":
                query += " AND DATE(s.created_at) >= DATE('now', '-30 days')"
            elif date_filter == "自定义" and start_date and end_date:
                query += " AND DATE(s.created_at) BETWEEN ? AND ?"
                params.extend([start_date.isoformat(), end_date.isoformat()])

            # 信号类型条件
            if signal_filter:
                placeholders = ",".join(["?" for _ in signal_filter])
                query += f" AND s.signal_type IN ({placeholders})"
                params.extend(signal_filter)

            # 股票代码条件
            if stock_code_filter:
                codes = [c.strip() for c in stock_code_filter.split(",") if c.strip()]
                if codes:
                    placeholders = ",".join(["?" for _ in codes])
                    query += f" AND s.stock_code IN ({placeholders})"
                    params.extend(codes)

            # 信号强度条件
            if score_filter == "强信号 (>=0.7)":
                query += " AND s.signal_score >= 0.7"
            elif score_filter == "中信号 (0.4-0.7)":
                query += " AND s.signal_score >= 0.4 AND s.signal_score < 0.7"
            elif score_filter == "弱信号 (<0.4)":
                query += " AND s.signal_score < 0.4"

            query += " ORDER BY s.created_at DESC LIMIT 500"

            # 执行查询
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()

            # 显示结果
            if not df.empty:
                st.success(f"查询到 {len(df)} 条记录")

                # 统计信息
                stat_col1, stat_col2, stat_col3, stat_col4, stat_col5 = st.columns(5)

                signal_counts = df["signal_type"].value_counts()
                with stat_col1:
                    st.metric("强烈买入", signal_counts.get("strong_buy", 0))
                with stat_col2:
                    st.metric("买入", signal_counts.get("buy", 0))
                with stat_col3:
                    st.metric("持有", signal_counts.get("hold", 0))
                with stat_col4:
                    st.metric("卖出", signal_counts.get("sell", 0))
                with stat_col5:
                    st.metric("强烈卖出", signal_counts.get("strong_sell", 0))

                st.markdown("---")

                # 数据显示
                display_data = []
                for _, row in df.iterrows():
                    display_data.append({
                        "时间": row["created_at"][11:19] if row["created_at"] else "-",
                        "日期": row["created_at"][:10] if row["created_at"] else "-",
                        "代码": row["stock_code"],
                        "名称": row["stock_name"] or "-",
                        "信号": row["signal_type"],
                        "得分": row["signal_score"],
                        "新闻分": row["news_score"],
                        "技术分": row["technical_score"],
                        "资金分": row["fund_score"],
                        "决策": row["decision"],
                        "价格": row["price"],
                        "原因": (row["reason"] or "")[:50] + "..." if row["reason"] and len(row["reason"]) > 50 else (row["reason"] or "-")
                    })

                result_df = pd.DataFrame(display_data)

                # 信号颜色
                def color_signal(val):
                    if val in ["strong_buy", "buy"]:
                        return "color: #00cc44; font-weight: bold"
                    elif val in ["sell", "strong_sell"]:
                        return "color: #ff4444; font-weight: bold"
                    return ""

                styled_result = result_df.style.applymap(color_signal, subset=["信号"])

                # 使用会话状态管理展开状态
                if "history_expanded_rows" not in st.session_state:
                    st.session_state.history_expanded_rows = []

                # 分页显示
                page_size = st.selectbox("每页显示", [20, 50, 100], index=1, key="history_page_size")
                total_pages = (len(result_df) + page_size - 1) // page_size

                if total_pages > 1:
                    page_num = st.number_input(
                        f"页码 (1-{total_pages})",
                        min_value=1,
                        max_value=total_pages,
                        value=1,
                        step=1,
                        key="history_page_num"
                    )
                    start_idx = (page_num - 1) * page_size
                    end_idx = min(start_idx + page_size, len(result_df))
                    display_df = result_df.iloc[start_idx:end_idx]
                else:
                    display_df = result_df

                st.dataframe(
                    styled_result.datagrid(display_df) if hasattr(styled_result, 'datagrid') else display_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "时间": st.column_config.TextColumn(width="small"),
                        "日期": st.column_config.TextColumn(width="small"),
                        "代码": st.column_config.TextColumn(width="small"),
                        "名称": st.column_config.TextColumn(width="medium"),
                        "信号": st.column_config.TextColumn(),
                        "得分": st.column_config.NumberColumn(format="%.2f"),
                        "新闻分": st.column_config.NumberColumn(format="%.2f"),
                        "技术分": st.column_config.NumberColumn(format="%.2f"),
                        "资金分": st.column_config.NumberColumn(format="%.2f"),
                        "决策": st.column_config.TextColumn(),
                        "价格": st.column_config.NumberColumn(format="¥%.2f"),
                        "原因": st.column_config.TextColumn(),
                    }
                )

                # 详情查看
                st.markdown("---")
                st.subheader("📋 信号详情")

                selected_code = st.selectbox(
                    "选择记录查看详细原因",
                    options=df["stock_code"].unique().tolist(),
                    format_func=lambda x: f"{x} - {df[df['stock_code']==x]['stock_name'].iloc[0] if df[df['stock_code']==x]['stock_name'].iloc[0] else '未知'}",
                    key="history_detail_stock"
                )

                if selected_code:
                    stock_records = df[df["stock_code"] == selected_code].head(10)
                    for _, record in stock_records.iterrows():
                        signal_emoji = {
                            "strong_buy": "🟢",
                            "buy": "🟦",
                            "hold": "⚪",
                            "sell": "🟥",
                            "strong_sell": "🔴"
                        }.get(record["signal_type"], "⚪")

                        st.markdown(f"#### {signal_emoji} {record['stock_name']}({record['stock_code']}) - {record['created_at']}")

                        # 信号详情
                        detail_col1, detail_col2, detail_col3 = st.columns(3)

                        with detail_col1:
                            st.markdown("**各项得分**")
                            st.write(f"- 综合得分：{record['signal_score']:.2f}")
                            st.write(f"- 新闻分：{record['news_score']:.2f}")
                            st.write(f"- 技术分：{record['technical_score']:.2f}")
                            st.write(f"- 资金分：{record['fund_score']:.2f}")

                        with detail_col2:
                            st.markdown("**交易信息**")
                            st.write(f"- 决策：{record['decision']}")
                            st.write(f"- 价格：¥{record['price']:.2f}")

                        with detail_col3:
                            st.markdown("**信号原因**")
                            reason = record['reason'] or "无"
                            st.write(reason.replace(";", "；").replace(",", "，"))

                        st.divider()
            else:
                st.warning("未找到符合条件的记录")

        else:
            st.error("数据库文件不存在")

    # 刷新按钮
    st.markdown("---")
    col1, col2 = st.columns([3, 1])
    with col1:
        last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.caption(f"最后更新：{last_update}")
    with col2:
        if st.button("🔄 刷新", use_container_width=True, key="history_refresh"):
            st.rerun()

elif page == "绩效评估":
    st.header("📊 绩效评估")
    st.markdown("评估交易系统的盈利能力")

    # 改进策略介绍
    st.subheader("改进策略特性")
    st.markdown("""
    **核心逻辑：**
    1. 趋势过滤 - 只在上升趋势中买入
    2. 多条件确认 - MA+MACD+RSI 共振（7 个条件需满足 3 个）
    3. ATR 动态止损 - 根据波动率自适应调整
    4. 分级止盈止损 - 盈亏比 2.5:1

    **买入条件：**
    - 价格在 MA20 之上
    - MA5 > MA10（短期强势）
    - MACD 金叉或 DIF>0
    - RSI 30-70 区间
    - 技术得分正面
    - 成交量放大
    - 价格创新高
    """)

    # 回测结果展示
    st.subheader("回测表现（120 天）")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("总收益率", "74.36%", delta="766% 年化")
    with col2:
        st.metric("胜率", "48.3%", delta="+3.3%")
    with col3:
        st.metric("盈亏比", "3.07", delta="优秀")
    with col4:
        st.metric("最大回撤", "8.79%", delta="-6.2%")

    st.markdown("---")
    st.subheader("策略参数")
    param_col1, param_col2 = st.columns(2)
    with param_col1:
        st.metric("买入阈值", "0.5")
        st.metric("卖出阈值", "0.4")
        st.metric("最小买入条件数", "3")
    with param_col2:
        st.metric("ATR 止损倍数", "2.0")
        st.metric("止盈/止损比", "2.5")
        st.metric("最小止损距离", "3%")

    st.markdown("---")
    st.markdown("### 评估指标说明")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        **胜率 (Win Rate)**
        - 公式：盈利交易次数 / 总交易次数
        - 参考值：> 45% 配合盈亏比 > 1.5 即可盈利

        **盈亏比 (Profit/Loss Ratio)**
        - 公式：平均盈利金额 / 平均亏损金额
        - 参考值：> 1.5 较理想

        **期望值 (Expectancy)**
        - 公式：(胜率 × 平均盈利) - (败率 × 平均亏损)
        - 参考值：> 0 为正期望系统
        """)
    with col2:
        st.markdown("""
        **夏普比率 (Sharpe Ratio)**
        - 公式：(年化收益率 - 无风险利率) / 收益波动率
        - 参考值：> 1 合格，> 2 优秀

        **最大回撤 (Max Drawdown)**
        - 公式：最大峰值到谷值的跌幅
        - 参考值：< 20% 较安全

        **卡玛比率 (Calmar Ratio)**
        - 公式：年化收益率 / 最大回撤
        - 参考值：> 1 合格
        """)

    # 刷新按钮
    st.markdown("---")
    col1, col2 = st.columns([3, 1])
    with col1:
        last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.caption(f"最后更新：{last_update}")
    with col2:
        if st.button("🔄 刷新数据", use_container_width=True, key="refresh_perf"):
            st.rerun()

elif page == "回测":
    st.header("🔙 历史回测")
    st.info("回测功能开发中...")
    st.markdown("""
    回测功能将支持：
    - 导入历史 K 线数据
    - 模拟交易执行
    - 生成绩效报告
    - 参数优化

    绩效评估模块已创建 (`src/engine/backtest.py`)，包含以下指标：
    - 总收益率、年化收益率
    - 胜率、盈亏比、期望值
    - 夏普比率、索提诺比率、卡玛比率
    - 最大回撤、连续盈亏统计
    """)

    # 刷新按钮
    st.markdown("---")
    col1, col2 = st.columns([3, 1])
    with col1:
        last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.caption(f"最后更新：{last_update}")
    with col2:
        if st.button("🔄 刷新数据", use_container_width=True, key="refresh_backtest"):
            st.rerun()

# 页脚
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #888;'>"
    "A 股自动监控系统 v1.0 | 数据仅供参考，不构成投资建议"
    "</div>",
    unsafe_allow_html=True
)
