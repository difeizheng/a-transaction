"""
图表组件 - Plotly 可视化
"""
import sys
from pathlib import Path
from typing import Optional, List, Dict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


def render_price_chart(
    df: pd.DataFrame,
    stock_code: str = '',
    stock_name: str = '',
    show_ma: bool = True,
    show_volume: bool = True
) -> go.Figure:
    """
    渲染股票价格图表（K 线 + 成交量）

    参数:
        df: 包含 OHLCV 数据的 DataFrame
        stock_code: 股票代码
        stock_name: 股票名称
        show_ma: 是否显示均线
        show_volume: 是否显示成交量

    返回:
        Plotly 图表对象
    """
    if df is None or len(df) < 2:
        st.warning("数据不足")
        return None

    # 创建子图
    fig = make_subplots(
        rows=2 if show_volume else 1,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.7, 0.3] if show_volume else [1.0]
    )

    # K 线图
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='K线'
        ),
        row=1, col=1
    )

    # 均线
    if show_ma:
        for period, color in [(5, 'blue'), (10, 'orange'), (20, 'purple'), (60, 'brown')]:
            ma = df['close'].rolling(period).mean()
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=ma,
                    mode='lines',
                    name=f'MA{period}',
                    line=dict(color=color, width=1)
                ),
                row=1, col=1
            )

    # 成交量
    if show_volume:
        colors = ['red' if df['close'].iloc[i] >= df['open'].iloc[i] else 'green'
                  for i in range(len(df))]

        fig.add_trace(
            go.Bar(
                x=df.index,
                y=df['volume'],
                name='成交量',
                marker_color=colors,
                opacity=0.5
            ),
            row=2, col=1
        )

    # 布局设置
    title = f"{stock_name} ({stock_code})" if stock_name else stock_code

    fig.update_layout(
        title=title,
        xaxis_rangeslider_visible=False,
        height=500,
        showlegend=True,
        template='plotly_white',
        margin=dict(l=50, r=50, t=50, b=50)
    )

    return fig


def render_technical_indicators(indicators: Dict) -> None:
    """
    渲染技术指标卡片

    参数:
        indicators: 技术指标字典
    """
    if not indicators:
        st.warning("暂无技术指标数据")
        return

    # 创建指标列
    cols = st.columns(6)

    # MA 指标
    with cols[0]:
        st.metric(
            "MA5",
            f"{indicators.get('ma5', 0):.2f}" if indicators.get('ma5') else "N/A"
        )

    with cols[1]:
        st.metric(
            "MA20",
            f"{indicators.get('ma20', 0):.2f}" if indicators.get('ma20') else "N/A"
        )

    # MACD 指标
    macd_dif = indicators.get('macd_dif', 0)
    macd_dea = indicators.get('macd_dea', 0)
    macd_color = "normal" if macd_dif > macd_dea else "inverse"

    with cols[2]:
        st.metric(
            "MACD",
            f"{macd_dif:.3f}",
            delta=f"{(macd_dif - macd_dea):.3f}",
            delta_color=macd_color
        )

    # RSI 指标
    rsi = indicators.get('rsi', 50)
    rsi_color = "normal" if rsi < 30 or rsi > 70 else "off"

    with cols[3]:
        st.metric(
            "RSI(14)",
            f"{rsi:.1f}",
            delta="超买" if rsi > 70 else "超卖" if rsi < 30 else None,
            delta_color="inverse" if rsi > 70 or rsi < 30 else "normal"
        )

    # KDJ 指标
    kdj_k = indicators.get('kdj_k', 50)
    with cols[4]:
        st.metric(
            "KDJ.K",
            f"{kdj_k:.1f}"
        )

    # ATR 指标
    atr = indicators.get('atr', 0)
    with cols[5]:
        st.metric(
            "ATR",
            f"{atr:.2f}"
        )


def render_fund_flow_chart(fund_flow: Dict) -> go.Figure:
    """
    渲染资金流向图表

    参数:
        fund_flow: 资金流向数据
    """
    if not fund_flow:
        return None

    categories = ['超大单', '大单', '中单', '小单']
    net_amounts = [
        fund_flow.get('super_net', 0),
        fund_flow.get('large_net', 0),
        fund_flow.get('medium_net', 0),
        fund_flow.get('small_net', 0)
    ]

    colors = ['green' if x > 0 else 'red' for x in net_amounts]

    fig = go.Figure(data=[
        go.Bar(
            x=categories,
            y=net_amounts,
            marker_color=colors,
            text=[f'{x/10000:.1f}万' for x in net_amounts],
            textposition='auto'
        )
    ])

    fig.update_layout(
        title="资金流向（净额）",
        height=300,
        template='plotly_white',
        yaxis_title="金额（元）"
    )

    return fig


def render_equity_curve(trades: List[Dict]) -> go.Figure:
    """
    渲染资金曲线

    参数:
        trades: 交易记录列表
    """
    if not trades:
        return None

    # 按时间排序
    trades = sorted(trades, key=lambda x: x.get('trade_time', ''))

    # 计算累计收益
    equity = [10000]  # 初始资金
    for trade in trades:
        if trade.get('action') == 'buy':
            equity.append(equity[-1])
        else:  # sell
            profit = trade.get('profit', 0)
            equity.append(equity[-1] + profit)

    fig = go.Figure(data=[
        go.Scatter(
            y=equity,
            mode='lines',
            name='资金曲线',
            line=dict(color='blue', width=2),
            fill='tozeroy',
            fillcolor='rgba(0, 0, 255, 0.1)'
        )
    ])

    fig.update_layout(
        title="资金曲线",
        height=300,
        template='plotly_white',
        yaxis_title="资金（元）",
        xaxis_title="交易次数"
    )

    return fig


def render_sector_heat(sector_data: List[Dict]) -> go.Figure:
    """
    渲染板块热力图

    参数:
        sector_data: 板块资金数据
    """
    if not sector_data:
        return None

    # 取前 10 个板块
    top_sectors = sector_data[:10]

    sectors = [s.get('name', '') for s in top_sectors]
    flows = [s.get('net_amount', 0) / 10000 for s in top_sectors]  # 转换为万元

    colors = ['green' if x > 0 else 'red' for x in flows]

    fig = go.Figure(data=[
        go.Bar(
            x=flows,
            y=sectors,
            orientation='h',
            marker_color=colors,
            text=[f'{x:.1f}万' for x in flows],
            textposition='auto'
        )
    ])

    fig.update_layout(
        title="板块资金流向（万元）",
        height=400,
        template='plotly_white',
        xaxis_title="净流入（万元）",
        yaxis=dict(autorange='reversed')
    )

    return fig