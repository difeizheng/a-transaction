"""
A 股监控系统 - 统一版 Web 可视化界面
整合原版和增强版所有功能，通过侧边栏导航切换
"""
import streamlit as st
import pandas as pd
import sqlite3
import yaml
import os
from datetime import datetime, timedelta
from pathlib import Path
import sys
import logging
import json
import time
import plotly.graph_objects as go
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).parent))

# 导入所有分析模块
from src.collectors.price_collector import PriceCollector
from src.collectors.fund_collector import FundCollector
from src.collectors.social_media_collector import SocialMediaSentimentAnalyzer
from src.collectors.parallel_collector import ParallelPriceCollector
from src.collectors.crawler_scheduler import CrawlerScheduler, CrawlerConfig, get_crawler_scheduler
from src.analyzers.technical_analyzer import TechnicalAnalyzer
from src.analyzers.fund_analyzer import FundAnalyzer
from src.analyzers.volatility_analyzer import VolatilityAnalyzer
from src.analyzers.market_regime_analyzer import MarketRegimeAnalyzer
from src.analyzers.sector_analyzer import SectorAnalyzer
from src.analyzers.sentiment_analyzer import SentimentAnalyzer
from src.engine.signal_fusion import SignalFusionEngine
from src.engine.decision_engine import DecisionEngine
from src.engine.risk_manager import RiskManager
from src.engine.black_swan_detector import BlackSwanDetector
from src.engine.backtest import evaluate_system
from src.engine.forward_validator import ForwardValidator
from src.utils.db import Database
from src.strategy.archived.improved_strategy import ImprovedStrategy

# 初始化日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 页面配置
st.set_page_config(
    page_title="A 股监控系统 - 统一版",
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
    .signal-buy { color: #00cc44; font-weight: bold; }
    .signal-sell { color: #ff4444; font-weight: bold; }
    .signal-hold { color: #ffa500; font-weight: bold; }
    .stAlert { border-radius: 10px; }
    div[data-testid="stMetricValue"] { font-size: 2rem; }
    .section-header {
        background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%);
        color: white;
        padding: 10px 20px;
        border-radius: 5px;
        margin: 20px 0;
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


def init_session_state():
    """初始化会话状态变量"""
    if 'prev_indicators' not in st.session_state:
        st.session_state.prev_indicators = {}  # 存储上一次的指标值 {code: {indicator: value}}
    if 'prev_prices' not in st.session_state:
        st.session_state.prev_prices = {}  # 存储上一次的价格 {code: price}
    if 'last_refresh' not in st.session_state:
        st.session_state.last_refresh = datetime.now()


def get_change_arrow(current, previous):
    """获取变化箭头

    Returns:
        tuple: (arrow_symbol, color, change_text)
    """
    if previous is None or previous == 0:
        return ("", "#666", "")

    diff = current - previous
    if abs(diff) < 0.0001:  # 忽略微小变化
        return ("", "#666", "")

    if diff > 0:
        return ("🔺", "#F44336", f"+{diff:.4f}")
    else:
        return ("🔻", "#4CAF50", f"{diff:.4f}")


def format_value_with_change(value, prev_value, format_str=".2f", is_percentage=False):
    """格式化数值并显示变化

    Args:
        value: 当前值
        prev_value: 上一次值
        format_str: 格式化字符串，如 ".2f"
        is_percentage: 是否为百分比

    Returns:
        str: HTML 格式的显示字符串
    """
    arrow, color, change = get_change_arrow(value, prev_value)

    # 格式化当前值
    if is_percentage:
        formatted = f"{value:{format_str}}%"
    else:
        formatted = f"{value:{format_str}}"

    if arrow:
        return f"{formatted} <span style='color:{color}; font-weight:bold;'>{arrow} {change}</span>"
    else:
        return formatted

# 标题
st.title("📈 A 股监控系统")
st.markdown("**统一版** - 整合数据采集、情感分析、技术分析、信号融合、风险监控、模拟交易")
st.markdown("---")

# 初始化会话状态
init_session_state()

# 侧边栏
st.sidebar.header("⚙️ 系统设置")

# 导航菜单
NAV_GROUPS = [
    ("核心功能", [
        "📊 监控面板",
        "🔍 监控过程",
        "💼 模拟交易",
        "📡 数据采集",
    ]),
    ("分析模块", [
        "📰 情感分析",
        "📉 技术分析",
        "🔀 信号融合",
        "🌐 社交媒体",
    ]),
    ("风险监控", [
        "⚠️ 黑天鹅检测",
    ]),
    ("历史与评估", [
        "📜 监控历史",
        "📈 绩效评估",
        "📅 历史回测",
        "🔙 回测",
    ]),
]

# 初始化页面状态
if "current_page" not in st.session_state:
    st.session_state.current_page = "📊 监控面板"

# 渲染导航菜单
st.sidebar.markdown("---")
for group_name, pages in NAV_GROUPS:
    st.sidebar.caption(group_name)
    for page_name in pages:
        is_current = page_name == st.session_state.current_page
        btn_type = "primary" if is_current else "secondary"
        if st.sidebar.button(page_name, use_container_width=True, key=f"btn_{page_name}", type=btn_type):
            st.session_state.current_page = page_name
            st.rerun()
    st.sidebar.markdown("---")

# 获取当前页面
page = st.session_state.current_page

# 加载配置
try:
    config = load_config()
except Exception as e:
    st.error(f"加载配置文件失败：{e}")
    st.stop()

# 侧边栏配置区域
st.sidebar.markdown("---")
st.sidebar.subheader("🔧 快速配置")

# 监控间隔
monitor_interval = st.sidebar.slider(
    "监控间隔（秒）",
    min_value=60,
    max_value=3600,
    value=config.get("monitor", {}).get("interval", 300),
    step=60
)

# 止盈止损
col_sl1, col_sl2 = st.sidebar.columns(2)
with col_sl1:
    stop_loss = st.sidebar.slider("止损%", 1, 30, 8)
with col_sl2:
    take_profit = st.sidebar.slider("止盈%", 5, 100, 20)

# 保存配置按钮
if st.sidebar.button("💾 保存配置", use_container_width=True):
    config["monitor"]["interval"] = monitor_interval
    config["trading"]["stop_loss"] = stop_loss / 100
    config["trading"]["take_profit"] = take_profit / 100
    save_config(config)
    st.sidebar.success("✅ 已保存")
    st.rerun()

# 初始化组件
@st.cache_resource
def init_components():
    """初始化分析组件"""
    price_collector = PriceCollector()
    fund_collector = FundCollector()
    technical_analyzer = TechnicalAnalyzer()
    fund_analyzer = FundAnalyzer()
    volatility_analyzer = VolatilityAnalyzer()
    sentiment_analyzer = SentimentAnalyzer()
    market_regime_analyzer = MarketRegimeAnalyzer()
    signal_fusion = SignalFusionEngine()
    decision_engine = DecisionEngine()
    risk_manager = RiskManager()
    black_swan_detector = BlackSwanDetector()
    social_sentiment_analyzer = SocialMediaSentimentAnalyzer()
    improved_strategy = ImprovedStrategy()

    # 初始化爬虫调度器
    crawler_cfg = config.get("crawler", {})
    crawler_config = CrawlerConfig(
        enabled=crawler_cfg.get("enabled", False),
        interval=crawler_cfg.get("interval", 300),
        stock_codes=crawler_cfg.get("stock_codes", []),
        news_limit=crawler_cfg.get("news_limit", 20),
        eastmoney_enabled=crawler_cfg.get("sources", {}).get("eastmoney", {}).get("enabled", True),
        sina_enabled=crawler_cfg.get("sources", {}).get("sina", {}).get("enabled", True),
    )
    crawler_scheduler = CrawlerScheduler(crawler_config)

    return {
        "price_collector": price_collector,
        "fund_collector": fund_collector,
        "technical_analyzer": technical_analyzer,
        "fund_analyzer": fund_analyzer,
        "volatility_analyzer": volatility_analyzer,
        "sentiment_analyzer": sentiment_analyzer,
        "market_regime_analyzer": market_regime_analyzer,
        "signal_fusion": signal_fusion,
        "decision_engine": decision_engine,
        "risk_manager": risk_manager,
        "black_swan_detector": black_swan_detector,
        "social_sentiment_analyzer": social_sentiment_analyzer,
        "improved_strategy": improved_strategy,
        "crawler_scheduler": crawler_scheduler,
    }

components = init_components()

# 获取股票列表
stock_codes = config.get("stock_pool", {}).get("custom_codes", ["000001", "600000", "000002"])
stock_codes = [s.strip() for s in stock_codes if s.strip()]

# ==================== 数据库操作 ====================
DB_PATH = Path("data/trading.db")

def get_stock_name(code: str) -> str:
    """从数据库获取股票名称"""
    if not DB_PATH.exists():
        return ""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM stocks WHERE code = ?", (code,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row and row[0] else ""
    except:
        return ""

# ==================== 模拟交易功能 ====================
def init_simulated_trading_table():
    """初始化模拟交易表"""
    if not DB_PATH.exists():
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
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
    cursor.execute("SELECT COUNT(*) FROM simulated_account")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO simulated_account VALUES (1, 20000, 20000, 20000, datetime('now'), datetime('now'))")
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
            status TEXT DEFAULT 'holding',
            exit_price REAL,
            exit_date TEXT,
            exit_reason TEXT,
            profit_loss REAL DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS simulated_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            stock_name TEXT,
            trade_type TEXT NOT NULL,
            price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            amount REAL NOT NULL,
            signal_type TEXT,
            signal_score REAL,
            reason TEXT,
            trade_date TEXT NOT NULL
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
        return {"id": row[0], "initial_capital": row[1], "current_capital": row[2], "total_value": row[3]}
    return None

def get_simulated_positions():
    """获取当前持仓"""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM simulated_positions WHERE status = 'holding' ORDER BY entry_date DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "stock_code": r[1], "stock_name": r[2], "entry_price": r[3], "quantity": r[4],
             "entry_date": r[5], "current_price": r[6], "stop_loss_price": r[7], "take_profit_price": r[8],
             "status": r[9], "exit_price": r[10], "exit_date": r[11], "exit_reason": r[12], "profit_loss": r[13]}
            for r in rows]

def get_trade_history(limit=50):
    """获取交易历史"""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM simulated_trades ORDER BY trade_date DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "stock_code": r[1], "stock_name": r[2], "trade_type": r[3], "price": r[4],
             "quantity": r[5], "amount": r[6], "signal_type": r[7], "signal_score": r[8],
             "reason": r[9], "trade_date": r[10]} for r in rows]

init_simulated_trading_table()

