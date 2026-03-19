"""
资金流向采集器 - 获取北向资金、主力资金等数据
"""
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger(__name__)


class FundCollector:
    """
    资金流向采集器

    支持：
    - 北向资金流向
    - 主力资金净流入
    - 龙虎榜数据
    - 个股资金流向
    """

    def __init__(self):
        self._akshare = None
        self._init_akshare()

    def _init_akshare(self):
        """初始化 AkShare"""
        try:
            import akshare as ak
            self._akshare = ak
            logger.info("AkShare 初始化成功")
        except ImportError:
            logger.error("AkShare 未安装，请运行：pip install akshare")
        except Exception as e:
            logger.error(f"AkShare 初始化失败：{e}")

    def get_northbound_flow(self) -> Optional[Dict]:
        """
        获取北向资金流向

        Returns:
            北向资金数据
        """
        if self._akshare is None:
            return None

        try:
            # 北向资金实时数据
            df = self._akshare.stock_hsgt_north_net_flow_in_em(symbol="北向资金")

            if df is not None and not df.empty:
                latest = df.iloc[0] if len(df) > 0 else None
                if latest is not None:
                    return {
                        "net_in": float(latest.get("当日净流入额", 0)),
                        "buy_amount": float(latest.get("当日买入额", 0)),
                        "sell_amount": float(latest.get("当日卖出额", 0)),
                        "balance": float(latest.get("余额", 0)),
                        "timestamp": datetime.now(),
                    }

            return None

        except Exception as e:
            logger.error(f"获取北向资金流向失败：{e}")
            return None

    def get_northbound_hist(self, days: int = 30) -> pd.DataFrame:
        """
        获取北向资金历史流向

        Args:
            days: 天数

        Returns:
            历史数据 DataFrame
        """
        if self._akshare is None:
            return pd.DataFrame()

        try:
            df = self._akshare.stock_hsgt_north_net_flow_in_em(symbol="北向资金")

            if df is not None and not df.empty:
                return df.head(days)

            return pd.DataFrame()

        except Exception as e:
            logger.error(f"获取北向资金历史数据失败：{e}")
            return pd.DataFrame()

    def get_stock_fund_flow(self, stock_code: str) -> Optional[Dict]:
        """
        获取个股资金流向

        Args:
            stock_code: 股票代码

        Returns:
            资金流向数据
        """
        if self._akshare is None:
            return None

        try:
            code = stock_code.strip().zfill(6)

            # 获取个股资金流向
            df = self._akshare.stock_individual_fund_flow(stock=code)

            if df is not None and not df.empty:
                latest = df.iloc[0] if len(df) > 0 else None
                if latest is not None:
                    return {
                        "code": code,
                        "main_net_in": float(latest.get("主力净流入", 0)) if "主力净流入" in latest else 0,
                        "large_order_net_in": float(latest.get("超大单净流入", 0)) if "超大单净流入" in latest else 0,
                        "medium_order_net_in": float(latest.get("大单净流入", 0)) if "大单净流入" in latest else 0,
                        "small_order_net_in": float(latest.get("中单净流入", 0)) if "中单净流入" in latest else 0,
                        "retail_net_in": float(latest.get("小单净流入", 0)) if "小单净流入" in latest else 0,
                        "timestamp": datetime.now(),
                    }

            return None

        except Exception as e:
            logger.error(f"获取个股资金流向失败：{e}")
            return None

    def get_stock_fund_flow_rank(self, market: str = "sh") -> List[Dict]:
        """
        获取资金流向排行榜

        Args:
            market: 市场 (sh/sz)

        Returns:
            资金流向排行榜
        """
        if self._akshare is None:
            return []

        try:
            df = self._akshare.stock_individual_fund_flow_rank(indicator="今日")

            if df is not None and not df.empty:
                stocks = []
                for _, row in df.head(50).iterrows():
                    stocks.append({
                        "code": str(row.get("代码", "")).zfill(6),
                        "name": row.get("名称", ""),
                        "main_net_in": float(row.get("主力净流入", 0)) if "主力净流入" in row else 0,
                        "change_pct": float(row.get("涨跌幅", 0)) if "涨跌幅" in row else 0,
                    })
                return stocks

            return []

        except Exception as e:
            logger.error(f"获取资金流向排行榜失败：{e}")
            return []

    def get_dragon_tiger_list(self, date: Optional[str] = None) -> List[Dict]:
        """
        获取龙虎榜数据

        Args:
            date: 日期 (YYYY-MM-DD)，默认今天

        Returns:
            龙虎榜数据列表
        """
        if self._akshare is None:
            return []

        try:
            if date is None:
                date = datetime.now().strftime("%Y%m%d")
            else:
                date = date.replace("-", "")

            df = self._akshare.stock_lhb_detail_em(start_date=date, end_date=date)

            if df is not None and not df.empty:
                stocks = []
                for _, row in df.iterrows():
                    stocks.append({
                        "code": str(row.get("代码", "")).zfill(6),
                        "name": row.get("名称", ""),
                        "close": float(row.get("收盘价", 0)) if "收盘价" in row else 0,
                        "change_pct": float(row.get("涨跌幅", 0)) if "涨跌幅" in row else 0,
                        "turnover_rate": float(row.get("换手率", 0)) if "换手率" in row else 0,
                        "net_in": float(row.get("龙虎榜净流入", 0)) if "龙虎榜净流入" in row else 0,
                        "buy_amount": float(row.get("买入金额", 0)) if "买入金额" in row else 0,
                        "sell_amount": float(row.get("卖出金额", 0)) if "卖出金额" in row else 0,
                    })
                return stocks

            return []

        except Exception as e:
            logger.error(f"获取龙虎榜数据失败：{e}")
            return []

    def get_industry_fund_flow(self) -> List[Dict]:
        """
        获取行业资金流向

        Returns:
            行业资金流向列表
        """
        if self._akshare is None:
            return []

        try:
            df = self._akshare.stock_sector_fund_flow_summary(indicator="行业资金流")

            if df is not None and not df.empty:
                industries = []
                for _, row in df.head(30).iterrows():
                    industries.append({
                        "name": row.get("行业名称", ""),
                        "net_in": float(row.get("主力净流入", 0)) if "主力净流入" in row else 0,
                        "change_pct": float(row.get("行业涨跌幅", 0)) if "行业涨跌幅" in row else 0,
                        "stock_count": int(row.get("上涨家数", 0)) if "上涨家数" in row else 0,
                    })
                return industries

            return []

        except Exception as e:
            logger.error(f"获取行业资金流向失败：{e}")
            return []

    def get_concept_fund_flow(self) -> List[Dict]:
        """
        获取概念资金流向

        Returns:
            概念资金流向列表
        """
        if self._akshare is None:
            return []

        try:
            df = self._akshare.stock_sector_fund_flow_summary(indicator="概念资金流")

            if df is not None and not df.empty:
                concepts = []
                for _, row in df.head(30).iterrows():
                    concepts.append({
                        "name": row.get("概念名称", ""),
                        "net_in": float(row.get("主力净流入", 0)) if "主力净流入" in row else 0,
                        "change_pct": float(row.get("概念涨跌幅", 0)) if "概念涨跌幅" in row else 0,
                        "stock_count": int(row.get("上涨家数", 0)) if "上涨家数" in row else 0,
                    })
                return concepts

            return []

        except Exception as e:
            logger.error(f"获取概念资金流向失败：{e}")
            return []

    def get_market_fund_flow(self) -> Dict:
        """
        获取大盘资金流向

        Returns:
            大盘资金流向汇总
        """
        if self._akshare is None:
            return {}

        try:
            # 获取市场总体资金流向
            df = self._akshare.stock_market_fund_flow()

            if df is not None and not df.empty:
                latest = df.iloc[0] if len(df) > 0 else None
                if latest is not None:
                    return {
                        "main_net_in": float(latest.get("主力净流入", 0)) if "主力净流入" in latest else 0,
                        "large_order_net_in": float(latest.get("超大单净流入", 0)) if "超大单净流入" in latest else 0,
                        "medium_order_net_in": float(latest.get("大单净流入", 0)) if "大单净流入" in latest else 0,
                        "small_order_net_in": float(latest.get("中单净流入", 0)) if "中单净流入" in latest else 0,
                        "retail_net_in": float(latest.get("小单净流入", 0)) if "小单净流入" in latest else 0,
                        "timestamp": datetime.now(),
                    }

            return {}

        except Exception as e:
            logger.error(f"获取大盘资金流向失败：{e}")
            return {}


__all__ = ["FundCollector"]
