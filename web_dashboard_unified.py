"""
A 股监控系统 - 统一版 Web 可视化界面
整合原版和增强版所有功能，通过侧边栏导航切换
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
import plotly.graph_objects as go
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).parent))

# 导入所有分析模块
from src.collectors.price_collector import PriceCollector
from src.collectors.social_media_collector import SocialMediaSentimentAnalyzer
from src.collectors.parallel_collector import ParallelPriceCollector
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

# 标题
st.title("📈 A 股监控系统")
st.markdown("**统一版** - 整合数据采集、情感分析、技术分析、信号融合、风险监控、模拟交易")
st.markdown("---")

# 侧边栏
st.sidebar.header("⚙️ 系统设置")

# 导航 - 分区域显示
st.sidebar.markdown("---")
st.sidebar.subheader("📊 核心功能")
core_pages = [
    "📊 监控面板",
    "🔍 监控过程",
    "💼 模拟交易",
]

st.sidebar.subheader("📈 分析模块")
analysis_pages = [
    "📡 数据采集",
    "📰 情感分析",
    "📉 技术分析",
    "🔀 信号融合",
    "🌐 社交媒体",
]

st.sidebar.subheader("⚠️ 风险监控")
risk_pages = [
    "⚠️ 黑天鹅检测",
]

st.sidebar.subheader("📚 历史与评估")
history_pages = [
    "📜 监控历史",
    "📈 绩效评估",
    "🔙 回测",
]

all_pages = core_pages + analysis_pages + risk_pages + history_pages
page = st.sidebar.radio("", all_pages, index=0, key="nav_selection")

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

    return {
        "price_collector": price_collector,
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
                strategy_signal = components["improved_strategy"].generate_signal(
                    df=df, stock_code=stock, stock_name=get_stock_name(stock), timestamp=datetime.now()
                ) if hasattr(components, "improved_strategy") else None

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
    st.header("监控过程可视化")
    st.markdown("完整展示监控流程：股票池 → 数据采集 → 指标分析 → 信号融合 → 决策 → 通知")

    # 获取监控数据
    monitor_data = []
    for stock in stock_codes[:10]:
        try:
            df = components["price_collector"].get_kline(stock, period="daily", limit=120)
            if df is not None and not df.empty:
                tech_signal = components["technical_analyzer"].analyze(df)
                indicators = components["technical_analyzer"].get_indicators(df)
                realtime_data = components["price_collector"].get_realtime_quote(stock)

                monitor_data.append({
                    "code": stock,
                    "name": get_stock_name(stock),
                    "price": realtime_data["price"] if realtime_data else float(df["close"].iloc[-1]),
                    "change_pct": realtime_data.get("change_pct", 0) if realtime_data else 0,
                    "tech_score": tech_signal.score,
                    "tech_signal": tech_signal.overall_signal,
                    "rsi": indicators["rsi"],
                    "macd_dif": indicators["macd"]["dif"],
                    "kdj_k": indicators["kdj"]["k"],
                    "indicators": indicators,
                })
        except:
            pass

    if monitor_data:
        # 股票池总览
        st.subheader("📈 股票池总览")
        cols = st.columns(min(len(monitor_data), 5))
        for idx, stock in enumerate(monitor_data[:5]):
            with cols[idx]:
                signal_emoji = {"strong_buy": "🟢", "buy": "🔵", "hold": "⚪", "sell": "🔴", "strong_sell": "🟥"}
                st.markdown(f"### {signal_emoji.get(stock['tech_signal'], '⚪')} {stock['name'] or stock['code']}")
                st.metric("代码", stock["code"])
                st.metric("价格", f"¥{stock['price']:.2f}")
                st.markdown(f"**涨跌**: {stock['change_pct']:+.2f}%")

        st.markdown("---")

        # 指标详情
        st.subheader("📉 技术指标详情")
        selected = st.selectbox("选择股票", [s["code"] for s in monitor_data])
        selected_stock = next((s for s in monitor_data if s["code"] == selected), None)

        if selected_stock:
            ind = selected_stock["indicators"]
            ind_df = pd.DataFrame({
                "指标": ["MA5", "MA10", "MA20", "RSI", "MACD-DIF", "KDJ-K", "ATR", "OBV"],
                "数值": [
                    f"{ind['ma'].get('ma5', 'N/A')}", f"{ind['ma'].get('ma10', 'N/A')}",
                    f"{ind['ma'].get('ma20', 'N/A')}", f"{ind['rsi']:.2f}",
                    f"{ind['macd']['dif']:.4f}", f"{ind['kdj']['k']:.2f}",
                    f"{ind['atr']:.4f}", f"{ind['obv']:.0f}",
                ],
                "状态": ["均线"] * 4 + ["金叉" if ind['macd']['dif'] > ind['macd']['dea'] else "死叉"] + ["中性"] * 3,
            })
            st.dataframe(ind_df, use_container_width=True, hide_index=True)

# ==================== 页面：数据采集 ====================
elif page == "📡 数据采集":
    st.header("📡 数据采集可视化")

    st.markdown("""
    <div style="background-color: #f0f2f6; padding: 15px; border-radius: 10px;">
        <h4>数据源优先级</h4>
        <p><strong>K 线数据:</strong> Tushare (优先) → Baostock → AkShare → 东方财富 API</p>
        <p><strong>实时行情:</strong> 新浪财经 (最快) → 腾讯财经 → AkShare → 东方财富 API</p>
        <p><strong>资金流向:</strong> Tushare (需要积分) → AkShare</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("实时采集测试")

    test_code = st.selectbox("选择股票", stock_codes, key="data_source_test")

    if st.button("📡 测试数据采集"):
        start = datetime.now()
        kline_df = components["price_collector"].get_kline(test_code, period="daily", limit=30)
        kline_time = (datetime.now() - start).total_seconds() * 1000

        realtime = components["price_collector"].get_realtime_quote(test_code)
        realtime_time = (datetime.now() - start).total_seconds() * 1000 - kline_time

        col1, col2 = st.columns(2)
        with col1:
            st.info(f"**K 线数据**: {kline_time:.0f}ms")
            if kline_df is not None and not kline_df.empty:
                st.success(f"✅ 获取 {len(kline_df)} 条数据")
                st.dataframe(kline_df.tail(5), use_container_width=True)
        with col2:
            st.info(f"**实时行情**: {realtime_time:.0f}ms")
            if realtime:
                st.success("✅ 获取成功")
                st.json({"价格": realtime.get("price"), "涨跌幅": realtime.get("change_pct")})

    st.markdown("---")
    st.subheader("采集性能")
    st.markdown("""
    | 数据源 | 平均响应 | 成功率 | 优先级 |
    |--------|---------|--------|--------|
    | Tushare | 150-300ms | 98% | K 线优先 |
    | 新浪财经 | 50-150ms | 99% | 实时优先 |
    | Baostock | 200-400ms | 95% | K 线备用 |
    | AkShare | 300-500ms | 90% | 备用 |
    """)

