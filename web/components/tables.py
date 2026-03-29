"""
表格组件 - Streamlit 表格渲染
"""
import sys
from pathlib import Path
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
from datetime import datetime


def render_stock_table(stocks: List[Dict], columns: List[str] = None) -> None:
    """
    渲染股票列表表格

    参数:
        stocks: 股票数据列表
        columns: 要显示的列
    """
    if not stocks:
        st.info("暂无数据")
        return

    # 默认列
    if columns is None:
        columns = ['code', 'name', 'price', 'change_pct', 'volume', 'amount']

    # 转换为 DataFrame
    df = pd.DataFrame(stocks)

    # 处理涨跌幅颜色
    def color_change(val):
        if 'change_pct' in str(val):
            try:
                pct = float(str(val).replace('%', ''))
                if pct > 0:
                    return 'color: red'
                elif pct < 0:
                    return 'color: green'
            except:
                pass
        return ''

    # 渲染表格
    st.dataframe(
        df[columns] if all(c in df.columns for c in columns) else df,
        use_container_width=True,
        hide_index=True
    )


def render_signal_history(signals: List[Dict], limit: int = 50) -> None:
    """
    渲染信号历史表格

    参数:
        signals: 信号列表
        limit: 显示数量
    """
    if not signals:
        st.info("暂无信号历史")
        return

    # 格式化数据
    formatted = []
    for signal in signals[:limit]:
        stock_code = signal.get('stock_code', '')
        action = signal.get('action', '')
        price = signal.get('price', 0)
        score = signal.get('score', 0)
        reason = signal.get('reason', '')
        created_at = signal.get('created_at', '')

        # 格式化时间
        if created_at:
            try:
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                created_at = dt.strftime('%Y-%m-%d %H:%M')
            except:
                pass

        formatted.append({
            '时间': created_at,
            '代码': stock_code,
            '操作': '买入' if action == 'buy' else '卖出' if action == 'sell' else action,
            '价格': f'{price:.2f}' if price else '-',
            '评分': f'{score:.2f}' if score else '-',
            '原因': reason[:30] + '...' if len(reason) > 30 else reason
        })

    df = pd.DataFrame(formatted)

    # 渲染表格
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=400
    )


def render_positions(positions: List[Dict]) -> None:
    """
    渲染持仓表格

    参数:
        positions: 持仓列表
    """
    if not positions:
        st.info("当前无持仓")
        return

    # 格式化数据
    formatted = []
    for pos in positions:
        stock_code = pos.get('stock_code', '')
        quantity = pos.get('quantity', 0)
        avg_cost = pos.get('avg_cost', 0)
        current_price = pos.get('current_price', 0)

        # 计算盈亏
        if current_price and avg_cost:
            profit = (current_price - avg_cost) * quantity
            profit_pct = (current_price - avg_cost) / avg_cost * 100
        else:
            profit = 0
            profit_pct = 0

        formatted.append({
            '代码': stock_code,
            '数量': quantity,
            '成本价': f'{avg_cost:.2f}',
            '现价': f'{current_price:.2f}' if current_price else '-',
            '盈亏': f'{profit:.2f}',
            '盈亏%': f'{profit_pct:.2f}%'
        })

    df = pd.DataFrame(formatted)

    # 渲染表格
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )


def render_trades(trades: List[Dict], limit: int = 30) -> None:
    """
    渲染交易记录表格

    参数:
        trades: 交易记录列表
        limit: 显示数量
    """
    if not trades:
        st.info("暂无交易记录")
        return

    # 格式化数据
    formatted = []
    for trade in trades[:limit]:
        stock_code = trade.get('stock_code', '')
        action = trade.get('action', '')
        price = trade.get('price', 0)
        quantity = trade.get('quantity', 0)
        amount = price * quantity if price and quantity else 0
        profit = trade.get('profit', 0)
        trade_time = trade.get('trade_time', '')

        # 格式化时间
        if trade_time:
            try:
                dt = datetime.fromisoformat(trade_time.replace('Z', '+00:00'))
                trade_time = dt.strftime('%Y-%m-%d %H:%M')
            except:
                pass

        formatted.append({
            '时间': trade_time,
            '代码': stock_code,
            '操作': '买入' if action == 'buy' else '卖出',
            '价格': f'{price:.2f}' if price else '-',
            '数量': quantity,
            '金额': f'{amount:.2f}' if amount else '-',
            '盈亏': f'{profit:.2f}' if profit else '-'
        })

    df = pd.DataFrame(formatted)

    # 渲染表格
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=400
    )


def render_black_swan_status(status: Dict) -> None:
    """
    渲染黑天鹅状态卡片

    参数:
        status: 黑天鹅检测状态
    """
    if not status:
        st.info("暂无黑天鹅检测数据")
        return

    level = status.get('level', 'unknown')
    panic_index = status.get('panic_index', 0)

    # 颜色映射
    color_map = {
        'normal': 'green',
        'watch': 'blue',
        'warning': 'yellow',
        'critical': 'orange',
        'emergency': 'red'
    }

    color = color_map.get(level, 'gray')

    # 渲染状态
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "警报级别",
            level.upper(),
            delta_color=color
        )

    with col2:
        st.metric(
            "恐慌指数",
            f"{panic_index:.1f}",
            delta=f"{panic_index:.1f}/100"
        )

    with col3:
        # 建议仓位
        recommendation = status.get('recommendation', {})
        position = recommendation.get('suggested_position', 0)
        st.metric(
            "建议仓位",
            f"{position*100:.0f}%"
        )

    # 显示检测项
    if 'detections' in status:
        st.subheader("检测详情")

        for detection in status['detections']:
            name = detection.get('name', '')
            status_detect = detection.get('status', 'normal')
            message = detection.get('message', '')

            status_icon = '✅' if status_detect == 'normal' else '⚠️'

            st.write(f"{status_icon} **{name}**: {message}")


def render_news_list(news: List[Dict], limit: int = 10) -> None:
    """
    渲染新闻列表

    参数:
        news: 新闻列表
        limit: 显示数量
    """
    if not news:
        st.info("暂无新闻")
        return

    for i, item in enumerate(news[:limit]):
        title = item.get('title', '无标题')
        source = item.get('source', '')
        publish_time = item.get('publish_time', '')
        sentiment = item.get('sentiment', 0)

        # 情感颜色
        sentiment_color = 'green' if sentiment > 0.3 else 'red' if sentiment < -0.3 else 'gray'

        with st.expander(f"{title}"):
            st.write(f"**来源**: {source} | **时间**: {publish_time}")
            st.write(f"**情感**: ", unsafe_allow_html=True)
            st.markdown(f":{sentiment_color}[{sentiment:.2f}]")

            content = item.get('content', '')
            if content:
                st.write(content[:500] + '...' if len(content) > 500 else content)