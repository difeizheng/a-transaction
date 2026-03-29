"""
选股模块 - 扩大选股范围

功能：
1. 从全市场筛选符合条件的股票
2. 过滤 ST、*ST、高风险股票
3. 根据市值、流动性、基本面筛选
4. 行业分散化配置
"""
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime
import pandas as pd
import numpy as np

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class StockFilterConfig:
    """选股配置"""
    # 市值要求
    min_market_cap: float = 10e9   # 最小市值 100 亿
    max_market_cap: float = 500e9  # 最大市值 5000 亿

    # 流动性要求
    min_daily_turnover: float = 1e8  # 日均成交 1 亿
    min_turnover_rate: float = 0.01  # 换手率 1%

    # 基本面要求
    min_roe: float = 0.05      # ROE > 5%
    max_pe: float = 50         # 市盈率 < 50
    max_pb: float = 10         # 市净率 < 10

    # 技术面要求
    min_price: float = 3       # 股价 > 3 元
    max_price: float = 500     # 股价 < 500 元

    # 风险过滤
    exclude_st: bool = True
    exclude_kcb: bool = True   # 科创板
    exclude_cyq: bool = False  # 创业板
    exclude_new_stock: bool = True  # 次新股（上市<60 天）
    new_stock_days: int = 60

    # 行业配置
    max_industry_weight: float = 0.20  # 单行业最大 20%
    min_industry_count: int = 3        # 至少覆盖 3 个行业

    # 选股数量
    target_stock_count: int = 15       # 目标选股数量
    max_stock_count: int = 20          # 最大选股数量


@dataclass
class StockInfo:
    """股票信息"""
    code: str
    name: str
    industry: str
    market_cap: float
    price: float
    pe_ratio: float
    pb_ratio: float
    roe: float
    turnover_rate: float
    daily_turnover: float
    score: float = 0.0  # 综合得分