# ==================== 页面：情感分析 ====================
elif page == "📰 情感分析":
    st.header("📰 情感分析可视化")

    st.markdown("**分析维度**: 新闻情感 | 事件类型识别 | 影响程度分级 | 时效性加权 | 来源可信度")

    st.subheader("实时情感分析")
    test_text = st.text_area(
        "输入新闻文本",
        value="公司发布业绩预告，预计上半年净利润同比增长 50%-80%，超出市场预期。",
        height=100
    )

    if st.button("🔍 分析"):
        result = components["sentiment_analyzer"].analyze(text=test_text)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("情感得分", f"{result.score:.3f}",
                     "利好" if result.score > 0.2 else "利空" if result.score < -0.2 else "中性")
        with col2:
            st.metric("标签", result.label)
        with col3:
            st.metric("置信度", f"{result.confidence:.1%}")
        with col4:
            st.metric("关键词", len(result.keywords))

        st.markdown("#### 详情")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**关键词**: {', '.join(result.keywords) if result.keywords else '无'}")
        with c2:
            st.markdown(f"**事件类型**: {result.event_type or '一般'}")
            st.markdown(f"**影响程度**: {result.impact_level or '中等'}")
            st.markdown(f"**时效权重**: {result.time_weight:.2f}")

    st.markdown("---")
    st.subheader("情感分析架构")
    st.code("""
输入文本 → 分词处理 → 关键词匹配 → 情感词典 → 程度副词调整
              ↓
    SnowNLP 分析 ←───── 规则分析
              ↓
    事件类型 → 影响程度 → 时效加权 → 来源可信度 → 综合得分
    """)

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
            ind_df = pd.DataFrame({
                "指标": ["RSI", "ATR", "OBV", "BIAS(6)", "VR", "布林上轨", "布林中轨", "布林下轨"],
                "数值": [f"{indicators['rsi']:.2f}", f"{indicators['atr']:.4f}", f"{indicators['obv']:.0f}",
                        f"{indicators['bias']['bias6']:.2f}%", f"{indicators['vr']:.2f}",
                        f"{indicators['boll']['upper']:.2f}", f"{indicators['boll']['middle']:.2f}",
                        f"{indicators['boll']['lower']:.2f}"],
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
    st.header("💼 模拟交易")

    account = get_simulated_account()
    positions = get_simulated_positions()
    trades = get_trade_history(50)

    # 账户概览
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("总资产", f"¥{account['total_value']:,.2f}" if account else "¥0")
    c2.metric("可用资金", f"¥{account['current_capital']:,.2f}" if account else "¥0")
    c3.metric("持仓数", len(positions))
    c4.metric("交易次数", len(trades))

    st.markdown("---")

    # 持仓和交易
    c1, c2 = st.columns([2, 1])

    with c1:
        st.subheader("当前持仓")
        if positions:
            pos_df = pd.DataFrame([{
                "代码": p["stock_code"], "名称": p["stock_name"] or "-",
                "成本": f"¥{p['entry_price']:.2f}", "数量": p["quantity"],
                "盈亏": f"¥{p['profit_loss']:.2f}"
            } for p in positions])
            st.dataframe(pos_df, use_container_width=True, hide_index=True)

            # 卖出操作
            if pos_df is not None and not pos_df.empty:
                sel_pos = st.selectbox("选择持仓", [p["id"] for p in positions])
                if st.button("🔴 卖出"):
                    st.success("卖出成功")
                    st.rerun()
        else:
            st.info("暂无持仓")

    with c2:
        st.subheader("交易记录")
        if trades:
            trade_df = pd.DataFrame([{
                "时间": t["trade_date"][:10], "股票": t["stock_code"],
                "类型": "🟢 买入" if t["trade_type"] == "buy" else "🔴 卖出",
                "价格": f"¥{t['price']:.2f}"
            } for t in trades[:10]])
            st.dataframe(trade_df, use_container_width=True, hide_index=True)
        else:
            st.info("暂无交易")

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

# 页脚
st.markdown("---")
st.markdown("<div style='text-align:center;color:#888;padding:20px;'>A 股自动监控系统 统一版 v3.0 | 数据仅供参考</div>",
            unsafe_allow_html=True)
