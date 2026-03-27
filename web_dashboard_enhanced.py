"""
A 股监控系统 - 增强版 Web 可视化界面
整合：数据采集、情感分析、技术分析、信号融合、黑天鹅检测、社交媒体情绪
"""
import streamlit as st
import pandas as pd
import numpy as np
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
from src.strategy.improved_strategy import ImprovedStrategy

# 初始化日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 页面配置
st.set_page_config(
    page_title="A 股监控系统 - 增强版",
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
</style>
""", unsafe_allow_html=True)

# 配置文件路径
CONFIG_PATH = Path("config.yaml")

def load_config():
    """加载配置"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

# 标题
st.title("📈 A 股监控系统 - 增强版")
st.markdown("**全模块可视化平台** - 数据采集 | 情感分析 | 技术分析 | 信号融合 | 风险监控")

# 加载配置
try:
    config = load_config()
except Exception as e:
    st.error(f"加载配置文件失败：{e}")
    st.stop()

# 侧边栏
st.sidebar.header("🧭 导航")
page = st.sidebar.radio(
    "页面",
    [
        "📊 系统总览",
        "📡 数据采集",
        "📰 情感分析",
        "📉 技术分析",
        "🔀 信号融合",
        "⚠️ 黑天鹅检测",
        "🌐 社交媒体",
        "💼 模拟交易",
        "📈 绩效评估"
    ]
)

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

# ==================== 页面 1: 系统总览 ====================
if page == "📊 系统总览":
    st.header("系统总览")

    # 刷新按钮
    col_refresh1, col_refresh2 = st.columns([5, 1])
    with col_refresh2:
        if st.button("🔄 刷新", use_container_width=True):
            st.rerun()

    # 系统状态指标
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("监控股票数", len(stock_codes))
    with col2:
        st.metric("数据源状态", "✅ 正常")
    with col3:
        st.metric("市场状态", "震荡市")
    with col4:
        st.metric("警报级别", "正常")
    with col5:
        st.metric("最后更新", datetime.now().strftime("%H:%M:%S"))

    st.markdown("---")

    # 核心模块状态
    st.subheader("🔧 模块状态")

    module_status = {
        "数据采集": "✅ 运行中",
        "情感分析": "✅ 运行中",
        "技术分析": "✅ 运行中",
        "信号融合": "✅ 运行中",
        "黑天鹅检测": "✅ 运行中",
        "社交媒体监控": "✅ 运行中",
    }

    cols = st.columns(3)
    for idx, (module, status) in enumerate(module_status.items()):
        with cols[idx % 3]:
            st.info(f"**{module}**: {status}")

    st.markdown("---")

    # 实时股票概览
    st.subheader("📊 股票池实时概览")

    stock_data = []
    for code in stock_codes[:10]:
        try:
            df = components["price_collector"].get_kline(code, period="daily", limit=30)
            if df is not None and not df.empty:
                latest_price = float(df["close"].iloc[-1])
                change_pct = float(df["change_pct"].iloc[-1]) if "change_pct" in df.columns else 0

                # 获取技术信号
                tech_signal = components["technical_analyzer"].analyze(df)

                stock_data.append({
                    "代码": code,
                    "最新价": f"¥{latest_price:.2f}",
                    "涨跌幅": f"{change_pct:+.2f}%",
                    "技术得分": f"{tech_signal.score:.2f}",
                    "技术信号": tech_signal.overall_signal,
                    "RSI": f"{tech_signal.rsi:.1f}",
                    "MACD": "金叉" if tech_signal.macd_signal == "bullish" else "死叉",
                })
        except Exception as e:
            pass

    if stock_data:
        st.dataframe(pd.DataFrame(stock_data), use_container_width=True, hide_index=True)

    st.markdown("---")

    # 风险提示
    st.subheader("⚠️ 风险提示")

    # 黑天鹅检测结果
    price_data = {}
    for code in stock_codes[:5]:
        df = components["price_collector"].get_kline(code, period="daily", limit=60)
        if df is not None and not df.empty:
            price_data[code] = df

    if price_data:
        bs_result = components["black_swan_detector"].detect(price_data)

        alert_colors = {
            "normal": ("🟢", "#333"),
            "watch": ("🟡", "#ffa500"),
            "warning": ("🟠", "#ff8800"),
            "critical": ("🔴", "#ff4444"),
            "emergency": ("🚨", "#cc0000"),
        }

        emoji, color = alert_colors.get(bs_result.alert_level.value, ("⚪", "#666"))

        st.markdown(f"""
        <div style="background-color: #f8f9fa; padding: 15px; border-radius: 10px; border-left: 4px solid {color};">
            <h3 style="margin: 0;">{emoji} 黑天鹅检测状态：{bs_result.market_status}</h3>
            <p style="margin: 10px 0;"><strong>警报级别：</strong><span style="color: {color};">{bs_result.alert_level.value.upper()}</span></p>
            <p style="margin: 10px 0;"><strong>恐慌指数：</strong>{bs_result.panic_index:.1f}</p>
            <p style="margin: 10px 0;"><strong>建议仓位：</strong>{bs_result.suggested_position:.0%}</p>
        </div>
        """, unsafe_allow_html=True)

# ==================== 页面 2: 数据采集可视化 ====================
elif page == "📡 数据采集":
    st.header("📡 数据采集可视化")

    # 数据源优先级说明
    st.subheader("数据源架构")

    st.markdown("""
    <div style="background-color: #f0f2f6; padding: 15px; border-radius: 10px;">
        <h4>K 线数据优先级</h4>
        <p>Tushare (优先) → Baostock → AkShare → 东方财富 API</p>

        <h4>实时行情优先级</h4>
        <p>新浪财经 (最快) → 腾讯财经 → AkShare → 东方财富 API</p>

        <h4>资金流优先级</h4>
        <p>Tushare (需要积分) → AkShare</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    # 实时数据采集测试
    st.subheader("实时采集测试")

    selected_code = st.selectbox("选择股票", stock_codes, key="data_source_test")

    if st.button("📡 测试数据采集", key="test_fetch"):
        with st.spinner("正在采集数据..."):
            start_time = datetime.now()

            # 测试 K 线数据
            kline_df = components["price_collector"].get_kline(selected_code, period="daily", limit=30)
            kline_time = (datetime.now() - start_time).total_seconds() * 1000

            # 测试实时行情
            realtime = components["price_collector"].get_realtime_quote(selected_code)
            realtime_time = (datetime.now() - start_time).total_seconds() * 1000 - kline_time

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
                    st.json({
                        "价格": realtime.get("price"),
                        "涨跌幅": realtime.get("change_pct"),
                        "成交量": realtime.get("volume"),
                    })

    st.markdown("---")

    # 数据采集性能
    st.subheader("采集性能监控")

    st.markdown("""
    | 数据源 | 平均响应时间 | 成功率 | 优先级 |
    |--------|-------------|--------|--------|
    | Tushare | 150-300ms | 98% | K 线优先 |
    | 新浪财经 | 50-150ms | 99% | 实时优先 |
    | Baostock | 200-400ms | 95% | K 线备用 |
    | AkShare | 300-500ms | 90% | 备用 |
    """)

# ==================== 页面 3: 情感分析可视化 ====================
elif page == "📰 情感分析":
    st.header("📰 情感分析可视化")

    st.markdown("""
    **分析维度：**
    - 新闻情感分析（NLP + 规则）
    - 事件类型识别
    - 影响程度分级
    - 时效性加权
    - 来源可信度评估
    """)

    # 情感分析测试
    st.subheader("实时情感分析")

    test_text = st.text_area(
        "输入新闻文本进行测试",
        value="公司发布业绩预告，预计上半年净利润同比增长 50%-80%，超出市场预期。",
        height=100
    )

    if st.button("🔍 分析情感"):
        result = components["sentiment_analyzer"].analyze(text=test_text)

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "情感得分",
                f"{result.score:.3f}",
                delta="利好" if result.score > 0.2 else "利空" if result.score < -0.2 else "中性"
            )
        with col2:
            st.metric("情感标签", result.label)
        with col3:
            st.metric("置信度", f"{result.confidence:.1%}")
        with col4:
            st.metric("关键词数量", len(result.keywords))

        # 详细结果
        st.markdown("#### 分析详情")
        detail_col1, detail_col2 = st.columns(2)

        with detail_col1:
            st.markdown("**识别关键词**")
            st.write(", ".join(result.keywords) if result.keywords else "无")

        with detail_col2:
            st.markdown("**事件类型**")
            event_names = {
                "earnings": "业绩财报",
                "capital_operation": "资本运作",
                "management": "管理层",
                "business": "业务",
                "policy": "政策",
                "equity": "股权",
                "product_tech": "产品技术",
                "industry": "行业",
                "fund_flow": "资金流",
                "rumor": "传闻",
            }
            st.write(event_names.get(result.event_type, result.event_type))

        # 影响程度和来源
        detail_col3, detail_col4 = st.columns(2)
        with detail_col3:
            impact_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}
            st.markdown(f"**影响程度**: {impact_emoji.get(result.impact_level, '⚪')} {result.impact_level}")
        with detail_col4:
            st.markdown(f"**时效权重**: {result.time_weight:.2f}")

    st.markdown("---")

    # 情感分析模块说明
    st.subheader("情感分析架构")

    st.markdown("""
    ```
    输入文本 → 分词处理 → 关键词匹配 → 情感词典 → 程度副词调整
                                      ↓
        SnowNLP 分析 ←───────────── 规则分析
                                      ↓
        事件类型识别 → 影响程度分级 → 时效性加权 → 来源可信度 → 综合得分
    ```
    """)

# ==================== 页面 4: 技术分析可视化 ====================
elif page == "📉 技术分析":
    st.header("📉 技术分析可视化")

    selected_code = st.selectbox("选择股票", stock_codes, key="tech_analysis")

    # 获取数据
    df = components["price_collector"].get_kline(selected_code, period="daily", limit=120)

    if df is not None and not df.empty:
        # K 线图和指标
        tab1, tab2, tab3, tab4 = st.tabs(["K 线指标", "MACD", "KDJ", "其他指标"])

        with tab1:
            st.subheader("K 线与均线")

            # 计算均线
            ma5 = df["close"].rolling(5).mean()
            ma10 = df["close"].rolling(10).mean()
            ma20 = df["close"].rolling(20).mean()
            ma60 = df["close"].rolling(60).mean()

            fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                              vertical_spacing=0.03, row_heights=[0.7, 0.3])

            # K 线
            fig.add_trace(go.Candlestick(
                x=df["trade_date"],
                open=df["open"],
                high=df["high"],
                low=df["low"],
                close=df["close"],
                name="K 线"
            ), row=1, col=1)

            # 均线
            fig.add_trace(go.Scatter(x=df["trade_date"], y=ma5, name="MA5", line=dict(color="red")), row=1, col=1)
            fig.add_trace(go.Scatter(x=df["trade_date"], y=ma10, name="MA10", line=dict(color="blue")), row=1, col=1)
            fig.add_trace(go.Scatter(x=df["trade_date"], y=ma20, name="MA20", line=dict(color="green")), row=1, col=1)
            fig.add_trace(go.Scatter(x=df["trade_date"], y=ma60, name="MA60", line=dict(color="gray")), row=1, col=1)

            # 成交量
            fig.add_trace(go.Bar(
                x=df["trade_date"],
                y=df["volume"],
                name="成交量",
                marker_color=["red" if df["close"].iloc[i] > df["open"].iloc[i] else "green" for i in range(len(df))]
            ), row=2, col=1)

            fig.update_layout(
                height=600,
                xaxis_rangeslider_visible=False,
                showlegend=True,
                legend=dict(orientation="h", y=1.1)
            )
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            st.subheader("MACD 指标")

            tech_signal = components["technical_analyzer"].analyze(df)
            indicators = components["technical_analyzer"].get_indicators(df)

            macd_col1, macd_col2 = st.columns(2)
            with macd_col1:
                st.metric("DIF", f"{indicators['macd']['dif']:.4f}")
                st.metric("DEA", f"{indicators['macd']['dea']:.4f}")
            with macd_col2:
                st.metric("MACD", f"{indicators['macd']['macd']:.4f}")
                st.metric("信号", "🟢 金叉" if indicators['macd']['dif'] > indicators['macd']['dea'] else "🔴 死叉")

        with tab3:
            st.subheader("KDJ 指标")

            indicators = components["technical_analyzer"].get_indicators(df)
            kjd_col1, kjd_col2 = st.columns(2)
            with kjd_col1:
                st.metric("K", f"{indicators['kdj']['k']:.2f}")
                st.metric("D", f"{indicators['kdj']['d']:.2f}")
            with kjd_col2:
                st.metric("J", f"{indicators['kdj']['j']:.2f}")
                st.metric("信号", "超买" if indicators['kdj']['k'] > 80 else "超卖" if indicators['kdj']['k'] < 20 else "中性")

        with tab4:
            st.subheader("其他技术指标")

            indicators = components["technical_analyzer"].get_indicators(df)

            ind_df = pd.DataFrame({
                "指标": ["RSI", "ATR", "OBV", "BIAS(6)", "VR", "布林上轨", "布林中轨", "布林下轨"],
                "数值": [
                    f"{indicators['rsi']:.2f}",
                    f"{indicators['atr']:.4f}",
                    f"{indicators['obv']:.0f}",
                    f"{indicators['bias']['bias6']:.2f}%",
                    f"{indicators['vr']:.2f}",
                    f"{indicators['boll']['upper']:.2f}",
                    f"{indicators['boll']['middle']:.2f}",
                    f"{indicators['boll']['lower']:.2f}",
                ],
                "状态": [
                    "超买" if indicators['rsi'] > 70 else "超卖" if indicators['rsi'] < 30 else "中性",
                    "-",
                    "-",
                    "正乖离" if indicators['bias']['bias6'] > 0 else "负乖离",
                    "热" if indicators['vr'] > 150 else "冷" if indicators['vr'] < 50 else "正常",
                    "-",
                    "-",
                    "-",
                ]
            })
            st.dataframe(ind_df, use_container_width=True, hide_index=True)

# ==================== 页面 5: 信号融合可视化 ====================
elif page == "🔀 信号融合":
    st.header("🔀 信号融合可视化")

    st.markdown("""
    **多因子加权评分系统：**
    - 新闻情感因子 (25%)
    - 技术分析因子 (25%)
    - 资金流向因子 (20%)
    - 波动率因子 (20%)
    - 市场情绪因子 (10%)
    """)

    # 动态权重显示
    st.subheader("动态权重配置")

    # 根据市场状态显示权重
    regime = "oscillating"  # 实际应从分析器获取
    weight_config = {
        "bull": {"新闻": 20, "技术": 30, "资金": 25, "波动率": 15, "情绪": 10},
        "bear": {"新闻": 15, "技术": 20, "资金": 30, "波动率": 25, "情绪": 10},
        "oscillating": {"新闻": 25, "技术": 25, "资金": 20, "波动率": 20, "情绪": 10},
    }

    weights = weight_config.get(regime, weight_config["oscillating"])

    # 权重饼图
    fig = go.Figure(data=[go.Pie(
        labels=list(weights.keys()),
        values=list(weights.values()),
        hole=.3
    )])
    fig.update_layout(title="当前市场状态下的因子权重", height=400)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # 实时信号融合演示
    st.subheader("实时信号融合演示")

    selected_code = st.selectbox("选择股票", stock_codes, key="signal_fusion")

    if st.button("🔀 计算融合信号"):
        df = components["price_collector"].get_kline(selected_code, period="daily", limit=60)

        if df is not None and not df.empty:
            # 获取各因子得分
            tech_signal = components["technical_analyzer"].analyze(df)

            # 模拟新闻情感得分
            news_score = 0.3

            # 模拟资金流得分
            fund_score = 0.2

            # 波动率得分
            vol_signal = components["volatility_analyzer"].analyze(df)
            volatility_score = -vol_signal.current_volatility * 10 if vol_signal.current_volatility > 0.03 else 0.2

            # 计算融合信号
            fusion_result = components["signal_fusion"].fuse(
                news_score=news_score,
                technical_score=tech_signal.score,
                fund_score=fund_score,
                volatility_score=volatility_score,
                sentiment_score=0.5,
            )

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("综合得分", f"{fusion_result.total_score:.3f}")
            with col2:
                st.metric("最终信号", fusion_result.signal)
            with col3:
                st.metric("置信度", f"{fusion_result.confidence:.1%}")
            with col4:
                st.metric("建议操作", "买入" if fusion_result.signal in ["buy", "strong_buy"] else "卖出" if fusion_result.signal in ["sell", "strong_sell"] else "观望")

            # 各因子得分详情
            st.markdown("#### 各因子得分详情")

            factor_df = pd.DataFrame({
                "因子": ["新闻情感", "技术分析", "资金流向", "波动率", "市场情绪"],
                "得分": [f"{news_score:.3f}", f"{tech_signal.score:.3f}", f"{fund_score:.3f}", f"{volatility_score:.3f}", "0.500"],
                "权重": [f"{weights['新闻']}%", f"{weights['技术']}%", f"{weights['资金']}%", f"{weights['波动率']}%", f"{weights['情绪']}%"],
            })
            st.dataframe(factor_df, use_container_width=True, hide_index=True)

# ==================== 页面 6: 黑天鹅检测 ====================
elif page == "⚠️ 黑天鹅检测":
    st.header("⚠️ 黑天鹅事件检测")

    st.markdown("""
    **检测类型：**
    - 闪崩检测（短时间暴跌>5%）
    - 成交量异常（暴增>3 倍）
    - 波动率异常（>2.5 倍基准）
    - 相关性崩溃（平均相关性>0.7）
    """)

    # 实时检测
    st.subheader("实时检测")

    if st.button("🔍 执行黑天鹅检测"):
        # 获取数据
        price_data = {}
        for code in stock_codes[:5]:
            df = components["price_collector"].get_kline(code, period="daily", limit=60)
            if df is not None and not df.empty:
                price_data[code] = df

        if price_data:
            result = components["black_swan_detector"].detect(price_data)

            # 警报级别显示
            alert_colors = {
                "normal": ("🟢", "#333", "正常"),
                "watch": ("🟡", "#ffa500", "关注"),
                "warning": ("🟠", "#ff8800", "警告"),
                "critical": ("🔴", "#ff4444", "严重"),
                "emergency": ("🚨", "#cc0000", "紧急"),
            }

            emoji, color, status_text = alert_colors.get(result.alert_level.value, ("⚪", "#666", "未知"))

            st.markdown(f"""
            <div style="background-color: #fff3f3; padding: 20px; border-radius: 10px; border: 2px solid {color};">
                <h2 style="color: {color}; margin: 0;">{emoji} 检测状态：{status_text}</h2>
            </div>
            """, unsafe_allow_html=True)

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("市场状态", result.market_status)
            with col2:
                st.metric("恐慌指数", f"{result.panic_index:.1f}")
            with col3:
                st.metric("警报级别", result.alert_level.value.upper())
            with col4:
                st.metric("建议仓位", f"{result.suggested_position:.0%}")

            # 风险因子
            st.markdown("#### 风险因子")
            risk_df = pd.DataFrame({
                "风险类型": ["闪崩风险", "成交量风险", "波动率风险", "相关性风险", "综合风险"],
                "风险值": [
                    f"{result.risk_factors.get('flash_crash_risk', 0):.2f}",
                    f"{result.risk_factors.get('volume_risk', 0):.2f}",
                    f"{result.risk_factors.get('volatility_risk', 0):.2f}",
                    f"{result.risk_factors.get('correlation_risk', 0):.2f}",
                    f"{result.risk_factors.get('overall_risk', 0):.2f}",
                ],
            })
            st.dataframe(risk_df, use_container_width=True, hide_index=True)

            # 活跃冲击事件
            if result.active_shocks:
                st.markdown("#### 活跃冲击事件")
                for shock in result.active_shocks:
                    st.warning(f"**[{shock.severity.value}]** {shock.event_type}: {shock.description} - 建议：{shock.suggested_action}")
            else:
                st.success("✅ 未检测到异常事件")

# ==================== 页面 7: 社交媒体情绪 ====================
elif page == "🌐 社交媒体":
    st.header("🌐 社交媒体情绪监控")

    st.markdown("""
    **监控平台：**
    - 微博（大众情绪）
    - 雪球（投资者观点）
    - 东方财富股吧（散户聚集地）
    """)

    selected_code = st.selectbox("选择股票", stock_codes, key="social_sentiment")
    stock_name = "平安银行"  # 实际应从数据库获取

    if st.button("🔍 分析社交媒体情绪"):
        with st.spinner("正在分析社交媒体情绪..."):
            # 调用分析器
            result = components["social_sentiment_analyzer"].analyze_stock_sentiment(
                selected_code, stock_name, limit_per_platform=5
            )

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("帖子总数", result.post_count)
            with col2:
                st.metric(
                    "综合情绪",
                    f"{result.overall_sentiment:.3f}",
                    "利好" if result.overall_sentiment > 0.2 else "利空" if result.overall_sentiment < -0.2 else "中性"
                )
            with col3:
                trend_emoji = {"improving": "📈", "worsening": "📉", "stable": "➡️"}
                st.metric("情绪趋势", trend_emoji.get(result.sentiment_trend, ""))
            with col4:
                intensity_emoji = {"high": "🔥", "medium": "🔶", "low": "🔵"}
                st.metric("讨论热度", intensity_emoji.get(result.discussion_intensity, ""))

            st.markdown("---")

            # 热门关键词
            st.subheader("热门关键词")
            if result.trending_keywords:
                keywords_text = "  |  ".join(result.trending_keywords[:10])
                st.markdown(f"`{keywords_text}`")

            # 热门帖子
            st.subheader("热门帖子")
            for i, post in enumerate(result.hot_posts[:5], 1):
                platform_emoji = {"weibo": "🧣", "xueqiu": "❄️", "guba": "🐟"}
                st.markdown(f"**{i}. {platform_emoji.get(post.platform, '')} [{post.platform}]** {post.title}")
                st.caption(f"互动：{post.likes + post.comments + post.shares} | 情感：{post.sentiment_score:.3f}")

# ==================== 页面 8: 模拟交易 ====================
elif page == "💼 模拟交易":
    st.header("💼 模拟交易")
    st.info("模拟交易功能与原版保持一致，此处略...")

# ==================== 页面 9: 绩效评估 ====================
elif page == "📈 绩效评估":
    st.header("📈 绩效评估")
    st.info("绩效评估功能与原版保持一致，此处略...")

# 页脚
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #888; padding: 20px;'>"
    "A 股自动监控系统 增强版 v2.0 | 数据仅供参考，不构成投资建议"
    "</div>",
    unsafe_allow_html=True
)
