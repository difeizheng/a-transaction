"""
板块联动分析模块 - 行业/概念板块资金流向与联动性分析

功能：
- 获取个股所属行业/概念板块
- 分析板块资金流向
- 计算板块联动性评分
- 识别龙头股状态
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SectorSignal:
    """板块信号"""
    sector_name: str             # 板块名称
    sector_type: str             # industry/concept
    change_pct: float            # 板块涨跌幅
    fund_net_in: float           # 资金净流入
    stock_count: int             # 板块股票数量
    up_ratio: float              # 上涨比例
    leaders: List[str]           # 龙头股列表
    linkage_score: float         # 联动性得分 [-1, 1]
    signal: str                  # strong/normal/weak


class SectorAnalyzer:
    """
    板块联动分析器

    分析逻辑：
    1. 获取个股所属行业/概念板块
    2. 分析板块整体表现
    3. 计算板块内个股联动性
    4. 识别板块龙头股
    """

    def __init__(self):
        self._akshare = None
        self._init_akshare()

        # 缓存的板块数据
        self._sector_cache: Dict[str, Dict] = {}
        self._cache_time: Optional[datetime] = None

    def _init_akshare(self):
        """初始化 AkShare"""
        try:
            import akshare as ak
            self._akshare = ak
            logger.debug("SectorAnalyzer: AkShare 初始化成功")
        except Exception as e:
            logger.error(f"SectorAnalyzer: AkShare 初始化失败 - {e}")

    def get_stock_sector(self, stock_code: str) -> Dict[str, List[str]]:
        """
        获取个股所属行业/概念板块

        Args:
            stock_code: 股票代码

        Returns:
            {industry: [行业列表], concept: [概念列表]}
        """
        if self._akshare is None:
            return {"industry": [], "concept": []}

        try:
            # 获取股票所属板块
            df = self._akshare.stock_board_industry_name_em()

            if df is not None and not df.empty:
                # 这里需要根据实际 API 返回结构调整
                # 暂时返回模拟数据
                pass

            # 使用东方财富行业分类
            return self._get_sector_from_em(stock_code)

        except Exception as e:
            logger.error(f"获取股票板块失败：{e}")
            return {"industry": [], "concept": []}

    def _get_sector_from_em(self, stock_code: str) -> Dict[str, List[str]]:
        """从东方财富获取板块信息"""
        # 简化实现：返回行业名称
        # 实际使用时需要调用具体 API
        return {
            "industry": ["未知行业"],
            "concept": ["未知概念"]
        }

    def get_sector_fund_flow(self, sector_name: str, sector_type: str = "industry") -> Optional[Dict]:
        """
        获取板块资金流向

        Args:
            sector_name: 板块名称
            sector_type: industry/concept

        Returns:
            板块资金流向数据
        """
        if self._akshare is None:
            return None

        try:
            if sector_type == "industry":
                df = self._akshare.stock_sector_fund_flow_summary(indicator="行业资金流")
            else:
                df = self._akshare.stock_sector_fund_flow_summary(indicator="概念资金流")

            if df is not None and not df.empty:
                row = df[df["行业名称"] == sector_name] if "行业名称" in df.columns else None
                if row is not None and len(row) > 0:
                    return {
                        "net_in": float(row.iloc[0].get("主力净流入", 0)),
                        "change_pct": float(row.iloc[0].get("行业涨跌幅", 0)),
                        "stock_count": int(row.iloc[0].get("上涨家数", 0)),
                    }

            return None

        except Exception as e:
            logger.error(f"获取板块资金流向失败：{e}")
            return None

    def get_all_sector_fund_flow(self, sector_type: str = "industry") -> List[Dict]:
        """
        获取所有板块资金流向

        Args:
            sector_type: industry/concept

        Returns:
            板块资金流向列表
        """
        if self._akshare is None:
            return []

        try:
            if sector_type == "industry":
                df = self._akshare.stock_sector_fund_flow_summary(indicator="行业资金流")
            else:
                df = self._akshare.stock_sector_fund_flow_summary(indicator="概念资金流")

            if df is not None and not df.empty:
                result = []
                for _, row in df.iterrows():
                    result.append({
                        "name": row.get("行业名称", "") if "行业名称" in df.columns else row.get("概念名称", ""),
                        "net_in": float(row.get("主力净流入", 0)),
                        "change_pct": float(row.get("行业涨跌幅", 0)) if "行业涨跌幅" in df.columns else float(row.get("概念涨跌幅", 0)),
                        "up_count": int(row.get("上涨家数", 0)),
                        "down_count": int(row.get("下跌家数", 0)) if "下跌家数" in df.columns else 0,
                    })
                return result

            return []

        except Exception as e:
            logger.error(f"获取板块资金流向失败：{e}")
            return []

    def analyze_sector(self, stock_code: str, stock_price_data: pd.DataFrame) -> SectorSignal:
        """
        分析个股所属板块的整体表现

        Args:
            stock_code: 股票代码
            stock_price_data: 个股价格数据

        Returns:
            板块信号
        """
        # 获取板块信息
        sector_info = self.get_stock_sector(stock_code)

        if not sector_info["industry"] and not sector_info["concept"]:
            return SectorSignal(
                sector_name="未知",
                sector_type="unknown",
                change_pct=0,
                fund_net_in=0,
                stock_count=0,
                up_ratio=0.5,
                leaders=[],
                linkage_score=0,
                signal="weak"
            )

        # 使用主要行业板块
        sector_name = sector_info["industry"][0] if sector_info["industry"] else sector_info["concept"][0]
        sector_type = "industry" if sector_info["industry"] else "concept"

        # 获取板块资金流向
        sector_flow = self.get_sector_fund_flow(sector_name, sector_type)

        if sector_flow is None:
            sector_flow = {"net_in": 0, "change_pct": 0, "stock_count": 0}

        # 计算联动性得分
        linkage_score = self._calculate_linkage_score(sector_flow)

        # 确定信号强度
        if linkage_score > 0.5:
            signal = "strong"
        elif linkage_score > 0:
            signal = "normal"
        else:
            signal = "weak"

        return SectorSignal(
            sector_name=sector_name,
            sector_type=sector_type,
            change_pct=sector_flow.get("change_pct", 0),
            fund_net_in=sector_flow.get("net_in", 0),
            stock_count=sector_flow.get("stock_count", 0),
            up_ratio=sector_flow.get("up_count", 0) / max(1, sector_flow.get("up_count", 0) + sector_flow.get("down_count", 0)),
            leaders=self._get_sector_leaders(sector_name),
            linkage_score=linkage_score,
            signal=signal
        )

    def _calculate_linkage_score(self, sector_flow: Dict) -> float:
        """
        计算联动性得分

        Args:
            sector_flow: 板块资金流向数据

        Returns:
            联动性得分 [-1, 1]
        """
        score = 0.0

        # 资金流向得分 (40%)
        net_in = sector_flow.get("net_in", 0)
        if net_in > 100000000:  # 1 亿以上
            score += 0.4
        elif net_in > 50000000:
            score += 0.2
        elif net_in < -100000000:
            score -= 0.4
        elif net_in < -50000000:
            score -= 0.2

        # 涨跌幅得分 (40%)
        change_pct = sector_flow.get("change_pct", 0)
        if change_pct > 2:
            score += 0.4
        elif change_pct > 1:
            score += 0.2
        elif change_pct < -2:
            score -= 0.4
        elif change_pct < -1:
            score -= 0.2

        # 上涨比例得分 (20%)
        up_ratio = sector_flow.get("up_count", 0) / max(1, sector_flow.get("up_count", 0) + sector_flow.get("down_count", 0))
        if up_ratio > 0.7:
            score += 0.2
        elif up_ratio > 0.5:
            score += 0.1
        elif up_ratio < 0.3:
            score -= 0.2
        elif up_ratio < 0.5:
            score -= 0.1

        return round(score, 3)

    def _get_sector_leaders(self, sector_name: str) -> List[str]:
        """
        获取板块龙头股

        Args:
            sector_name: 板块名称

        Returns:
            龙头股代码列表
        """
        # 简化实现：返回常见的龙头股映射
        leaders_map = {
            "银行": ["600000", "601398", "601288"],
            "证券": ["600030", "601688", "000776"],
            "保险": ["601318", "601628", "601601"],
            "房地产": ["000002", "001979", "600048"],
            "白酒": ["600519", "000858", "000568"],
            "医药": ["600276", "000538", "300760"],
            "新能源": ["300750", "002594", "300014"],
            "半导体": ["688981", "002371", "603986"],
            "人工智能": ["002230", "600588", "002415"],
        }

        for name, leaders in leaders_map.items():
            if name in sector_name:
                return leaders

        return []

    def get_hot_sectors(self, top_n: int = 5) -> List[Dict]:
        """
        获取热门板块

        Args:
            top_n: 返回数量

        Returns:
            热门板块列表
        """
        # 获取行业资金流向
        industry_flows = self.get_all_sector_fund_flow("industry")

        if not industry_flows:
            return []

        # 按涨跌幅排序
        industry_flows.sort(key=lambda x: x.get("change_pct", 0), reverse=True)

        return industry_flows[:top_n]

    def get_sector_sentiment(self) -> Dict:
        """
        获取板块情绪

        Returns:
            板块情绪数据
        """
        industry_flows = self.get_all_sector_fund_flow("industry")
        concept_flows = self.get_all_sector_fund_flow("concept")

        if not industry_flows and not concept_flows:
            return {"sentiment": "neutral", "hot_count": 0, "cold_count": 0}

        all_flows = industry_flows + concept_flows

        # 统计热门和冷门板块
        hot_count = sum(1 for f in all_flows if f.get("change_pct", 0) > 2)
        cold_count = sum(1 for f in all_flows if f.get("change_pct", 0) < -2)

        # 确定整体情绪
        if hot_count > cold_count * 2:
            sentiment = "bullish"
        elif cold_count > hot_count * 2:
            sentiment = "bearish"
        else:
            sentiment = "neutral"

        return {
            "sentiment": sentiment,
            "hot_count": hot_count,
            "cold_count": cold_count,
            "total_count": len(all_flows),
        }


def analyze_stock_sector(stock_code: str) -> Optional[SectorSignal]:
    """
    分析个股所属板块（便捷函数）

    Args:
        stock_code: 股票代码

    Returns:
        板块信号
    """
    try:
        analyzer = SectorAnalyzer()
        # 获取简单的板块数据
        df = pd.DataFrame()  # 实际需要传入价格数据
        return analyzer.analyze_sector(stock_code, df)
    except Exception as e:
        logger.error(f"分析板块失败：{e}")
        return None


__all__ = [
    "SectorAnalyzer",
    "SectorSignal",
    "analyze_stock_sector",
]