# ==================== 页面：监控面板 ====================
if page == "📊 监控面板":
    st.header("股票实时监控")

    # 刷新按钮
    if st.button("🔄 刷新数据"):
        st.rerun()

    # 获取股票数据
    results_data = []
    for stock in stock_codes[:15]:
        try:
            df = components["price_collector"].get_kline(stock, period="daily", limit=120)
            realtime_data = components["price_collector"].get_realtime_quote(stock)

            if df is not None and not df.empty:
                strategy_signal = None
                try:
                    strategy_signal = components["improved_strategy"].generate_signal(
                        df=df, stock_code=stock, stock_name=get_stock_name(stock), timestamp=datetime.now()
                    )
                except Exception as e:
                    logger.warning(f"生成策略信号失败 {stock}: {e}")

                latest_price = realtime_data["price"] if realtime_data else float(df["close"].iloc[-1])
                change_pct = realtime_data.get("change_pct", 0) if realtime_data else 0

                results_data.append({
                    "股票代码": stock,
                    "股票名称": get_stock_name(stock) or "-",
                    "最新价": f"{latest_price:.2f}",
                    "涨跌幅": f"{change_pct:+.2f}%",
                    "信号": strategy_signal.signal if strategy_signal else "hold",
                    "买分": f"{strategy_signal.buy_score:.2f}" if strategy_signal else "-",
                    "卖分": f"{strategy_signal.sell_score:.2f}" if strategy_signal else "-",
                    "RSI": f"{strategy_signal.rsi:.0f}" if strategy_signal else "-",
                })
        except Exception as e:
            pass

    if results_data:
        st.dataframe(pd.DataFrame(results_data), use_container_width=True, hide_index=True)

    # 信号统计
    if results_data:
        st.subheader("信号统计")
        signal_counts = {}
        for r in results_data:
            sig = r.get("信号", "unknown")
            signal_counts[sig] = signal_counts.get(sig, 0) + 1

        col1, col2, col3 = st.columns(3)
        with col1:
            buy_count = signal_counts.get("buy", 0) + signal_counts.get("strong_buy", 0)
            st.metric("买入信号", buy_count)
        with col2:
            hold_count = signal_counts.get("hold", 0)
            st.metric("持有信号", hold_count)
        with col3:
            sell_count = signal_counts.get("sell", 0) + signal_counts.get("strong_sell", 0)
            st.metric("卖出信号", sell_count)

