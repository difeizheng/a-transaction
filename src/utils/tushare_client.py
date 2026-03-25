"""
Tushare 数据客户端 - 封装 Tushare Pro API

提供稳定的 A 股数据源支持：
- K 线数据（日线/周线/月线）
- 实时行情（需要积分）
- 资金流向（需要积分）
- 股票基本信息
"""
import tushare as ts
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger(__name__)


class TushareClient:
    """
    Tushare Pro API 客户端

    积分说明：
    - 基础用户：约 5000 次/天调用额度
    - 120 积分：解锁实时行情
    - 200 积分：解锁资金流向
    - 300 积分：解锁龙虎榜
    """

    def __init__(self, token: str = None):
        """
        初始化 Tushare 客户端

        Args:
            token: Tushare Token，为空则不初始化
        """
        self.token = token
        self.pro = None
        self._initialized = False

        if token:
            try:
                ts.set_token(token)
                self.pro = ts.pro_api()
                self._initialized = True
                logger.info(f"Tushare 初始化成功 (token={token[:10]}...)")
            except Exception as e:
                logger.error(f"Tushare 初始化失败：{e}")

    def is_available(self) -> bool:
        """检查 Tushare 是否可用"""
        return self._initialized and self.pro is not None

    def get_daily_kline(
        self,
        ts_code: str,
        start_date: str = None,
        end_date: str = None,
        limit: int = 120,
    ) -> Optional[pd.DataFrame]:
        """
        获取日线 K 线数据（免费接口）

        Args:
            ts_code: 股票代码（格式：000948.SZ 或 600000.SH）
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
            limit: 最大返回条数

        Returns:
            DataFrame 包含 K 线数据
        """
        if not self.is_available():
            return None

        try:
            # 标准化股票代码
            ts_code = self._normalize_ts_code(ts_code)

            # 默认日期范围（最近 6 个月）
            if not end_date:
                end_date = datetime.now().strftime("%Y%m%d")
            else:
                end_date = end_date.replace("-", "")

            if not start_date:
                # 向前推 6 个月
                start = datetime.now() - timedelta(days=180)
                start_date = start.strftime("%Y%m%d")
            else:
                start_date = start_date.replace("-", "")

            df = self.pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)

            logger.debug(f"Tushare 请求：ts_code={ts_code}, start={start_date}, end={end_date}")
            if df is None:
                logger.warning(f"Tushare 返回 None ({ts_code})")
            elif df.empty:
                logger.warning(f"Tushare 返回空 DataFrame ({ts_code})")
            else:
                logger.debug(f"Tushare 返回 {len(df)} 条数据")

            if df is not None and not df.empty:
                df = df.sort_values("trade_date")
                return df.head(limit)

            return None

        except Exception as e:
            logger.warning(f"Tushare 获取日线失败 ({ts_code}): {e}")
            return None

    def get_weekly_kline(
        self,
        ts_code: str,
        start_date: str = None,
        end_date: str = None,
        limit: int = 120,
    ) -> Optional[pd.DataFrame]:
        """
        获取周线 K 线数据

        Args:
            ts_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            limit: 最大返回条数

        Returns:
            DataFrame 包含周 K 线数据
        """
        if not self.is_available():
            return None

        try:
            ts_code = self._normalize_ts_code(ts_code)

            if not end_date:
                end_date = datetime.now().strftime("%Y%m%d")
            else:
                end_date = end_date.replace("-", "")

            if not start_date:
                start = datetime.now() - timedelta(days=365)
                start_date = start.strftime("%Y%m%d")
            else:
                start_date = start_date.replace("-", "")

            df = self.pro.weekly(ts_code=ts_code, start_date=start_date, end_date=end_date)

            if df is not None and not df.empty:
                df = df.sort_values("trade_date")
                return df.head(limit)

            return None

        except Exception as e:
            logger.warning(f"Tushare 获取周线失败 ({ts_code}): {e}")
            return None

    def get_monthly_kline(
        self,
        ts_code: str,
        start_date: str = None,
        end_date: str = None,
        limit: int = 120,
    ) -> Optional[pd.DataFrame]:
        """
        获取月线 K 线数据

        Args:
            ts_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            limit: 最大返回条数

        Returns:
            DataFrame 包含月 K 线数据
        """
        if not self.is_available():
            return None

        try:
            ts_code = self._normalize_ts_code(ts_code)

            if not end_date:
                end_date = datetime.now().strftime("%Y%m%d")
            else:
                end_date = end_date.replace("-", "")

            if not start_date:
                start = datetime.now() - timedelta(days=365 * 3)
                start_date = start.strftime("%Y%m%d")
            else:
                start_date = start_date.replace("-", "")

            df = self.pro.monthly(ts_code=ts_code, start_date=start_date, end_date=end_date)

            if df is not None and not df.empty:
                df = df.sort_values("trade_date")
                return df.head(limit)

            return None

        except Exception as e:
            logger.warning(f"Tushare 获取月线失败 ({ts_code}): {e}")
            return None

    def get_realtime_quote(self, ts_code: str) -> Optional[Dict]:
        """
        获取实时行情（需要 120 积分）

        Args:
            ts_code: 股票代码

        Returns:
            实时行情数据字典
        """
        if not self.is_available():
            return None

        try:
            ts_code = self._normalize_ts_code(ts_code)
            df = self.pro.quote(ts_code=ts_code)

            if df is not None and not df.empty:
                row = df.iloc[0]
                return {
                    "code": ts_code[:6],
                    "name": row.get("name", ""),
                    "price": float(row.get("close", 0)),
                    "change_pct": float(row.get("pct_chg", 0)),
                    "change_amount": float(row.get("close", 0)) - float(row.get("pre_close", 0)),
                    "open": float(row.get("open", 0)),
                    "high": float(row.get("high", 0)),
                    "low": float(row.get("low", 0)),
                    "pre_close": float(row.get("pre_close", 0)),
                    "volume": float(row.get("vol", 0)) * 100,  # 手转股
                    "amount": float(row.get("amount", 0)) * 1000,  # 千元转元
                    "turnover_rate": float(row.get("turnover_rate", 0)) if "turnover_rate" in row else 0,
                    "timestamp": datetime.now(),
                }

            return None

        except Exception as e:
            logger.warning(f"Tushare 获取实时行情失败 ({ts_code}): {e}")
            return None

    def get_moneyflow(self, ts_code: str, start_date: str = None, end_date: str = None) -> Optional[pd.DataFrame]:
        """
        获取资金流向数据（需要 200 积分）

        Args:
            ts_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            DataFrame 包含资金流向数据
        """
        if not self.is_available():
            return None

        try:
            ts_code = self._normalize_ts_code(ts_code)

            if not end_date:
                end_date = datetime.now().strftime("%Y%m%d")
            else:
                end_date = end_date.replace("-", "")

            if not start_date:
                start = datetime.now() - timedelta(days=30)
                start_date = start.strftime("%Y%m%d")
            else:
                start_date = start_date.replace("-", "")

            df = self.pro.moneyflow(ts_code=ts_code, start_date=start_date, end_date=end_date)

            if df is not None and not df.empty:
                return df

            return None

        except Exception as e:
            logger.warning(f"Tushare 获取资金流向失败 ({ts_code}): {e}")
            return None

    def get_stock_info(self, ts_code: str) -> Optional[Dict]:
        """
        获取股票基本信息

        Args:
            ts_code: 股票代码

        Returns:
            股票信息字典
        """
        if not self.is_available():
            return None

        try:
            ts_code = self._normalize_ts_code(ts_code)

            # 获取股票列表
            df = self.pro.stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name,area,industry,market,list_date")

            if df is not None and not df.empty:
                stock_df = df[df["ts_code"] == ts_code]
                if not stock_df.empty:
                    row = stock_df.iloc[0]
                    return {
                        "code": ts_code[:6],
                        "name": row.get("name", ""),
                        "area": row.get("area", ""),
                        "industry": row.get("industry", ""),
                        "market": row.get("market", ""),
                        "list_date": row.get("list_date", ""),
                    }

            return None

        except Exception as e:
            logger.warning(f"Tushare 获取股票信息失败 ({ts_code}): {e}")
            return None

    def get_all_stocks(self) -> List[Dict]:
        """
        获取全部 A 股股票列表

        Returns:
            股票列表
        """
        if not self.is_available():
            return []

        try:
            # 获取股票列表
            df = self.pro.stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name,area,industry,market,list_date")

            if df is not None and not df.empty:
                stocks = []
                for _, row in df.iterrows():
                    stocks.append({
                        "ts_code": row.get("ts_code", ""),
                        "code": row.get("ts_code", "")[:6],
                        "symbol": row.get("symbol", ""),
                        "name": row.get("name", ""),
                        "area": row.get("area", ""),
                        "industry": row.get("industry", ""),
                        "market": row.get("market", ""),
                    })
                return stocks

            return []

        except Exception as e:
            logger.error(f"Tushare 获取股票列表失败：{e}")
            return []

    def get_trade_cal(self, exchange: str = "SSE", year: int = None) -> Optional[pd.DataFrame]:
        """
        获取交易日历

        Args:
            exchange: 交易所 SSE(上交所)/SZSE(深交所)
            year: 年份

        Returns:
            DataFrame 包含交易日历
        """
        if not self.is_available():
            return None

        try:
            if not year:
                year = datetime.now().year

            start_date = f"{year}0101"
            end_date = f"{year}1231"

            df = self.pro.trade_cal(exchange=exchange, start_date=start_date, end_date=end_date)

            if df is not None and not df.empty:
                return df

            return None

        except Exception as e:
            logger.warning(f"Tushare 获取交易日历失败：{e}")
            return None

    def _normalize_ts_code(self, code: str) -> str:
        """
        标准化股票代码格式

        Args:
            code: 股票代码（支持多种格式）

        Returns:
            标准化格式（000948.SZ 或 600000.SH）
        """
        code = code.strip().upper()

        # 如果已经是标准格式，直接返回
        if ".SZ" in code or ".SH" in code:
            return code[:9]

        # 提取 6 位数字代码
        code_num = "".join(filter(str.isdigit, code))[:6].zfill(6)

        # 根据前缀判断市场
        if code.startswith("6") or code.startswith("9"):
            return f"{code_num}.SH"
        elif code.startswith("0") or code.startswith("3"):
            return f"{code_num}.SZ"
        else:
            # 默认根据数字判断
            if code_num.startswith("6") or code_num.startswith("9"):
                return f"{code_num}.SH"
            else:
                return f"{code_num}.SZ"


__all__ = ["TushareClient"]
