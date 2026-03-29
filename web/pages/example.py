"""
示例页面 - 展示如何使用 Web 组件

这个文件展示了如何从新的组件化 Web 结构中构建页面
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st

# 导入组件
from web.services.data_service import get_data_service
from web.components.charts import render_price_chart, render_technical_indicators, render_fund_flow_chart
from web.components.tables import render_positions, render_trades


def render_monitor_page():
    """监控面板页面示例"""
    st.title("股票实时监控")

    # 获取数据服务
    ds = get_data_service()

    # 股票池配置
    stock_codes = ['000948', '601360', '300459', '002714', '600036']
    stock_names = {
        '000948': '南天信息',
        '601360': '三六零',
        '300459': '汤姆猫',
        '002714': '牧原股份',
        '600036': '招商银行'
    }

    # 批量获取行情
    quotes = ds.get_stock_batch_quotes(stock_codes)

    # 显示股票列表
    cols = st.columns(len(stock_codes))

    for i, (code, quote) in enumerate(zip(stock_codes, quotes)):
        with cols[i]:
            price = quote.get('price', 0) if quote else 0
            change = quote.get('change_pct', 0) if quote else 0

            # 涨跌幅颜色
            color = 'red' if change > 0 else 'green' if change < 0 else 'gray'

            st.metric(
                stock_names.get(code, code),
                f"{price:.2f}",
                f"{change:+.2f}%"
            )

    # 获取并显示信号
    signals = ds.get_signals(stock_codes)

    if signals:
        st.subheader("交易信号")

        for signal in signals:
            code = signal.get('stock_code', '')
            action = signal.get('action', '')
            price = signal.get('price', 0)
            score = signal.get('score', 0)

            action_text = "买入" if action == 'buy' else "卖出"
            emoji = "📈" if action == 'buy' else "📉"

            st.write(f"{emoji} **{stock_names.get(code, code)}**: {action_text} @ {price:.2f} (评分: {score:.2f})")

    # 获取持仓
    positions = ds.get_simulated_positions()

    if positions:
        st.subheader("当前持仓")
        render_positions(positions)

    # 获取交易记录
    trades = ds.get_simulated_trades(limit=20)

    if trades:
        st.subheader("最近交易")
        render_trades(trades)


def render_analysis_page(stock_code: str = '300459'):
    """分析页面示例"""
    st.title(f"股票分析 - {stock_code}")

    ds = get_data_service()

    # 获取价格数据
    df = ds.get_stock_price(stock_code, days=60)

    if df is not None and len(df) >= 2:
        # 渲染价格图表
        fig = render_price_chart(df, stock_code)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("数据不足")

    # 获取技术指标
    indicators = ds.get_technical_indicators(stock_code)

    if indicators:
        st.subheader("技术指标")
        render_technical_indicators(indicators)

    # 获取资金流向
    fund_flow = ds.get_fund_flow(stock_code)

    if fund_flow:
        st.subheader("资金流向")
        fig = render_fund_flow_chart(fund_flow)
        if fig:
            st.plotly_chart(fig, use_container_width=True)

    # 获取新闻
    news = ds.get_news(stock_code, limit=5)

    if news:
        st.subheader("最新新闻")
        for item in news:
            st.write(f"**{item.get('title', '无标题')}**")
            st.caption(f"{item.get('source', '')} - {item.get('publish_time', '')}")


# 可以在 web_dashboard_unified.py 中导入并使用这些函数
# from web.pages.example import render_monitor_page, render_analysis_page