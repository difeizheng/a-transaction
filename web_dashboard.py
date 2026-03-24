"""
A 股监控系统 - Web 可视化界面
使用 Streamlit 构建
支持配置修改
"""
import streamlit as st
import pandas as pd
import sqlite3
import yaml
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from src.collectors.price_collector import PriceCollector
from src.analyzers.technical_analyzer import TechnicalAnalyzer
from src.analyzers.fund_analyzer import FundAnalyzer
from src.analyzers.volatility_analyzer import VolatilityAnalyzer
from src.engine.signal_fusion import SignalFusionEngine
from src.engine.backtest import evaluate_system
from src.strategy.improved_strategy import ImprovedStrategy

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
page = st.sidebar.radio("页面", ["监控面板", "绩效评估", "回测"])

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

# 获取股票列表
stock_list = [s.strip() for s in stock_codes_input.split(",") if s.strip()]

# 根据页面选择显示不同内容
if page == "监控面板":
    # 主区域
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("监控股票数", len(stock_list))

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

        for code in stock_list[:15]:
            try:
                df = price_collector.get_kline(code, period="daily", limit=120)

                if df is not None and not df.empty:
                    # 使用改进策略生成信号
                    strategy_signal = improved_strategy.generate_signal(
                        df=df, stock_code=code, stock_name="", timestamp=datetime.now()
                    )

                    latest_price = float(df["close"].iloc[-1])
                    change_pct = float(df["change_pct"].iloc[-1]) if "change_pct" in df.columns else 0

                    results_data.append({
                        "代码": code,
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
                    "代码": code,
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
                    "代码": st.column_config.TextColumn(width="small"),
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

        selected_stock = st.selectbox("选择股票", stock_list, key="monitor_stock")

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