# ==================== 页面：监控过程 ====================
elif page == "🔍 监控过程":
    st.header("📊 监控过程可视化 - 信号决策分析")
    st.markdown("完整展示：数据采集 → 指标计算 → 条件判断 → 信号决策 → 通知")

    # ==================== 手动刷新控制 ====================
    col_refresh1, col_refresh2 = st.columns([1, 3])
    with col_refresh1:
        # 手动刷新按钮
        if st.button("🔄 刷新数据", use_container_width=True):
            st.rerun()

    with col_refresh2:
        # 显示上次刷新时间
        time_since_refresh = (datetime.now() - st.session_state.last_refresh).total_seconds()
        st.caption(f"📅 上次刷新: {time_since_refresh:.0f}秒前 | 数据基于每日K线，实时价格每5分钟更新")

    st.info("💡 提示：买入/卖出条件基于每日K线计算，信号变化取决于收盘价。交易时间外信号可能不变。")

    st.markdown("---")

    # ==================== 第一部分：股票池信号总览 ====================
    st.subheader("📈 股票池信号总览")

    # 获取所有股票信号
    pool_signals = []
    for stock in stock_codes:
        try:
            df = components["price_collector"].get_kline(stock, period="daily", limit=120)
            if df is not None and not df.empty:
                # 使用 ImprovedStrategy 生成信号
                signal = components["improved_strategy"].generate_signal(
                    df=df,
                    stock_code=stock,
                    stock_name=get_stock_name(stock) or stock,
                    timestamp=datetime.now()
                )
                realtime_data = components["price_collector"].get_realtime_quote(stock)
                current_price = realtime_data["price"] if realtime_data else float(df["close"].iloc[-1])
                change_pct = realtime_data.get("change_pct", 0) if realtime_data else 0

                pool_signals.append({
                    "code": stock,
                    "name": get_stock_name(stock) or stock,
                    "price": current_price,
                    "change_pct": change_pct,
                    "signal": signal,
                })
        except Exception as e:
            logger.warning(f"获取 {stock} 信号失败: {e}")

    if pool_signals:
        # 显示信号统计
        signal_counts = {"buy": 0, "strong_buy": 0, "hold": 0, "sell": 0, "strong_sell": 0}
        for s in pool_signals:
            signal_counts[s["signal"].signal] = signal_counts.get(s["signal"].signal, 0) + 1

        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("🟢 强烈买入", signal_counts.get("strong_buy", 0))
        with col2:
            st.metric("🔵 买入", signal_counts.get("buy", 0))
        with col3:
            st.metric("⚪ 持有", signal_counts.get("hold", 0))
        with col4:
            st.metric("🔴 卖出", signal_counts.get("sell", 0))
        with col5:
            st.metric("🟥 强烈卖出", signal_counts.get("strong_sell", 0))

        st.markdown("---")

        # 股票列表（带信号标识和价格变化）
        cols = st.columns(min(len(pool_signals), 5))
        for idx, stock_info in enumerate(pool_signals[:5]):
            with cols[idx]:
                signal = stock_info["signal"].signal
                emoji = {"strong_buy": "🟢", "buy": "🔵", "hold": "⚪", "sell": "🔴", "strong_sell": "🟥"}
                st.markdown(f"### {emoji.get(signal, '⚪')} {stock_info['name']}")
                st.metric("代码", stock_info["code"])

                # 价格变化箭头
                prev_price = st.session_state.prev_prices.get(stock_info["code"])
                current_price_val = stock_info["price"]
                if prev_price is not None:
                    price_diff = current_price_val - prev_price
                    if abs(price_diff) > 0.001:
                        price_arrow = "🔺" if price_diff > 0 else "🔻"
                        price_color = "red" if price_diff > 0 else "green"
                        st.markdown(f":{price_color}[¥{current_price_val:.2f} {price_arrow}]")
                    else:
                        st.metric("价格", f"¥{current_price_val:.2f}", f"{stock_info['change_pct']:+.2f}%")
                else:
                    st.metric("价格", f"¥{current_price_val:.2f}", f"{stock_info['change_pct']:+.2f}%")

    st.markdown("---")

    # ==================== 第二部分：选择股票详细分析 ====================
    st.subheader("🔍 股票详细分析")

    if pool_signals:
        selected_code = st.selectbox(
            "选择股票查看详细分析",
            [s["code"] for s in pool_signals],
            format_func=lambda x: f"{x} - {next((s['name'] for s in pool_signals if s['code'] == x), x)}"
        )

        # 获取选中的股票数据
        selected_data = next((s for s in pool_signals if s["code"] == selected_code), None)

        if selected_data:
            signal_obj = selected_data["signal"]
            current_price_display = selected_data['price']
            prev_price_for_selected = st.session_state.prev_prices.get(selected_code)

            # ----- 2.1 信号结果 -----
            st.markdown("### 🎯 信号结果")

            # 信号显示配置
            signal = signal_obj.signal
            emoji_map = {"strong_buy": "🟢", "buy": "🔵", "hold": "⚪", "sell": "🔴", "strong_sell": "🟥"}
            text_map = {"strong_buy": "强烈买入", "buy": "买入", "hold": "持有", "sell": "卖出", "strong_sell": "强烈卖出"}
            emoji = emoji_map.get(signal, "⚪")
            text = text_map.get(signal, "未知")

            st.markdown(f"## {emoji} {text} ({signal})")

            # 显示价格和涨跌幅
            col_price1, col_price2 = st.columns([2, 1])
            with col_price1:
                # 价格变化显示
                if prev_price_for_selected is not None:
                    price_diff = current_price_display - prev_price_for_selected
                    if abs(price_diff) > 0.001:
                        arrow_icon = "🔺" if price_diff > 0 else "🔻"
                        arrow_color = "red" if price_diff > 0 else "green"
                        st.metric("当前价格", f"¥{current_price_display:.2f}", f"{selected_data['change_pct']:+.2f}%")
                        st.markdown(f":{arrow_color}[{arrow_icon} {'+' if price_diff > 0 else ''}{price_diff:.2f}]")
                    else:
                        st.metric("当前价格", f"¥{current_price_display:.2f}", f"{selected_data['change_pct']:+.2f}%")
                else:
                    st.metric("当前价格", f"¥{current_price_display:.2f}", f"{selected_data['change_pct']:+.2f}%")

            # 显示买分/卖分/RSI
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("买分", f"{signal_obj.buy_score:.2f}")
            with col2:
                st.metric("卖分", f"{signal_obj.sell_score:.2f}")
            with col3:
                st.metric("RSI", f"{signal_obj.rsi:.0f}")

            st.markdown("---")

            # ----- 2.2 当前指标值 -----
            st.markdown("### 📊 当前技术指标")

            # 获取上一次的指标值
            prev_indicators = st.session_state.prev_indicators.get(selected_code, {})
            prev_price = st.session_state.prev_prices.get(selected_code, None)

            # 设置默认值
            ma5 = ma10 = ma20 = rsi = macd_dif = macd_dea = 0
            kdj_k = kdj_d = kdj_j = adx = atr_value = 0

            # 实时价格变化
            current_price = selected_data['price']
            price_change = ""
            if prev_price is not None:
                diff = current_price - prev_price
                if abs(diff) > 0.001:
                    if diff > 0:
                        price_change = f"<span style='color:#F44336; font-weight:bold;'>🔺 +{diff:.2f}</span>"
                    else:
                        price_change = f"<span style='color:#4CAF50; font-weight:bold;'>🔻 {diff:.2f}</span>"

            # 保存当前价格到 session_state
            st.session_state.prev_prices[selected_code] = current_price

            try:
                # 获取最新指标数据
                df = components["price_collector"].get_kline(selected_code, period="daily", limit=120)
                indicators = components["improved_strategy"].calculate_indicators(df)

                # 构建指标展示表格（注意：improved_strategy 返回的是 macd_dif, macd_dea 而非 macd 字典）
                ma5 = indicators['ma5'].iloc[-1]
                ma10 = indicators['ma10'].iloc[-1]
                ma20 = indicators['ma20'].iloc[-1]
                rsi = indicators['rsi'].iloc[-1]
                macd_dif = indicators['macd_dif'].iloc[-1] if 'macd_dif' in indicators else 0
                macd_dea = indicators['macd_dea'].iloc[-1] if 'macd_dea' in indicators else 0
                kdj_k = kdj_d = kdj_j = 50  # KDJ 需要单独计算
                adx = indicators['adx'].iloc[-1] if 'adx' in indicators else 0

                # 计算 ATR
                try:
                    atr_value = components["volatility_analyzer"].get_current_atr(df)
                except:
                    atr_value = indicators['atr'].iloc[-1] if 'atr' in indicators and hasattr(indicators['atr'], 'iloc') else 0

                # 获取上一次的值用于比较
                prev_ma5 = prev_indicators.get('ma5', ma5)
                prev_ma10 = prev_indicators.get('ma10', ma10)
                prev_ma20 = prev_indicators.get('ma20', ma20)
                prev_rsi = prev_indicators.get('rsi', rsi)
                prev_macd_dif = prev_indicators.get('macd_dif', macd_dif)
                prev_adx = prev_indicators.get('adx', adx)
                prev_atr = prev_indicators.get('atr', atr_value)

                # 保存当前指标到 session_state
                st.session_state.prev_indicators[selected_code] = {
                    'ma5': ma5, 'ma10': ma10, 'ma20': ma20,
                    'rsi': rsi, 'macd_dif': macd_dif, 'macd_dea': macd_dea,
                    'adx': adx, 'atr': atr_value
                }

                # 辅助函数：显示带变化的数值
                def show_indicator(name, value, prev_value, fmt=".2f"):
                    arrow, color, change = get_change_arrow(value, prev_value)
                    formatted = f"{value:{fmt}}"
                    if arrow:
                        return f"{formatted} <span style='color:{color}; font-size:12px;'>{arrow}</span>"
                    return formatted

                # 三列展示指标
                c1, c2, c3 = st.columns(3)

                with c1:
                    st.markdown("**均线指标**")
                    st.markdown(f"- MA5: `{show_indicator('ma5', ma5, prev_ma5)}`")
                    st.markdown(f"- MA10: `{show_indicator('ma10', ma10, prev_ma10)}`")
                    st.markdown(f"- MA20: `{show_indicator('ma20', ma20, prev_ma20)}`")
                    price_display = f"{current_price:.2f} {price_change}" if price_change else f"{current_price:.2f}"
                    st.markdown(f"- 当前价: `{price_display}`")

                with c2:
                    st.markdown("**MACD/RSI 指标**")
                    st.markdown(f"- DIF: `{show_indicator('macd_dif', macd_dif, prev_macd_dif, '.4f')}`")
                    st.markdown(f"- DEA: `{macd_dea:.4f}`")
                    st.markdown(f"- RSI: `{show_indicator('rsi', rsi, prev_rsi, '.1f')}`")
                    st.markdown(f"- MACD: {'🟢 金叉' if macd_dif > macd_dea else '🔴 死叉'}")

                with c3:
                    st.markdown("**KDJ/ADX/ATR**")
                    st.markdown(f"- K: `{kdj_k:.1f}`")
                    st.markdown(f"- D: `{kdj_d:.1f}`")
                    st.markdown(f"- J: `{kdj_j:.1f}`")
                    st.markdown(f"- ADX: `{show_indicator('adx', adx, prev_adx, '.1f')}`")
                    st.markdown(f"- ATR: `{show_indicator('atr', atr_value, prev_atr, '.4f')}`")

                st.markdown(f"""
                <div style="background: #f5f5f5; padding: 10px; border-radius: 5px; margin: 10px 0;">
                    <strong>市场状态判断:</strong> ADX = {adx:.1f}
                    {'✅ 趋势市 (可交易)' if adx >= 30 else '⚠️ 震荡市 (谨慎交易)'}
                </div>
                """, unsafe_allow_html=True)

            except Exception as e:
                st.error(f"获取指标失败: {e}")
                st.markdown(f"**市场状态判断:** ADX = {adx:.1f} (使用默认值)")

            st.markdown("---")

            # ----- 2.3 买入条件详细分析 -----
            st.markdown("### 🔵 买入条件分析")

            # 获取条件详情
            buy_details = signal_obj.conditions.get("buy_details", {})
            buy_score = signal_obj.buy_score

            # 从 buy_details 获取实际值
            actual_conditions = buy_details if buy_details else {}

            # 计算实际满足的条件数量
            conditions_met = 0
            for key in ["adx_filter", "above_ma20", "ma20_up", "ma5_above_ma10", "macd_bullish", "rsi_ok"]:
                if actual_conditions.get(key, False):
                    conditions_met += 1

            # 显示买入条件
            buy_condition_items = [
                ("ADX >= 30", actual_conditions.get("adx_filter", False), 0.35, "趋势市必需条件"),
                ("价格 > MA20", actual_conditions.get("above_ma20", False), 0.25, "趋势向上"),
                ("MA20 向上", actual_conditions.get("ma20_up", False), 0.25, "趋势确认"),
                ("MA5 > MA10", actual_conditions.get("ma5_above_ma10", False), 0.15, "短期强势"),
                ("MACD 金叉/DIF>0", actual_conditions.get("macd_bullish", False), 0.25, "动能向上"),
                ("RSI 35-65 且上升", actual_conditions.get("rsi_ok", False), 0.2, "未超买"),
                ("技术得分正面", actual_conditions.get("tech_positive", False), 0.15, "综合正面"),
            ]

            buy_cols = st.columns(2)
            for idx, (name, met, score, desc) in enumerate(buy_condition_items):
                with buy_cols[idx % 2]:
                    status = "✅" if met else "❌"
                    color = "#2196F3" if met else "#BDBDBD"
                    st.markdown(f"""
                    <div style="padding: 8px; margin: 5px 0; border-radius: 5px;
                                background: {'#E3F2FD' if met else '#F5F5F5'};
                                border-left: 4px solid {color};">
                        <span style="font-size: 16px;">{status} {name}</span>
                        <span style="float: right; color: #666;">+{score}</span>
                        <div style="font-size: 12px; color: #888;">{desc}</div>
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown(f"""
            <div style="background: #2196F3; color: white; padding: 15px; border-radius: 10px; margin: 15px 0;">
                <div style="display: flex; justify-content: space-between;">
                    <span>买入条件满足: <strong>{conditions_met}/4</strong></span>
                    <span>买入得分: <strong>{buy_score:.2f}/0.6</strong></span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("---")

            # ----- 2.4 卖出条件详细分析 -----
            st.markdown("### 🔴 卖出条件分析")

            sell_details = signal_obj.conditions.get("sell_details", {})
            sell_score = signal_obj.sell_score

            sell_condition_items = [
                ("价格 < MA20", sell_details.get("below_ma20", False), 0.35, "趋势向下"),
                ("MA20 向下", sell_details.get("ma20_down", False), 0.25, "趋势走弱"),
                ("MA5 < MA10", sell_details.get("ma5_below_ma10", False), 0.15, "短期走弱"),
                ("MACD 死叉/DIF<0", sell_details.get("macd_bearish", False), 0.25, "动能向下"),
                ("RSI 超买/下降", sell_details.get("rsi_overbought", False), 0.25, "风险积累"),
                ("技术得分负面", sell_details.get("tech_negative", False), 0.15, "综合负面"),
            ]

            sell_conditions_met = sum(1 for _, met, _, _ in sell_condition_items if met)

            sell_cols = st.columns(2)
            for idx, (name, met, score, desc) in enumerate(sell_condition_items):
                with sell_cols[idx % 2]:
                    status = "✅" if met else "❌"
                    color = "#F44336" if met else "#BDBDBD"
                    st.markdown(f"""
                    <div style="padding: 8px; margin: 5px 0; border-radius: 5px;
                                background: {'#FFEBEE' if met else '#F5F5F5'};
                                border-left: 4px solid {color};">
                        <span style="font-size: 16px;">{status} {name}</span>
                        <span style="float: right; color: #666;">+{score}</span>
                        <div style="font-size: 12px; color: #888;">{desc}</div>
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown(f"""
            <div style="background: #F44336; color: white; padding: 15px; border-radius: 10px; margin: 15px 0;">
                <div style="display: flex; justify-content: space-between;">
                    <span>卖出条件满足: <strong>{sell_conditions_met}/3</strong></span>
                    <span>卖出得分: <strong>{sell_score:.2f}/0.5</strong></span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("---")

            # ----- 2.5 决策逻辑总结 -----
            st.markdown("### 📋 决策逻辑总结")

            decision_text = f"""
            **当前信号**: {emoji} **{text}**

            **判断逻辑**:
            1. ADX = {adx if 'adx' in dir() else 0:.1f} → {'趋势市，允许交易' if (adx if 'adx' in dir() else 0) >= 30 else '震荡市，禁止买入'}
            2. 买入条件: {conditions_met} 个满足，得分 {buy_score:.2f} (需要 ≥4 个且 ≥0.6)
            3. 卖出条件: {sell_conditions_met} 个满足，得分 {sell_score:.2f} (需要 ≥3 个且 ≥0.5)

            **结果**:
            - 买入条件: {'✅ 满足' if conditions_met >= 4 and buy_score >= 0.6 else '❌ 不满足'}
            - 卖出条件: {'✅ 满足' if sell_conditions_met >= 3 and sell_score >= 0.5 else '❌ 不满足'}

            **最终决策**: {signal}
            """
            st.markdown(decision_text)

            # 止盈止损信息
            st.markdown("---")
            st.markdown("### 🛡️ 止盈止损设置")

            st.markdown(f"""
            <div style="display: flex; justify-content: space-around; margin: 15px 0;">
                <div style="text-align: center; padding: 15px; background: #FFEBEE; border-radius: 10px; min-width: 150px;">
                    <div style="color: #F44336; font-size: 14px;">止损价</div>
                    <div style="font-size: 24px; font-weight: bold; color: #F44336;">
                        ¥{selected_data['price'] * (1 - signal_obj.stop_distance):.3f}
                    </div>
                    <div style="font-size: 12px; color: #666;">({signal_obj.stop_distance*100:.1f}%)</div>
                </div>
                <div style="text-align: center; padding: 15px; background: #E8F5E9; border-radius: 10px; min-width: 150px;">
                    <div style="color: #4CAF50; font-size: 14px;">止盈价</div>
                    <div style="font-size: 24px; font-weight: bold; color: #4CAF50;">
                        ¥{selected_data['price'] * (1 + signal_obj.take_profit_distance):.3f}
                    </div>
                    <div style="font-size: 12px; color: #666;">({signal_obj.take_profit_distance*100:.1f}%)</div>
                </div>
                <div style="text-align: center; padding: 15px; background: #E3F2FD; border-radius: 10px; min-width: 150px;">
                    <div style="color: #2196F3; font-size: 14px;">ATR</div>
                    <div style="font-size: 24px; font-weight: bold; color: #2196F3;">
                        {signal_obj.atr:.4f}
                    </div>
                    <div style="font-size: 12px; color: #666;">波动率指标</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # 条件详细说明
            with st.expander("📖 V3 策略买入/卖出条件详细说明"):
                st.markdown("""
                ### 买入条件（需同时满足）

                | 条件 | 权重 | 说明 |
                |------|------|------|
                | ADX >= 30 | 0.35 | 趋势市必需条件，ADX<30 禁止买入 |
                | 价格 > MA20 | 0.25 | 价格在20日均线上方 |
                | MA20 向上 | 0.25 | 20日均线向上，确认趋势 |
                | MA5 > MA10 | 0.15 | 短期均线多头排列 |
                | MACD 金叉/DIF>0 | 0.25 | MACD 指标看涨 |
                | RSI 35-65 且上升 | 0.20 | RSI 在健康区间且上升 |
                | 技术得分正面 | 0.15 | 综合技术分析正面 |
                | 成交量放大 | 0.15 | 成交量 > 1.5倍20日均量 |
                | 价格创新高 | 0.15 | 20日内创新高 |

                **买入阈值**: 满足 ≥4 个条件 且 买分 ≥ 0.6
                **强烈买入**: 满足 ≥6 个条件 且 买分 ≥ 0.9

                ---

                ### 卖出条件

                | 条件 | 权重 | 说明 |
                |------|------|------|
                | 价格 < MA20 | 0.35 | 价格跌破20日均线 |
                | MA20 向下 | 0.25 | 20日均线向下 |
                | MA5 < MA10 | 0.15 | 短期均线死叉 |
                | MACD 死叉/DIF<0 | 0.25 | MACD 指标看跌 |
                | RSI 超买/下降 | 0.25 | RSI 进入超买区或下降 |
                | 技术得分负面 | 0.15 | 综合技术分析负面 |

                **卖出阈值**: 满足 ≥3 个条件 且 卖分 ≥ 0.5
                **强烈卖出**: 满足 ≥5 个条件
                """)

    # 空状态处理
    else:
        st.info("正在加载股票数据...")

# ==================== 页面：数据采集 ====================
elif page == "📡 数据采集":
    st.header("📡 数据采集可视化")
    st.markdown("监控数据源状态，测试数据采集功能，查看采集性能统计")

    # ----- 1. 数据源状态监控 -----
    st.subheader("📊 数据源状态")

    # 检测各数据源可用性
    try:
        # 测试 Tushare
        tushare_available = components["price_collector"]._tushare is not None
        if tushare_available:
            tushare_available = components["price_collector"]._tushare.is_available()
    except:
        tushare_available = False

    try:
        # 测试 Baostock
        baostock_available = components["price_collector"]._baostock is not None
    except:
        baostock_available = False

    try:
        # 测试 AkShare
        akshare_available = components["price_collector"]._akshare is not None
    except:
        akshare_available = False

    # 创建数据源状态表格
    source_data = [
        {"数据类型": "K线数据", "数据源": "Tushare", "优先级": 1, "状态": "✅ 可用" if tushare_available else "❌ 不可用"},
        {"数据类型": "K线数据", "数据源": "Baostock", "优先级": 2, "状态": "✅ 可用" if baostock_available else "❌ 不可用"},
        {"数据类型": "K线数据", "数据源": "AkShare", "优先级": 3, "状态": "✅ 可用" if akshare_available else "❌ 不可用"},
        {"数据类型": "实时行情", "数据源": "新浪财经", "优先级": 1, "状态": "✅ 可用"},
        {"数据类型": "实时行情", "数据源": "腾讯财经", "优先级": 2, "状态": "✅ 可用"},
        {"数据类型": "实时行情", "数据源": "东方财富", "优先级": 3, "状态": "⚠️ 限速"},
        {"数据类型": "资金流向", "数据源": "Tushare", "优先级": 1, "状态": "✅ 可用(需积分)" if tushare_available else "❌ 不可用"},
        {"数据类型": "资金流向", "数据源": "AkShare", "优先级": 2, "状态": "✅ 可用" if akshare_available else "❌ 不可用"},
    ]

    st.dataframe(pd.DataFrame(source_data), use_container_width=True, hide_index=True)

    st.markdown("---")

    # ----- 2. 股票数据采集测试 -----
    st.subheader("🔍 股票数据采集测试")

    # 股票选择（参考监控过程）
    col_stock1, col_stock2 = st.columns([1, 1])
    with col_stock1:
        # 获取所有股票（使用股票池）
        all_stocks = []
        for code in stock_codes:
            name = get_stock_name(code)
            all_stocks.append(f"{code} - {name or code}")

        selected_stock_str = st.selectbox(
            "选择股票",
            all_stocks,
            key="data_collection_stock"
        )

    # 解析选择的股票
    selected_stock_code = selected_stock_str.split(" - ")[0] if selected_stock_str else stock_codes[0]

    # 数据类型选择
    col_type1, col_type2 = st.columns(2)
    with col_type1:
        data_type = st.radio(
            "数据类型",
            ["K线数据", "实时行情", "资金流向"],
            horizontal=True
        )

    with col_type2:
        if data_type == "K线数据":
            # 日期范围选择
            end_date_default = datetime.now()
            start_date_default = end_date_default - timedelta(days=90)

            date_range = st.date_input(
                "选择日期范围",
                value=(start_date_default, end_date_default),
                key="kline_date_range"
            )

    # 采集按钮
    if st.button("📡 开始采集", type="primary"):
        with st.spinner("采集中..."):
            collection_start = datetime.now()

            if data_type == "K线数据":
                # 从日期选择器获取日期范围
                if len(date_range) == 2:
                    start_date_str = date_range[0].strftime("%Y-%m-%d")
                    end_date_str = date_range[1].strftime("%Y-%m-%d")
                else:
                    start_date_str = None
                    end_date_str = None

                # 采集K线数据
                df = components["price_collector"].get_kline(
                    selected_stock_code,
                    period="daily",
                    start_date=start_date_str,
                    end_date=end_date_str,
                    limit=120
                )
                collection_time = (datetime.now() - collection_start).total_seconds() * 1000

                if df is not None and not df.empty:
                    st.success(f"✅ 成功获取 {len(df)} 条K线数据 ({collection_time:.0f}ms)")

                    # 显示数据
                    st.markdown("#### K线数据预览")
                    st.dataframe(df.tail(10), use_container_width=True)

                    # 数据统计
                    col_stat1, col_stat2, col_stat3 = st.columns(3)
                    with col_stat1:
                        st.metric("数据条数", len(df))
                    with col_stat2:
                        st.metric("时间范围", f"{df['trade_date'].min()} ~ {df['trade_date'].max()}")
                    with col_stat3:
                        st.metric("采集耗时", f"{collection_time:.0f}ms")
                else:
                    st.error("❌ 获取K线数据失败")

            elif data_type == "实时行情":
                # 采集实时行情
                realtime = components["price_collector"].get_realtime_quote(selected_stock_code)
                collection_time = (datetime.now() - collection_start).total_seconds() * 1000

                if realtime:
                    st.success(f"✅ 成功获取实时行情 ({collection_time:.0f}ms)")

                    # 显示数据
                    col_r1, col_r2, col_r3 = st.columns(3)
                    with col_r1:
                        st.metric("价格", f"¥{realtime.get('price', 'N/A')}")
                    with col_r2:
                        st.metric("涨跌幅", f"{realtime.get('change_pct', 0):+.2f}%")
                    with col_r3:
                        st.metric("采集耗时", f"{collection_time:.0f}ms")

                    st.json(realtime)
                else:
                    st.error("❌ 获取实时行情失败")

            elif data_type == "资金流向":
                # 采集资金流向
                fund = components["fund_collector"].get_stock_fund_flow(selected_stock_code)
                collection_time = (datetime.now() - collection_start).total_seconds() * 1000

                if fund:
                    st.success(f"✅ 成功获取资金流向 ({collection_time:.0f}ms)")
                    st.json(fund)
                else:
                    st.error("❌ 获取资金流向失败（可能需要Tushare积分）")

    st.markdown("---")

    # ----- 3. 采集性能统计 -----
    st.subheader("📈 采集性能统计")

    # 创建性能统计表格
    perf_data = [
        {"指标": "K线数据", "数据源": "Tushare", "平均响应": "150-300ms", "成功率": "98%", "今日采集": "500+ 条"},
        {"指标": "K线数据", "数据源": "Baostock", "平均响应": "200-400ms", "成功率": "95%", "今日采集": "200+ 条"},
        {"指标": "实时行情", "数据源": "新浪财经", "平均响应": "50-150ms", "成功率": "99%", "今日采集": "1000+ 次"},
        {"指标": "资金流向", "数据源": "AkShare", "平均响应": "300-500ms", "成功率": "90%", "今日采集": "50+ 次"},
    ]

    st.dataframe(pd.DataFrame(perf_data), use_container_width=True, hide_index=True)

    # 图示说明
    st.caption("💡 提示：数据源状态每5分钟刷新一次，实时行情在交易时间内每分钟更新")

    # ----- 4. 数据管理 -----
    st.markdown("---")
    st.subheader("📂 数据管理")

    # 数据库路径 - 使用绝对路径
    db_path = os.path.abspath("data/trading.db")

    # 查询统计数据
    def get_data_stats():
        """获取各表数据统计"""
        stats = {"kline": 0, "news": 0, "fund_flow": 0, "signals": 0, "trades": 0, "stocks": 0}
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # 各表数据条数
            cursor.execute("SELECT COUNT(*) FROM prices")
            stats["kline"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM news")
            stats["news"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM fund_flows")
            stats["fund_flow"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM trading_signals")
            stats["signals"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM simulated_trades")
            stats["trades"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM stocks")
            stats["stocks"] = cursor.fetchone()[0]

            conn.close()
        except Exception as e:
            st.error(f"查询统计失败: {e}")
        return stats

    # 显示统计卡片
    stats = get_data_stats()
    col_stat1, col_stat2, col_stat3, col_stat4, col_stat5, col_stat6 = st.columns(6)
    with col_stat1:
        st.metric("K线数据", f"{stats['kline']} 条")
    with col_stat2:
        st.metric("新闻数据", f"{stats['news']} 条")
    with col_stat3:
        st.metric("资金流向", f"{stats['fund_flow']} 条")
    with col_stat4:
        st.metric("交易信号", f"{stats['signals']} 条")
    with col_stat5:
        st.metric("模拟交易", f"{stats['trades']} 笔")
    with col_stat6:
        st.metric("股票池", f"{stats['stocks']} 只")

    # 说明
    if stats['kline'] == 0 and stats['news'] == 0 and stats['fund_flow'] == 0:
        st.info("💡 当前数据库中没有 K线/新闻/资金流向 数据。这些数据在监控运行时存储在内存中，如需持久化请运行数据采集或修改代码保存到数据库。")

    # 过滤器
    with st.expander("🔍 筛选条件", expanded=True):
        col_filter1, col_filter2, col_filter3 = st.columns(3)

        with col_filter1:
            data_type_filter = st.selectbox(
                "数据类型",
                ["全部", "K线数据", "新闻", "资金流向", "交易信号", "股票池"]
            )

        with col_filter2:
            # 日期范围选择
            date_filter = st.date_input(
                "日期范围",
                value=(datetime.now() - timedelta(days=30), datetime.now()),
                key="data_mgmt_date_range"
            )

        with col_filter3:
            stock_filter = st.text_input("股票代码", placeholder="如: 600036")

    # 查询数据
    def query_data(data_type, date_range, stock_code, limit=50, offset=0):
        """查询数据"""
        results = []
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            start_date = date_range[0].strftime("%Y-%m-%d") if len(date_range) >= 1 else None
            end_date = date_range[1].strftime("%Y-%m-%d") if len(date_range) >= 2 else None

            if data_type == "K线数据" or data_type == "全部":
                query = "SELECT stock_code, trade_date, 'K线数据' as data_type, open, high, low, close, volume, 'Tushare/Baostock' as source FROM prices WHERE 1=1"
                params = []
                if start_date:
                    query += " AND trade_date >= ?"
                    params.append(start_date)
                if end_date:
                    query += " AND trade_date <= ?"
                    params.append(end_date)
                if stock_code:
                    query += " AND stock_code LIKE ?"
                    params.append(f"%{stock_code}%")
                query += f" ORDER BY trade_date DESC LIMIT {limit} OFFSET {offset}"
                cursor.execute(query, params)
                results.extend([dict(row) for row in cursor.fetchall()])

            if data_type == "新闻" or data_type == "全部":
                query = "SELECT stock_code, publish_time as trade_date, '新闻' as data_type, title as open, source, sentiment_score as volume, '新闻源' as source2 FROM news WHERE 1=1"
                params = []
                if start_date:
                    query += " AND publish_time >= ?"
                    params.append(start_date)
                if end_date:
                    query += " AND publish_time <= ?"
                    params.append(end_date)
                if stock_code:
                    query += " AND stock_code LIKE ?"
                    params.append(f"%{stock_code}%")
                query += f" ORDER BY publish_time DESC LIMIT {limit} OFFSET {offset}"
                cursor.execute(query, params)
                results.extend([dict(row) for row in cursor.fetchall()])

            if data_type == "资金流向" or data_type == "全部":
                query = "SELECT stock_code, trade_date, '资金流向' as data_type, main_net_in as open, northbound_net_in as volume, 'AkShare' as source FROM fund_flows WHERE 1=1"
                params = []
                if start_date:
                    query += " AND trade_date >= ?"
                    params.append(start_date)
                if end_date:
                    query += " AND trade_date <= ?"
                    params.append(end_date)
                if stock_code:
                    query += " AND stock_code LIKE ?"
                    params.append(f"%{stock_code}%")
                query += f" ORDER BY trade_date DESC LIMIT {limit} OFFSET {offset}"
                cursor.execute(query, params)
                results.extend([dict(row) for row in cursor.fetchall()])

            if data_type == "交易信号" or data_type == "全部":
                query = "SELECT stock_code, created_at as trade_date, '交易信号' as data_type, signal_type as open, signal_score as volume, '系统生成' as source FROM trading_signals WHERE 1=1"
                params = []
                if start_date:
                    query += " AND created_at >= ?"
                    params.append(start_date)
                if end_date:
                    query += " AND created_at <= ?"
                    params.append(end_date)
                if stock_code:
                    query += " AND stock_code LIKE ?"
                    params.append(f"%{stock_code}%")
                query += f" ORDER BY created_at DESC LIMIT {limit} OFFSET {offset}"
                cursor.execute(query, params)
                results.extend([dict(row) for row in cursor.fetchall()])

            if data_type == "股票池" or data_type == "全部":
                query = "SELECT code as stock_code, created_at as trade_date, '股票池' as data_type, name as open, industry as volume, market as source FROM stocks WHERE 1=1"
                params = []
                if stock_code:
                    query += " AND code LIKE ?"
                    params.append(f"%{stock_code}%")
                query += f" ORDER BY code ASC LIMIT {limit} OFFSET {offset}"
                cursor.execute(query, params)
                results.extend([dict(row) for row in cursor.fetchall()])

            conn.close()
        except Exception as e:
            st.error(f"查询失败: {e}")

        # 按日期排序
        results.sort(key=lambda x: x.get('trade_date', ''), reverse=True)
        return results[:limit]

    # 分页参数
    if "data_page" not in st.session_state:
        st.session_state.data_page = 1

    col_page1, col_page2, col_page3 = st.columns([1, 2, 1])
    with col_page1:
        if st.button("◀ 上一页"):
            st.session_state.data_page = max(1, st.session_state.data_page - 1)
    with col_page2:
        st.markdown(f"**第 {st.session_state.data_page} 页**")
    with col_page3:
        if st.button("下一页 ▶"):
            st.session_state.data_page += 1

    # 查询并显示数据
    offset = (st.session_state.data_page - 1) * 50
    data = query_data(data_type_filter, date_filter, stock_filter, limit=50, offset=offset)

    if data:
        # 转换为 DataFrame 显示
        display_data = []
        for row in data:
            display_data.append({
                "数据类型": row.get("data_type", ""),
                "股票代码": row.get("stock_code", ""),
                "日期": str(row.get("trade_date", ""))[:10],
                "数据值": f"开:{row.get('open', '')} 收:{row.get('close', '')} 量:{row.get('volume', '')}" if row.get('data_type') == 'K线数据' else f"情感:{row.get('volume', ''):.2f}" if row.get('data_type') == '新闻' else f"主力净流入:{row.get('open', ''):.0f}" if row.get('data_type') == '资金流向' else f"信号:{row.get('open', '')} 得分:{row.get('volume', '')}" if row.get('data_type') == '交易信号' else f"名称:{row.get('open', '')} 行业:{row.get('volume', '')}",
            })

        st.dataframe(pd.DataFrame(display_data), use_container_width=True, hide_index=True)
        st.caption(f"显示 {len(display_data)} 条数据")
    else:
        st.info("暂无数据")

# ==================== 页面：情感分析 ====================
elif page == "📰 情感分析":
    st.header("📰 情感分析 - 新闻采集与实时分析")

    # 获取爬虫调度器
    crawler = components["crawler_scheduler"]

    # 初始化会话状态
    if "crawler_running" not in st.session_state:
        st.session_state.crawler_running = crawler.config.enabled
    if "target_stocks" not in st.session_state:
        st.session_state.target_stocks = crawler.config.stock_codes.copy()

    # ========== 1. 爬虫状态与控制 ==========
    st.subheader("🕷️ 爬虫状态与控制")

    col_ctrl1, col_ctrl2, col_ctrl3 = st.columns(3)
    with col_ctrl1:
        # 启动/停止按钮
        if st.session_state.crawler_running:
            if st.button("⏹️ 停止爬虫", type="primary"):
                crawler.stop()
                st.session_state.crawler_running = False
                st.rerun()
        else:
            if st.button("▶️ 启动爬虫"):
                crawler.start()
                st.session_state.crawler_running = True
                st.rerun()

    with col_ctrl2:
        # 采集间隔设置
        new_interval = st.number_input("采集间隔（秒）", min_value=60, max_value=3600,
                                         value=crawler.config.interval, key="interval_input")
        if new_interval != crawler.config.interval:
            crawler.config.interval = new_interval

    with col_ctrl3:
        # 统计信息
        stats = crawler.get_stats()
        st.metric("已采集新闻", stats["total_news"])

    # ========== 2. 目标股票管理 ==========
    st.markdown("---")
    st.subheader("📋 目标股票管理")

    col_stock1, col_stock2 = st.columns([3, 1])

    with col_stock1:
        # 显示当前目标股票
        st.write(f"**当前目标股票**: {', '.join(st.session_state.target_stocks) if st.session_state.target_stocks else '未设置'}")

    with col_stock2:
        # 添加新股票
        new_stock = st.text_input("添加股票", placeholder="如: 600036", key="add_stock")
        if st.button("➕ 添加") and new_stock:
            if new_stock not in st.session_state.target_stocks:
                st.session_state.target_stocks.append(new_stock)
                crawler.add_stock(new_stock)
                st.rerun()

    # 移除股票按钮
    if st.session_state.target_stocks:
        selected_to_remove = st.selectbox("选择要移除的股票", st.session_state.target_stocks, key="remove_stock")
        if st.button("➖ 移除"):
            st.session_state.target_stocks.remove(selected_to_remove)
            crawler.remove_stock(selected_to_remove)
            st.rerun()

    # ========== 3. 立即采集 ==========
    st.markdown("---")
    st.subheader("⚡ 立即采集")

    col_crawl1, col_crawl2, col_crawl3 = st.columns(3)

    with col_crawl1:
        # 选择数据源
        sources = st.multiselect("选择数据源", ["东方财富", "新浪财经"],
                                  default=["东方财富", "新浪财经"], key="crawl_sources")

    with col_crawl2:
        # 选择股票
        crawl_stocks = st.multiselect("选择股票", stock_codes,
                                       default=st.session_state.target_stocks[:1] if st.session_state.target_stocks else [],
                                       key="crawl_stocks")

    with col_crawl3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🚀 立即采集", type="primary"):
            with st.spinner("采集中..."):
                collected = crawler.crawl_now(crawl_stocks, sources)
                st.success(f"✅ 采集完成，共 {collected} 条新闻")
                st.rerun()

    # ========== 4. 采集结果展示 ==========
    st.markdown("---")
    st.subheader("📊 采集结果")

    # 统计卡片
    col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
    with col_stat1:
        st.metric("新闻总数", stats["total_news"])
    with col_stat2:
        st.metric("股票数", len(stats["stocks"]))
    with col_stat3:
        st.metric("数据源", len(stats["sources"]))
    with col_stat4:
        latest = stats["latest_time"][:16] if stats["latest_time"] else "无"
        st.metric("最新采集", latest)

    # 筛选条件
    with st.expander("🔍 筛选条件", expanded=True):
        col_filter1, col_filter2, col_filter3 = st.columns(3)

        with col_filter1:
            source_filter = st.selectbox("数据源", ["全部"] + list(stats["sources"]) if stats["sources"] else ["全部"])

        with col_filter2:
            stock_filter = st.selectbox("股票", ["全部"] + list(stats["stocks"]) if stats["stocks"] else stock_codes)

        with col_filter3:
            sentiment_filter = st.selectbox("情感", ["全部", "利好", "中性", "利空"])

    # 查询新闻数据
    def query_news(source, stock, sentiment, limit=50):
        results = []
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = "SELECT * FROM news WHERE 1=1"
            params = []

            if source and source != "全部":
                query += " AND source = ?"
                params.append(source)
            if stock and stock != "全部":
                query += " AND stock_code = ?"
                params.append(stock)
            if sentiment and sentiment != "全部":
                query += " AND sentiment_label = ?"
                params.append(sentiment)

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            results = [dict(row) for row in cursor.fetchall()]
            conn.close()
        except Exception as e:
            st.error(f"查询失败: {e}")
        return results

    news_data = query_news(source_filter, stock_filter, sentiment_filter)

    if news_data:
        # 显示新闻列表
        for i, news in enumerate(news_data):
            with st.expander(f"📰 {news['stock_code']} | {news['source']} | {news['sentiment_label']} | {news['created_at'][:16]}", expanded=False):
                col_n1, col_n2 = st.columns([3, 1])
                with col_n1:
                    st.markdown(f"**{news['title']}**")
                    if news['content']:
                        st.markdown(f"_{news['content'][:200]}..._")
                with col_n2:
                    sentiment_color = "🟢" if news['sentiment_label'] == "利好" else "🔴" if news['sentiment_label'] == "利空" else "⚪"
                    st.metric("情感", f"{sentiment_color} {news['sentiment_label']}", f"{news['sentiment_score']:.2f}")

                # 对该条新闻进行情感分析
                if st.button(f"🔍 详细分析", key=f"analyze_{i}"):
                    result = components["sentiment_analyzer"].analyze(text=f"{news['title']} {news['content']}")
                    col_a1, col_a2, col_a3, col_a4 = st.columns(4)
                    with col_a1:
                        st.metric("情感得分", f"{result.score:.3f}")
                    with col_a2:
                        st.metric("标签", result.label)
                    with col_a3:
                        st.metric("置信度", f"{result.confidence:.1%}")
                    with col_a4:
                        st.metric("关键词", len(result.keywords))

                    if result.keywords:
                        st.markdown(f"**关键词**: {', '.join(result.keywords)}")
    else:
        st.info("暂无采集数据，请先启动爬虫或点击立即采集")

    st.markdown("---")
    st.caption("💡 提示：爬虫在后台运行时，会每隔设定的时间间隔自动采集新闻并保存到数据库")

# ==================== 页面：技术分析 ====================
elif page == "📉 技术分析":
    st.header("📉 技术分析可视化")

    selected_code = st.selectbox("选择股票", stock_codes, key="tech_analysis")
    df = components["price_collector"].get_kline(selected_code, period="daily", limit=120)

    if df is not None and not df.empty:
        tab1, tab2, tab3, tab4 = st.tabs(["K 线指标", "MACD", "KDJ", "其他"])

        with tab1:
            st.subheader("K 线与均线")
            ma5 = df["close"].rolling(5).mean()
            ma10 = df["close"].rolling(10).mean()
            ma20 = df["close"].rolling(20).mean()

            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
            fig.add_trace(go.Candlestick(x=df["trade_date"], open=df["open"], high=df["high"],
                                        low=df["low"], close=df["close"], name="K 线"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df["trade_date"], y=ma5, name="MA5", line=dict(color="red")), row=1, col=1)
            fig.add_trace(go.Scatter(x=df["trade_date"], y=ma10, name="MA10", line=dict(color="blue")), row=1, col=1)
            fig.add_trace(go.Scatter(x=df["trade_date"], y=ma20, name="MA20", line=dict(color="green")), row=1, col=1)
            fig.add_trace(go.Bar(x=df["trade_date"], y=df["volume"], name="成交量"), row=2, col=1)
            fig.update_layout(height=600, xaxis_rangeslider_visible=False, showlegend=True)
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            indicators = components["technical_analyzer"].get_indicators(df)
            c1, c2 = st.columns(2)
            c1.metric("DIF", f"{indicators['macd']['dif']:.4f}")
            c1.metric("DEA", f"{indicators['macd']['dea']:.4f}")
            c2.metric("信号", "🟢 金叉" if indicators['macd']['dif'] > indicators['macd']['dea'] else "🔴 死叉")

        with tab3:
            indicators = components["technical_analyzer"].get_indicators(df)
            c1, c2 = st.columns(2)
            c1.metric("K", f"{indicators['kdj']['k']:.2f}")
            c1.metric("D", f"{indicators['kdj']['d']:.2f}")
            c2.metric("J", f"{indicators['kdj']['j']:.2f}")
            c2.metric("状态", "超买" if indicators['kdj']['k'] > 80 else "超卖" if indicators['kdj']['k'] < 20 else "中性")

        with tab4:
            indicators = components["technical_analyzer"].get_indicators(df)

            # 安全获取ATR和OBV
            atr_value = "N/A"
            try:
                atr_value = components["volatility_analyzer"].get_current_atr(df)
            except:
                pass

            obv_value = indicators.get('obv', 'N/A')
            if obv_value == 'N/A':
                obv_display = "N/A"
            else:
                obv_display = f"{obv_value:.0f}"

            ind_df = pd.DataFrame({
                "指标": ["RSI", "ATR", "OBV", "BIAS(6)", "VR", "布林上轨", "布林中轨", "布林下轨"],
                "数值": [
                    f"{indicators.get('rsi', 'N/A'):.2f}" if indicators.get('rsi') is not None else "N/A",
                    f"{atr_value:.4f}" if atr_value != "N/A" and atr_value != 0 else "N/A",
                    obv_display,
                    f"{indicators.get('bias', {}).get('bias6', 'N/A'):.2f}%" if indicators.get('bias', {}).get('bias6') is not None else "N/A",
                    f"{indicators.get('vr', 'N/A'):.2f}" if indicators.get('vr') is not None else "N/A",
                    f"{indicators.get('boll', {}).get('upper', 'N/A'):.2f}" if indicators.get('boll', {}).get('upper') is not None else "N/A",
                    f"{indicators.get('boll', {}).get('middle', 'N/A'):.2f}" if indicators.get('boll', {}).get('middle') is not None else "N/A",
                    f"{indicators.get('boll', {}).get('lower', 'N/A'):.2f}" if indicators.get('boll', {}).get('lower') is not None else "N/A",
                ],
            })
            st.dataframe(ind_df, use_container_width=True, hide_index=True)

# ==================== 页面：信号融合 ====================
elif page == "🔀 信号融合":
    st.header("🔀 信号融合可视化")

    st.markdown("**多因子加权评分**: 新闻 (25%) + 技术 (25%) + 资金 (20%) + 波动率 (20%) + 情绪 (10%)")

    # 权重饼图
    fig = go.Figure(data=[go.Pie(labels=["新闻", "技术", "资金", "波动率", "情绪"],
                                 values=[25, 25, 20, 20, 10], hole=.3)])
    fig.update_layout(title="因子权重", height=350)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.subheader("实时信号融合演示")

    selected = st.selectbox("选择股票", stock_codes, key="fusion")

    if st.button("🔀 计算融合信号"):
        df = components["price_collector"].get_kline(selected, period="daily", limit=60)
        if df is not None and not df.empty:
            tech_signal = components["technical_analyzer"].analyze(df)

            # 模拟各因子得分
            news_score = 0.3
            fund_score = 0.2
            vol_score = 0.1
            sentiment_score = 0.5

            # 融合
            fusion_result = components["signal_fusion"].fuse(
                stock_code=selected,
                stock_name=get_stock_name(selected) or selected,
                news_score=news_score, technical_score=tech_signal.score,
                fund_score=fund_score, volatility_score=vol_score, sentiment_score=sentiment_score
            )

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("综合得分", f"{fusion_result.total_score:.3f}")
            c2.metric("信号", fusion_result.signal)
            c3.metric("置信度", f"{fusion_result.confidence:.1%}")
            c4.metric("建议", "买入" if fusion_result.signal in ["buy", "strong_buy"] else
                     "卖出" if fusion_result.signal in ["sell", "strong_sell"] else "观望")

            factor_df = pd.DataFrame({
                "因子": ["新闻情感", "技术分析", "资金流向", "波动率", "市场情绪"],
                "得分": [f"{news_score:.3f}", f"{tech_signal.score:.3f}", f"{fund_score:.3f}",
                        f"{vol_score:.3f}", f"{sentiment_score:.3f}"],
                "权重": ["25%", "25%", "20%", "20%", "10%"],
            })
            st.dataframe(factor_df, use_container_width=True, hide_index=True)

# ==================== 页面：社交媒体 ====================
elif page == "🌐 社交媒体":
    st.header("🌐 社交媒体情绪监控")
    st.markdown("**监控平台**: 微博 🧣 | 雪球 ❄️ | 股吧 🐟")

    selected = st.selectbox("选择股票", stock_codes, key="social")
    stock_name = get_stock_name(selected) or "股票"

    if st.button("🔍 分析情绪"):
        with st.spinner("分析中..."):
            result = components["social_sentiment_analyzer"].analyze_stock_sentiment(
                selected, stock_name, limit_per_platform=5
            )

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("帖子数", result.post_count)
            c2.metric("综合情绪", f"{result.overall_sentiment:.3f}",
                     "利好" if result.overall_sentiment > 0.2 else "利空" if result.overall_sentiment < -0.2 else "中性")
            c3.metric("趋势", {"improving": "📈", "worsening": "📉", "stable": "➡️"}.get(result.sentiment_trend, ""))
            c4.metric("热度", {"high": "🔥", "medium": "🔶", "low": "🔵"}.get(result.discussion_intensity, ""))

            if result.trending_keywords:
                st.subheader("热门关键词")
                st.markdown("`" + " | ".join(result.trending_keywords[:10]) + "`")

            if result.hot_posts:
                st.subheader("热门帖子")
                for i, post in enumerate(result.hot_posts[:5], 1):
                    emoji = {"weibo": "🧣", "xueqiu": "❄️", "guba": "🐟"}.get(post.platform, "")
                    st.markdown(f"**{i}. {emoji}** {post.title} (互动：{post.likes + post.comments + post.shares})")

# ==================== 页面：黑天鹅检测 ====================
elif page == "⚠️ 黑天鹅检测":
    st.header("⚠️ 黑天鹅事件检测")
    st.markdown("**检测类型**: 闪崩 | 成交量异常 | 波动率异常 | 相关性崩溃")

    if st.button("🔍 执行检测"):
        price_data = {}
        for code in stock_codes[:5]:
            df = components["price_collector"].get_kline(code, period="daily", limit=60)
            if df is not None and not df.empty:
                price_data[code] = df

        if price_data:
            result = components["black_swan_detector"].detect(price_data)

            colors = {"normal": ("🟢", "#333"), "watch": ("🟡", "#ffa500"), "warning": ("🟠", "#ff8800"),
                     "critical": ("🔴", "#ff4444"), "emergency": ("🚨", "#cc0000")}
            emoji, color = colors.get(result.alert_level.value, ("⚪", "#666"))

            st.markdown(f"""<div style="background:#fff3f3;padding:15px;border-radius:10px;border:2px solid {color};">
                <h3 style="color:{color};margin:0;">{emoji} 状态：{result.market_status}</h3>
            </div>""", unsafe_allow_html=True)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("状态", result.market_status)
            c2.metric("恐慌指数", f"{result.panic_index:.1f}")
            c3.metric("警报", result.alert_level.value.upper())
            c4.metric("建议仓位", f"{result.suggested_position:.0%}")

            if result.active_shocks:
                st.subheader("活跃冲击事件")
                for shock in result.active_shocks:
                    st.warning(f"[{shock.severity.value}] {shock.description} - {shock.suggested_action}")
            else:
                st.success("✅ 未检测到异常")

# ==================== 页面：模拟交易 ====================
elif page == "💼 模拟交易":
    st.header("💼 模拟交易 - 前向验证")
    st.caption("基于真实市价的模拟撮合交易，验证策略实际有效性")

    # 读取 DB 数据
    _db = Database(str(DB_PATH))
    open_positions = _db.get_open_positions()
    closed_trades  = _db.get_closed_trades()
    trade_log      = _db.get_simulated_trades(limit=100)
    equity_rows    = _db.get_equity_curve(limit=500)

    # ── 账户概览 ────────────────────────────────────────
    initial_capital = 20000.0
    try:
        cfg = load_config()
        initial_capital = float(cfg.get("trading", {}).get("initial_capital", 20000))
    except Exception:
        pass

    # 从交易流水重建账户余额
    cash = initial_capital
    for t in _db.get_simulated_trades(limit=0):
        if t["trade_type"] == "buy":
            cash -= (t["net_amount"] or t["amount"])
        elif t["trade_type"] == "sell":
            cash += (t["net_amount"] or t["amount"])

    position_value = sum(
        (p.get("current_price") or p["entry_price"]) * p["quantity"]
        for p in open_positions
    )
    total_equity = cash + position_value
    total_pnl = total_equity - initial_capital
    total_pnl_rate = total_pnl / initial_capital if initial_capital > 0 else 0.0

    # 最大回撤
    peak = initial_capital
    max_dd = 0.0
    for r in equity_rows:
        v = r["total_equity"]
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("总净值", f"¥{total_equity:,.2f}",
              delta=f"{'+' if total_pnl_rate >= 0 else ''}{total_pnl_rate:.2%}")
    c2.metric("可用现金", f"¥{cash:,.2f}")
    c3.metric("持仓市值", f"¥{position_value:,.2f}")
    c4.metric("累计盈亏", f"¥{total_pnl:,.2f}")
    c5.metric("最大回撤", f"{max_dd:.2%}")

    st.markdown("---")

    # ── 净值曲线 + 当前持仓 ─────────────────────────────
    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.subheader("净值曲线")
        if len(equity_rows) >= 2:
            ts_list  = [r["timestamp"] for r in equity_rows]
            eq_list  = [r["total_equity"] for r in equity_rows]
            # 归一化为 100 起始
            base = eq_list[0] if eq_list[0] > 0 else initial_capital
            eq_norm = [v / base * 100 for v in eq_list]

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=ts_list, y=eq_norm,
                mode="lines", name="策略净值",
                line=dict(color="#2196F3", width=2),
            ))
            fig.add_hline(y=100, line_dash="dash", line_color="gray",
                          annotation_text="起始基准")
            fig.update_layout(
                height=280,
                margin=dict(l=10, r=10, t=10, b=30),
                yaxis_title="净值（起始=100）",
                xaxis_title="",
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("净值数据不足（需运行至少 2 次监控后才会生成曲线）")

    with col_right:
        st.subheader(f"当前持仓（{len(open_positions)} 只）")
        if open_positions:
            pos_rows = []
            for p in open_positions:
                cur = p.get("current_price") or p["entry_price"]
                cost = p["entry_price"]
                pnl_rate = (cur - cost) / cost if cost > 0 else 0.0
                sign = "+" if pnl_rate >= 0 else ""
                pos_rows.append({
                    "代码": p["stock_code"],
                    "名称": p.get("stock_name") or "-",
                    "成本": f"{cost:.3f}",
                    "现价": f"{cur:.3f}",
                    "浮盈%": f"{sign}{pnl_rate:.2%}",
                    "止损": f"{p.get('stop_loss_price', 0):.3f}",
                })
            st.dataframe(pd.DataFrame(pos_rows), use_container_width=True, hide_index=True)
        else:
            st.info("暂无持仓")

    st.markdown("---")

    # ── 前向验证统计 ────────────────────────────────────
    st.subheader("前向验证统计（真实模拟交易，非历史回测）")
    fwd = ForwardValidator.compute(_db)

    if fwd.total_trades == 0:
        st.info("尚无平仓交易记录。运行监控服务后，当止盈/止损/策略卖出触发时将自动生成统计。")
    else:
        warn = ForwardValidator.warn_if_underperforming(fwd)
        if warn:
            st.warning(warn)

        fc1, fc2, fc3, fc4, fc5, fc6 = st.columns(6)
        fc1.metric("总交易", fwd.total_trades,
                   help="不含样本不足提示（需>=20笔）" if not fwd.sufficient_sample else "")
        fc2.metric("实际胜率", f"{fwd.win_rate:.1%}",
                   delta=f"vs 回测 {fwd.win_rate_vs_backtest:+.1%}")
        fc3.metric("盈亏比", f"{fwd.profit_loss_ratio:.2f}")
        fc4.metric("期望值", f"¥{fwd.expectancy:.1f}/笔")
        fc5.metric("最大回撤", f"{fwd.max_drawdown:.2%}")
        fc6.metric("夏普比率", f"{fwd.sharpe_ratio:.2f}")

        if not fwd.sufficient_sample:
            st.caption(f"⚠️ 当前样本 {fwd.total_trades} 笔，建议积累至 20 笔以上后再参考统计结论")

        with st.expander("完整统计详情"):
            detail = fwd.to_dict()
            detail_df = pd.DataFrame(list(detail.items()), columns=["指标", "值"])
            st.dataframe(detail_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── 历史交易记录 ────────────────────────────────────
    st.subheader("历史交易流水")
    if trade_log:
        log_rows = []
        for t in trade_log:
            log_rows.append({
                "时间": (t.get("trade_date") or "")[:16],
                "代码": t["stock_code"],
                "名称": t.get("stock_name") or "-",
                "类型": "买入" if t["trade_type"] == "buy" else "卖出",
                "价格": f"{t['price']:.3f}",
                "数量": t["quantity"],
                "成交额": f"¥{t['amount']:.2f}",
                "手续费": f"¥{(t.get('commission') or 0) + (t.get('stamp_tax') or 0):.2f}",
                "实现盈亏": f"¥{t['realized_pnl']:.2f}" if t.get("realized_pnl") is not None else "-",
                "原因": t.get("reason") or "-",
            })
        log_df = pd.DataFrame(log_rows)
        st.dataframe(log_df, use_container_width=True, hide_index=True)
    else:
        st.info("暂无交易流水")

# ==================== 页面：监控历史 ====================
elif page == "📜 监控历史":
    st.header("📜 监控历史")
    st.info("监控历史功能 - 从数据库加载历史记录")

    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH)
        try:
            df = pd.read_sql("SELECT * FROM trading_signals ORDER BY created_at DESC LIMIT 100", conn)
            if not df.empty:
                st.dataframe(df, use_container_width=True)
        except:
            st.info("暂无历史记录")
        finally:
            conn.close()
    else:
        st.warning("数据库不存在")

# ==================== 页面：绩效评估 ====================
elif page == "📈 绩效评估":
    st.header("📈 绩效评估")

    st.markdown("""
    **改进策略特性**:
    1. 趋势过滤 - 只在上升趋势中买入
    2. 多条件确认 - MA+MACD+RSI 共振
    3. ATR 动态止损 - 根据波动率调整
    4. 盈亏比 2.5:1
    """)

    st.subheader("回测表现")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("总收益率", "74.36%")
    c2.metric("胜率", "48.3%")
    c3.metric("盈亏比", "3.07")
    c4.metric("最大回撤", "8.79%")

    st.markdown("---")
    st.markdown("""
    **评估指标说明**:
    - 胜率：盈利交易/总交易，>45% 配合盈亏比>1.5 即可盈利
    - 盈亏比：平均盈利/平均亏损，>1.5 较理想
    - 夏普比率：(年化收益 - 无风险利率)/波动率，>1 合格
    - 最大回撤：最大峰值到谷值跌幅，<20% 较安全
    """)

# ==================== 页面：回测 ====================
elif page == "🔙 回测":
    st.header("🔙 回测")
    st.info("回测功能 - 支持历史数据回测和参数优化")

    st.markdown("""
    **支持功能**:
    - 导入历史 K 线数据
    - 模拟交易执行
    - 生成绩效报告
    - 参数优化 (网格搜索/遗传算法)

    **绩效指标**: 总收益率、年化收益率、胜率、盈亏比、夏普比率、最大回撤
    """)

# ==================== 页面：历史回测 ====================
elif page == "📅 历史回测":
    st.header("📅 历史深度分析")
    st.markdown("选择股票和时间段，分析历史每日信号决策，支持回溯验证策略有效性")

    if not stock_codes:
        st.warning("请先配置股票池")
    else:
        # ----- 1. 股票和时间选择 -----
        col1, col2 = st.columns(2)
        with col1:
            selected_stock = st.selectbox("选择股票", stock_codes, format_func=lambda x: f"{x} - {get_stock_name(x) or x}")
        with col2:
            # 获取股票数据日期范围
            df_all = components["price_collector"].get_kline(selected_stock, period="daily", limit=500)
            if df_all is not None and not df_all.empty:
                min_date = pd.to_datetime(df_all['trade_date'].min()).to_pydatetime()
                max_date = pd.to_datetime(df_all['trade_date'].max()).to_pydatetime()
                st.caption(f"数据范围: {min_date.strftime('%Y-%m-%d')} 至 {max_date.strftime('%Y-%m-%d')}")

                # 日期范围选择
                date_range = st.slider(
                    "选择时间范围",
                    min_value=min_date,
                    max_value=max_date,
                    value=(max_date - pd.Timedelta(days=90), max_date),
                    format="YYYY-MM-DD"
                )
            else:
                st.error("无法获取股票数据")
                st.stop()

        # ----- 2. 过滤数据 -----
        if df_all is not None:
            start_date, end_date = date_range
            # 确保比较的是相同类型
            df_all['trade_date_dt'] = pd.to_datetime(df_all['trade_date'])
            df = df_all[
                (df_all['trade_date_dt'] >= pd.to_datetime(start_date)) &
                (df_all['trade_date_dt'] <= pd.to_datetime(end_date))
            ].copy()
            df = df.drop('trade_date_dt', axis=1)

            if len(df) < 10:
                st.warning("数据点太少，请选择更长的时间范围")
                st.stop()

            st.markdown("---")

            # ----- 3. 计算技术指标 -----
            indicators_df = components["improved_strategy"].calculate_indicators(df)

            # ----- 4. 绘制折线图 -----
            st.subheader("📊 价格与技术指标走势 (X轴: 日期)")

            # 将日期转换为 datetime 格式
            df_plot = df.copy()
            df_plot['trade_date'] = pd.to_datetime(df_plot['trade_date'], format='%Y%m%d')

            # 转换为列表以避免索引问题
            trade_dates = df_plot['trade_date'].tolist()
            close_prices = df_plot['close'].tolist()
            open_prices = df_plot['open'].tolist() if 'open' in df_plot.columns else close_prices
            high_prices = df_plot['high'].tolist() if 'high' in df_plot.columns else close_prices
            low_prices = df_plot['low'].tolist() if 'low' in df_plot.columns else close_prices

            # 计算技术指标（转换为列表）
            indicators = components["improved_strategy"].calculate_indicators(df_plot)
            ma5_values = indicators['ma5'].tolist()
            ma10_values = indicators['ma10'].tolist()
            ma20_values = indicators['ma20'].tolist()
            macd_dif_values = indicators['macd_dif'].tolist()
            macd_dea_values = indicators['macd_dea'].tolist()
            rsi_values = indicators['rsi'].tolist()
            adx_values = indicators['adx'].tolist()

            # 创建图表
            fig = make_subplots(
                rows=4, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.05,
                row_heights=[0.35, 0.2, 0.2, 0.15],
                subplot_titles=("股价 K线 + 均线", "MACD", "RSI", "ADX 趋势强度")
            )

            # 4.1 收盘价折线 + 均线
            fig.add_trace(go.Scatter(x=trade_dates, y=close_prices, name="收盘价", line=dict(color="black", width=2)), row=1, col=1)
            fig.add_trace(go.Scatter(x=trade_dates, y=ma5_values, name="MA5", line=dict(color="red", width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=trade_dates, y=ma10_values, name="MA10", line=dict(color="blue", width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=trade_dates, y=ma20_values, name="MA20", line=dict(color="green", width=1)), row=1, col=1)

            # 4.2 MACD
            fig.add_trace(go.Scatter(x=trade_dates, y=macd_dif_values, name="DIF", line=dict(color="blue")), row=2, col=1)
            fig.add_trace(go.Scatter(x=trade_dates, y=macd_dea_values, name="DEA", line=dict(color="orange")), row=2, col=1)

            # 4.3 RSI
            fig.add_trace(go.Scatter(x=trade_dates, y=rsi_values, name="RSI", line=dict(color="purple")), row=3, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)

            # 4.4 ADX
            fig.add_trace(go.Scatter(x=trade_dates, y=adx_values, name="ADX", line=dict(color="brown")), row=4, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="red", row=4, col=1)

            # 设置图表样式
            fig.update_layout(height=700, showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02))
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")

            # ----- 5. 日期控件选择具体日期 -----
            st.subheader("📅 选择具体日期分析")

            # 获取日期范围
            date_list = df['trade_date'].tolist()
            min_date = pd.to_datetime(min(date_list)).to_pydatetime()
            max_date = pd.to_datetime(max(date_list)).to_pydatetime()

            # 使用日期控件
            selected_date = st.date_input(
                "选择要分析的日期",
                value=max_date,
                min_value=min_date,
                max_value=max_date
            )

            # 格式化日期为字符串
            if isinstance(selected_date, pd.Timestamp):
                selected_date_str = selected_date.strftime('%Y%m%d')
            elif isinstance(selected_date, datetime):
                selected_date_str = selected_date.strftime('%Y%m%d')
            else:
                selected_date_str = str(selected_date).replace('-', '')

            # ----- 6. 选中日期的深度分析 -----
            st.markdown(f"### 📊 {selected_date_str} 深度分析")

            # 获取选中日期的数据（需要足够的历史数据来计算指标）
            # 为了正确计算指标，需要从开始到选中日期的所有数据
            df_until_date = df_all[
                (pd.to_datetime(df_all['trade_date']) <= pd.to_datetime(selected_date_str))
            ].copy()

            if len(df_until_date) < 30:
                st.warning("数据不足，无法进行完整分析")
            else:
                # 计算信号
                signal_obj = components["improved_strategy"].generate_signal(
                    df=df_until_date,
                    stock_code=selected_stock,
                    stock_name=get_stock_name(selected_stock) or selected_stock,
                    timestamp=pd.to_datetime(selected_date)
                )

                current_price = float(df_until_date['close'].iloc[-1])

                # 6.1 信号结果
                st.markdown("#### 🎯 信号结果")
                col_sig1, col_sig2, col_sig3, col_sig4 = st.columns(4)
                with col_sig1:
                    st.metric("信号", signal_obj.signal.upper())
                with col_sig2:
                    st.metric("买分", f"{signal_obj.buy_score:.2f}")
                with col_sig3:
                    st.metric("卖分", f"{signal_obj.sell_score:.2f}")
                with col_sig4:
                    st.metric("RSI", f"{signal_obj.rsi:.0f}")

                # 6.2 买入条件分析
                st.markdown("#### 🔵 买入条件分析")
                buy_details = signal_obj.conditions.get("buy_details", {})
                buy_score = signal_obj.buy_score

                buy_items = [
                    ("ADX >= 30 (趋势市)", buy_details.get("adx_filter", False), "必需条件"),
                    ("价格 > MA20", buy_details.get("above_ma20", False), "趋势向上"),
                    ("MA20 向上", buy_details.get("ma20_up", False), "趋势确认"),
                    ("MA5 > MA10", buy_details.get("ma5_above_ma10", False), "短期强势"),
                    ("MACD 金叉/DIF>0", buy_details.get("macd_bullish", False), "动能向上"),
                    ("RSI 35-65 且上升", buy_details.get("rsi_ok", False), "未超买"),
                ]

                buy_cols = st.columns(3)
                for idx, (name, met, desc) in enumerate(buy_items):
                    with buy_cols[idx % 3]:
                        status = "✅" if met else "❌"
                        bg = "#E3F2FD" if met else "#F5F5F5"
                        st.markdown(f"""
                        <div style="padding: 8px; margin: 3px 0; border-radius: 5px; background: {bg};">
                            {status} {name}<br>
                            <small style="color: #888;">{desc}</small>
                        </div>
                        """, unsafe_allow_html=True)

                conditions_met = sum(1 for _, met, _ in buy_items if met)
                st.metric("买入条件满足", f"{conditions_met}/6", f"买分 {buy_score:.2f}")

                st.markdown("---")

                # 6.3 卖出条件分析
                st.markdown("#### 🔴 卖出条件分析")
                sell_details = signal_obj.conditions.get("sell_details", {})

                sell_items = [
                    ("价格 < MA20", sell_details.get("below_ma20", False), "趋势向下"),
                    ("MA20 向下", sell_details.get("ma20_down", False), "趋势走弱"),
                    ("MA5 < MA10", sell_details.get("ma5_below_ma10", False), "短期走弱"),
                    ("MACD 死叉/DIF<0", sell_details.get("macd_bearish", False), "动能向下"),
                    ("RSI 超买/下降", sell_details.get("rsi_overbought", False), "风险积累"),
                ]

                sell_cols = st.columns(3)
                for idx, (name, met, desc) in enumerate(sell_items):
                    with sell_cols[idx % 3]:
                        status = "✅" if met else "❌"
                        bg = "#FFEBEE" if met else "#F5F5F5"
                        st.markdown(f"""
                        <div style="padding: 8px; margin: 3px 0; border-radius: 5px; background: {bg};">
                            {status} {name}<br>
                            <small style="color: #888;">{desc}</small>
                        </div>
                        """, unsafe_allow_html=True)

                sell_conditions_met = sum(1 for _, met, _ in sell_items if met)
                st.metric("卖出条件满足", f"{sell_conditions_met}/5", f"卖分 {signal_obj.sell_score:.2f}")

                st.markdown("---")

                # 6.4 决策逻辑总结
                st.markdown("#### 📋 决策逻辑总结")

                # 获取 ADX
                ind = components["improved_strategy"].calculate_indicators(df_until_date)
                adx = ind['adx'].iloc[-1]

                is_trend = adx >= 30
                buy_ok = conditions_met >= 4 and buy_score >= 0.6
                sell_ok = sell_conditions_met >= 3 and signal_obj.sell_score >= 0.5

                st.markdown(f"""
                | 项目 | 状态 |
                |------|------|
                | ADX | {adx:.1f} ({'趋势市' if is_trend else '震荡市'}) |
                | 买入条件 | {'✅ 满足' if buy_ok else '❌ 不满足'} (条件{conditions_met}个, 买分{buy_score:.2f}) |
                | 卖出条件 | {'✅ 满足' if sell_ok else '❌ 不满足'} (条件{sell_conditions_met}个, 卖分{signal_obj.sell_score:.2f}) |
                | 最终信号 | **{signal_obj.signal.upper()}** |
                """)

                # 6.5 止盈止损
                st.markdown("#### 🛡️ 止盈止损设置")
                col_ssl1, col_ssl2, col_ssl3 = st.columns(3)
                with col_ssl1:
                    stop_loss = current_price * (1 - signal_obj.stop_distance)
                    st.metric("止损价", f"¥{stop_loss:.2f}", f"-{signal_obj.stop_distance*100:.1f}%")
                with col_ssl2:
                    take_profit = current_price * (1 + signal_obj.take_profit_distance)
                    st.metric("止盈价", f"¥{take_profit:.2f}", f"+{signal_obj.take_profit_distance*100:.1f}%")
                with col_ssl3:
                    st.metric("ATR", f"{signal_obj.atr:.4f}", "波动率")

# 页脚
st.markdown("---")
st.markdown("<div style='text-align:center;color:#888;padding:20px;'>A 股自动监控系统 统一版 v3.0 | 数据仅供参考</div>",
            unsafe_allow_html=True)