class StockSelector:
    """
    选股器

    功能：
    1. 全市场股票筛选
    2. 风险股票过滤
    3. 行业分散化
    4. 综合评分排序
    """

    def __init__(self, config: Optional[StockFilterConfig] = None):
        self.config = config or StockFilterConfig()
        self._akshare = None
        self._init_akshare()

        # 行业分类缓存
        self.industry_map: Dict[str, str] = {}  # code -> industry

    def _init_akshare(self):
        """初始化 AkShare"""
        try:
            import akshare as ak
            self._akshare = ak
            logger.info("StockSelector: AkShare 初始化成功")
        except ImportError:
            logger.error("AkShare 未安装")
        except Exception as e:
            logger.error(f"AkShare 初始化失败：{e}")

    def get_all_stocks(self) -> pd.DataFrame:
        """
        获取全市场股票列表

        Returns:
            包含所有股票基本信息的 DataFrame
        """
        if self._akshare is None:
            return pd.DataFrame()

        try:
            # 获取 A 股实时行情
            df = self._akshare.stock_zh_a_spot_em()

            if df is not None and not df.empty:
                # 重命名列
                df = df.rename(columns={
                    "代码": "code",
                    "名称": "name",
                    "最新价": "price",
                    "涨跌幅": "change_pct",
                    "总市值": "market_cap",
                    "市盈率 - 动态": "pe_ratio",
                    "市净率": "pb_ratio",
                    "换手率": "turnover_rate",
                    "成交额": "turnover_amount",
                })

                return df

        except Exception as e:
            logger.error(f"获取股票列表失败：{e}")

        return pd.DataFrame()

    def filter_stocks(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        过滤风险股票

        Args:
            df: 股票数据

        Returns:
            过滤后的数据
        """
        if df.empty:
            return df

        original_count = len(df)

        # 1. 过滤 ST 股票
        if self.config.exclude_st:
            df = df[~df["name"].str.contains("ST", na=False)]
            logger.info(f"过滤 ST 股票：{original_count - len(df)} 只")
            original_count = len(df)

        # 2. 过滤科创板
        if self.config.exclude_kcb:
            df = df[~df["code"].str.startswith("688")]
            logger.info(f"过滤科创板：{original_count - len(df)} 只")
            original_count = len(df)

        # 3. 过滤创业板（可选）
        if self.config.exclude_cyq:
            df = df[~df["code"].str.startswith("300")]
            original_count = len(df)

        # 4. 过滤股价异常
        df = df[(df["price"] >= self.config.min_price) &
                (df["price"] <= self.config.max_price)]
        logger.info(f"过滤股价异常：{original_count - len(df)} 只")
        original_count = len(df)

        # 5. 过滤市值异常
        df = df[(df["market_cap"] >= self.config.min_market_cap) &
                (df["market_cap"] <= self.config.max_market_cap)]
        logger.info(f"过滤市值异常：{original_count - len(df)} 只")
        original_count = len(df)

        # 6. 过滤流动性不足
        df = df[df["turnover_amount"] >= self.config.min_daily_turnover]
        logger.info(f"过滤流动性不足：{original_count - len(df)} 只")
        original_count = len(df)

        # 7. 过滤市盈率过高
        df = df[(df["pe_ratio"] > 0) & (df["pe_ratio"] <= self.config.max_pe)]
        logger.info(f"过滤市盈率过高：{original_count - len(df)} 只")

        return df

    def calculate_score(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算综合得分

        评分维度：
        1. 市值得分（适中为好）
        2. 估值得分（低 PE/PB 为好）
        3. 流动性得分（高换手为好）
        4. 动量得分（近期涨幅）

        Returns:
            添加 score 列的 DataFrame
        """
        if df.empty:
            return df

        scores = pd.DataFrame(index=df.index)

        # 1. 市值得分（对数正态分布，中间高）
        mid_cap = (self.config.min_market_cap * self.config.max_market_cap) ** 0.5
        cap_distance = (df["market_cap"] - mid_cap).abs()
        cap_score = 1 - cap_distance / cap_distance.max()
        scores["cap_score"] = cap_score

        # 2. 估值得分（低 PE/PB 为好）
        pe_score = 1 - df["pe_ratio"] / df["pe_ratio"].max()
        pb_score = 1 - df["pb_ratio"] / df["pb_ratio"].max()
        scores["value_score"] = pe_score * 0.6 + pb_score * 0.4

        # 3. 流动性得分（高换手为好）
        turnover_score = df["turnover_rate"] / df["turnover_rate"].max()
        scores["liquidity_score"] = turnover_score

        # 4. 动量得分（近期涨幅适中为好，避免暴涨暴跌）
        change_score = 1 - (df["change_pct"].abs() / df["change_pct"].abs().max())
        scores["momentum_score"] = change_score

        # 综合得分
        df["score"] = (
            scores["cap_score"] * 0.25 +
            scores["value_score"] * 0.35 +
            scores["liquidity_score"] * 0.25 +
            scores["momentum_score"] * 0.15
        )

        return df

    def select_stocks(
        self,
        target_count: Optional[int] = None,
        exclude_codes: Optional[List[str]] = None,
    ) -> List[StockInfo]:
        """
        选股主函数

        Args:
            target_count: 目标选股数量
            exclude_codes: 要排除的股票代码

        Returns:
            选中的股票列表
        """
        if self._akshare is None:
            logger.error("AkShare 未初始化")
            return []

        target = target_count or self.config.target_stock_count

        # 1. 获取全市场股票
        logger.info("获取全市场股票数据...")
        df = self.get_all_stocks()

        if df.empty:
            logger.error("无法获取股票数据")
            return []

        logger.info(f"全市场股票数：{len(df)}")

        # 2. 过滤风险股票
        logger.info("过滤风险股票...")
        df = self.filter_stocks(df)
        logger.info(f"过滤后股票数：{len(df)}")

        # 3. 计算综合得分
        logger.info("计算综合得分...")
        df = self.calculate_score(df)

        # 4. 排除指定股票
        if exclude_codes:
            df = df[~df["code"].isin(exclude_codes)]

        # 5. 按得分排序
        df = df.sort_values("score", ascending=False)

        # 6. 行业分散化选择
        selected = []
        industry_count: Dict[str, int] = {}
        max_per_industry = int(target * self.config.max_industry_weight) + 1

        for _, row in df.iterrows():
            if len(selected) >= self.config.max_stock_count:
                break

            code = row["code"]
            industry = self._get_industry(code)

            # 检查行业配置
            current_count = industry_count.get(industry, 0)
            if current_count >= max_per_industry:
                continue

            # 添加到选中列表
            selected.append(StockInfo(
                code=code,
                name=row.get("name", ""),
                industry=industry,
                market_cap=float(row.get("market_cap", 0)),
                price=float(row.get("price", 0)),
                pe_ratio=float(row.get("pe_ratio", 0)),
                pb_ratio=float(row.get("pb_ratio", 0)),
                roe=0.0,  # 需要额外获取
                turnover_rate=float(row.get("turnover_rate", 0)),
                daily_turnover=float(row.get("turnover_amount", 0)),
                score=float(row.get("score", 0)),
            ))

            industry_count[industry] = current_count + 1

        logger.info(f"选中股票数：{len(selected)}")
        logger.info(f"行业分布：{industry_count}")

        # 7. 返回目标数量
        return selected[:target]

    def _get_industry(self, code: str) -> str:
        """
        获取股票所属行业

        Args:
            code: 股票代码

        Returns:
            行业名称
        """
        # 先从缓存获取
        if code in self.industry_map:
            return self.industry_map[code]

        # 简单行业分类（根据代码前缀）
        if code.startswith("600"):
            industry = "金融"
        elif code.startswith("601"):
            industry = "周期"
        elif code.startswith("603"):
            industry = "制造"
        elif code.startswith("000"):
            industry = "消费"
        elif code.startswith("002"):
            industry = "科技"
        elif code.startswith("003"):
            industry = "医药"
        else:
            industry = "其他"

        self.industry_map[code] = industry
        return industry

    def get_stock_pool(
        self,
        custom_codes: Optional[List[str]] = None,
        use_custom_only: bool = False,
    ) -> List[str]:
        """
        获取最终股票池

        Args:
            custom_codes: 自定义股票代码
            use_custom_only: 是否仅使用自定义股票

        Returns:
            股票代码列表
        """
        if use_custom_only and custom_codes:
            return custom_codes

        # 自动选股
        selected = self.select_stocks()

        if custom_codes:
            # 合并自定义和自动选股
            existing_codes = {s.code for s in selected}
            for code in custom_codes:
                if code not in existing_codes:
                    # 简单添加到列表
                    selected.append(StockInfo(
                        code=code,
                        name="",
                        industry="",
                        market_cap=0,
                        price=0,
                        pe_ratio=0,
                        pb_ratio=0,
                        roe=0,
                        turnover_rate=0,
                        daily_turnover=0,
                        score=0,
                    ))

        return [s.code for s in selected]


# 辅助函数：获取行业分类详情
def get_detailed_industry(code: str) -> Dict[str, str]:
    """
    获取详细的行业分类信息

    Args:
        code: 股票代码

    Returns:
        行业信息字典
    """
    # 这里可以调用 AkShare 获取真实行业数据
    # 目前返回简单分类
    industry_map = {
        "600": "银行/金融",
        "601": "周期/资源",
        "603": "高端制造",
        "605": "消费升级",
        "000": "大消费",
        "002": "中小板/科技",
        "003": "医药生物",
        "300": "创业板/成长",
        "688": "科创板/硬科技",
    }

    for prefix, industry in industry_map.items():
        if code.startswith(prefix):
            return {"industry": industry, "concept": ""}

    return {"industry": "其他", "concept": ""}
