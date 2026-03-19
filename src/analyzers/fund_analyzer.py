"""
资金分析模块 - 分析资金流向数据
"""
from typing import Dict, List, Optional
from dataclasses import dataclass
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class FundSignal:
    """资金信号"""
    northbound_signal: str  # 北向资金信号
    main_force_signal: str  # 主力资金信号
    overall_signal: str  # 综合信号
    score: float  # 综合得分 [-1, 1]
    details: Dict  # 详细信息


class FundAnalyzer:
    """
    资金流向分析器

    分析维度：
    - 北向资金流向
    - 主力资金净流入
    - 大单/中单/小单分析
    """

    def __init__(
        self,
        northbound_threshold: float = 10000000,  # 北向资金阈值（1000 万）
        main_force_threshold: float = 5000000,    # 主力资金阈值（500 万）
    ):
        """
        初始化资金分析器

        Args:
            northbound_threshold: 北向资金显著流入阈值（元）
            main_force_threshold: 主力资金显著流入阈值（元）
        """
        self.northbound_threshold = northbound_threshold
        self.main_force_threshold = main_force_threshold

    def analyze(
        self,
        stock_fund_flow: Optional[Dict] = None,
        northbound_flow: Optional[Dict] = None,
        market_fund_flow: Optional[Dict] = None,
    ) -> FundSignal:
        """
        综合分析资金流向

        Args:
            stock_fund_flow: 个股资金流向数据
            northbound_flow: 北向资金数据
            market_fund_flow: 大盘资金流向数据

        Returns:
            资金信号
        """
        details = {
            "stock_fund_flow": stock_fund_flow,
            "northbound_flow": northbound_flow,
            "market_fund_flow": market_fund_flow,
        }

        # 分析北向资金
        northbound_signal = self._analyze_northbound(northbound_flow)

        # 分析主力资金
        main_force_signal = self._analyze_main_force(stock_fund_flow)

        # 分析市场整体
        market_signal = self._analyze_market(market_fund_flow)

        # 计算综合得分
        score = self._calculate_score(
            northbound_signal,
            main_force_signal,
            market_signal,
            stock_fund_flow,
        )

        # 确定综合信号
        overall_signal = self._get_overall_signal(score)

        return FundSignal(
            northbound_signal=northbound_signal,
            main_force_signal=main_force_signal,
            overall_signal=overall_signal,
            score=score,
            details=details,
        )

    def _analyze_northbound(self, flow_data: Optional[Dict]) -> str:
        """
        分析北向资金

        Args:
            flow_data: 北向资金数据

        Returns:
            信号 (buy/sell/hold)
        """
        if not flow_data:
            return "hold"

        net_in = flow_data.get("net_in", 0)

        if net_in >= self.northbound_threshold * 5:
            return "strong_buy"  # 大幅净流入
        elif net_in >= self.northbound_threshold:
            return "buy"  # 净流入
        elif net_in <= -self.northbound_threshold * 5:
            return "strong_sell"  # 大幅净流出
        elif net_in <= -self.northbound_threshold:
            return "sell"  # 净流出

        return "hold"

    def _analyze_main_force(self, flow_data: Optional[Dict]) -> str:
        """
        分析主力资金

        Args:
            flow_data: 个股资金流向数据

        Returns:
            信号
        """
        if not flow_data:
            return "hold"

        main_net_in = flow_data.get("main_net_in", 0)
        large_order_net_in = flow_data.get("large_order_net_in", 0)

        # 计算主力流入强度
        if main_net_in >= self.main_force_threshold * 3:
            return "strong_buy"
        elif main_net_in >= self.main_force_threshold:
            return "buy"
        elif main_net_in <= -self.main_force_threshold * 3:
            return "strong_sell"
        elif main_net_in <= -self.main_force_threshold:
            return "sell"

        # 超大单分析
        if large_order_net_in >= self.main_force_threshold:
            return "buy"
        elif large_order_net_in <= -self.main_force_threshold:
            return "sell"

        return "hold"

    def _analyze_market(self, flow_data: Optional[Dict]) -> str:
        """
        分析市场整体资金流向

        Args:
            flow_data: 市场资金流向数据

        Returns:
            信号
        """
        if not flow_data:
            return "hold"

        main_net_in = flow_data.get("main_net_in", 0)

        # 市场整体资金流向作为参考
        if main_net_in >= self.main_force_threshold * 10:
            return "buy"  # 市场整体大幅流入
        elif main_net_in <= -self.main_force_threshold * 10:
            return "sell"  # 市场整体大幅流出

        return "hold"

    def _calculate_score(
        self,
        northbound_signal: str,
        main_force_signal: str,
        market_signal: str,
        stock_fund_flow: Optional[Dict],
    ) -> float:
        """
        计算综合得分

        权重：
        - 北向资金：30%
        - 主力资金：50%
        - 市场资金：20%
        """
        signal_score = {
            "strong_buy": 1.0,
            "buy": 0.7,
            "hold": 0.0,
            "sell": -0.7,
            "strong_sell": -1.0,
        }

        # 北向资金得分
        nb_score = signal_score.get(northbound_signal, 0)

        # 主力资金得分（权重最高）
        mf_score = signal_score.get(main_force_signal, 0)

        # 市场资金得分
        mkt_score = signal_score.get(market_signal, 0)

        # 加权计算
        score = nb_score * 0.30 + mf_score * 0.50 + mkt_score * 0.20

        # 根据实际流入金额微调
        if stock_fund_flow:
            main_net_in = stock_fund_flow.get("main_net_in", 0)
            # 流入金额特别大时加分
            if main_net_in >= self.main_force_threshold * 10:
                score = min(1.0, score + 0.1)
            elif main_net_in <= -self.main_force_threshold * 10:
                score = max(-1.0, score - 0.1)

        return max(-1.0, min(1.0, score))

    def _get_overall_signal(self, score: float) -> str:
        """根据得分确定综合信号"""
        if score >= 0.7:
            return "strong_buy"
        elif score >= 0.4:
            return "buy"
        elif score >= -0.2:
            return "hold"
        elif score >= -0.5:
            return "sell"
        else:
            return "strong_sell"

    def analyze_industry_flow(
        self,
        industry_flows: List[Dict],
    ) -> List[Dict]:
        """
        分析行业资金流向

        Args:
            industry_flows: 行业资金流向列表

        Returns:
            排序后的行业流向（按净流入）
        """
        if not industry_flows:
            return []

        # 按净流入排序
        sorted_industries = sorted(
            industry_flows,
            key=lambda x: x.get("net_in", 0),
            reverse=True
        )

        # 添加信号标记
        for industry in sorted_industries:
            net_in = industry.get("net_in", 0)
            if net_in >= self.main_force_threshold * 5:
                industry["signal"] = "strong_buy"
            elif net_in >= self.main_force_threshold:
                industry["signal"] = "buy"
            elif net_in <= -self.main_force_threshold * 5:
                industry["signal"] = "strong_sell"
            elif net_in <= -self.main_force_threshold:
                industry["signal"] = "sell"
            else:
                industry["signal"] = "hold"

        return sorted_industries

    def get_fund_flow_summary(
        self,
        stock_code: str,
        flow_data: Dict,
    ) -> str:
        """
        生成资金流向摘要

        Args:
            stock_code: 股票代码
            flow_data: 资金流向数据

        Returns:
            摘要文本
        """
        if not flow_data:
            return "无资金流向数据"

        main_net_in = flow_data.get("main_net_in", 0)
        large_order = flow_data.get("large_order_net_in", 0)
        medium_order = flow_data.get("medium_order_net_in", 0)
        small_order = flow_data.get("small_order_net_in", 0)
        retail = flow_data.get("retail_net_in", 0)

        # 判断主力态度
        if main_net_in > 0:
            main_attitude = "主力净流入"
        else:
            main_attitude = "主力净流出"

        # 判断散户态度
        if retail > 0:
            retail_attitude = "散户净流入"
        else:
            retail_attitude = "散户净流出"

        summary = (
            f"{stock_code} 资金流向：{main_attitude} {main_net_in/10000:.1f}万，"
            f"超大单 {large_order/10000:.1f}万，大单 {medium_order/10000:.1f}万，"
            f"中单 {small_order/10000:.1f}万，小单 {retail/10000:.1f}万"
        )

        return summary


__all__ = ["FundAnalyzer", "FundSignal"]
