"""
行情数据采集器 - 从 AkShare 等源获取 A 股行情数据
"""
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import pandas as pd
import urllib.request
import urllib.error
import json
import os

from src.utils.logger import get_logger

logger = get_logger(__name__)


class PriceCollector:
    """
    行情数据采集器

    使用 Baostock 作为主要数据源（更稳定），东方财富 API 作为备用
    支持：
    - 实时行情
    - K 线数据（日线/分钟线）
    - 历史行情
    - 指数数据
    """

    def __init__(self):
        self._akshare = None
        self._baostock = None
        self._init_baostock()
        self._init_akshare()

    def _init_baostock(self):
        """初始化 Baostock"""
        try:
            import baostock as bs
            bs.login()
            self._baostock = bs
            logger.info("Baostock 初始化成功")
        except ImportError:
            logger.warning("Baostock 未安装，将使用 AkShare")
        except Exception as e:
            logger.error(f"Baostock 初始化失败：{e}")

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

    def get_realtime_quote(self, stock_code: str) -> Optional[Dict]:
        """
        获取实时行情

        Args:
            stock_code: 股票代码 (如：000001 或 000001.SZ)

        Returns:
            实时行情数据字典
        """
        if self._akshare is None:
            logger.error("AkShare 未初始化")
            return None

        try:
            # 标准化股票代码
            code = self._normalize_code(stock_code)

            # 获取实时行情
            df = self._akshare.stock_zh_a_spot_em()

            if df is not None and not df.empty:
                stock_data = df[df["代码"] == code]
                if not stock_data.empty:
                    row = stock_data.iloc[0]
                    return {
                        "code": code,
                        "name": row.get("名称", ""),
                        "price": float(row.get("最新价", 0)),
                        "change_pct": float(row.get("涨跌幅", 0)),
                        "change_amount": float(row.get("涨跌额", 0)),
                        "volume": float(row.get("成交量", 0)),
                        "amount": float(row.get("成交额", 0)),
                        "high": float(row.get("最高", 0)),
                        "low": float(row.get("最低", 0)),
                        "open": float(row.get("今开", 0)),
                        "pre_close": float(row.get("昨收", 0)),
                        "pe_ratio": float(row.get("市盈率 - 动态", 0)) if "市盈率 - 动态" in row else 0,
                        "pb_ratio": float(row.get("市净率", 0)) if "市净率" in row else 0,
                        "market_cap": float(row.get("总市值", 0)) if "总市值" in row else 0,
                        "turnover_rate": float(row.get("换手率", 0)) if "换手率" in row else 0,
                        "timestamp": datetime.now(),
                    }
            logger.warning(f"未找到股票 {code} 的实时行情")
            return None

        except Exception as e:
            logger.error(f"获取实时行情失败：{e}")
            return None

    def get_kline(
        self,
        stock_code: str,
        period: str = "daily",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
    ) -> pd.DataFrame:
        """
        获取 K 线数据

        Args:
            stock_code: 股票代码
            period: 周期 (daily/weekly/monthly/1m/5m/15m/30m/60m)
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            limit: 数据条数限制

        Returns:
            DataFrame 包含 K 线数据
        """
        if self._akshare is None:
            logger.error("AkShare 未初始化")
            return pd.DataFrame()

        try:
            code = self._normalize_code(stock_code)

            # 根据周期选择 API
            if period in ["1m", "5m", "15m", "30m", "60m"]:
                # 分钟线
                df = self._get_minute_kline(code, period)
            else:
                # 日线/周线/月线
                df = self._get_daily_kline(code, period, start_date, end_date, limit)

            if df is not None and not df.empty:
                # 标准化列名
                df = self._standardize_columns(df)
                return df

            return pd.DataFrame()

        except Exception as e:
            logger.error(f"获取 K 线数据失败：{e}")
            return pd.DataFrame()

    def _get_daily_kline(
        self,
        code: str,
        period: str,
        start_date: Optional[str],
        end_date: Optional[str],
        limit: int,
    ) -> Optional[pd.DataFrame]:
        """获取日线数据"""
        # 优先使用 Baostock（更稳定）
        if self._baostock:
            try:
                return self._get_from_baostock(code, start_date, end_date, limit)
            except Exception as e:
                logger.warning(f"Baostock 获取失败，尝试 AkShare: {e}")

        # 备用：使用 AkShare
        if self._akshare:
            try:
                df = self._akshare.stock_zh_a_hist(
                    symbol=code,
                    period=period,
                    start_date=start_date.replace("-", "") if start_date else None,
                    end_date=end_date.replace("-", "") if end_date else None,
                    adjust="qfq"
                )
                if df is not None and not df.empty:
                    return df.head(limit) if limit else df
            except Exception as e:
                logger.warning(f"AkShare 获取失败，尝试直接连接：{e}")

        # 最后尝试：直接连接东方财富 API
        try:
            return self._fetch_from_em_api(code, start_date, end_date, limit)
        except Exception as e:
            logger.error(f"获取日线数据失败：{e}")
            return None

    def _get_from_baostock(
        self,
        code: str,
        start_date: Optional[str],
        end_date: Optional[str],
        limit: int,
    ) -> Optional[pd.DataFrame]:
        """
        从 Baostock 获取日线数据

        Args:
            code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            limit: 数据条数限制

        Returns:
            DataFrame 包含 K 线数据
        """
        # 转换股票代码格式
        if code.startswith("6"):
            bs_code = f"sh.{code}"
        else:
            bs_code = f"sz.{code}"

        # 默认日期范围
        if not start_date:
            start_date = "2024-01-01"
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        rs = self._baostock.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume,amount",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="3"  # 前复权
        )

        if rs.error_code != "0":
            raise Exception(f"Baostock 错误：{rs.error_msg}")

        data_list = []
        while rs.next():
            data_list.append(rs.get_row_data())

        if data_list:
            df = pd.DataFrame(data_list, columns=rs.fields)
            df = df.rename(columns={
                "date": "trade_date",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
                "amount": "amount",
            })

            # 转换数据类型
            numeric_cols = ["open", "high", "low", "close", "volume", "amount"]
            for col in numeric_cols:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            df["pre_close"] = df["close"].shift(1)
            df["change_pct"] = ((df["close"] - df["pre_close"]) / df["pre_close"] * 100).fillna(0)
            df["change_amount"] = (df["close"] - df["pre_close"]).fillna(0)

            return df.head(limit)

        return None

    def _fetch_from_em_api(
        self,
        code: str,
        start_date: Optional[str],
        end_date: Optional[str],
        limit: int,
    ) -> Optional[pd.DataFrame]:
        """
        直接从东方财富 API 获取数据（不使用 AkShare）

        Args:
            code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            limit: 数据条数限制

        Returns:
            DataFrame 包含 K 线数据
        """
        # 标准化代码
        if code.startswith("6"):
            secid = f"1.{code}"
        else:
            secid = f"0.{code}"

        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        params = {
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
            "klt": "101",
            "fqt": "1",
            "secid": secid,
            "beg": "0",
            "end": "20500101"
        }

        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        full_url = f"{url}?{query_string}"

        # 使用 urllib 并禁用代理
        req = urllib.request.Request(
            full_url,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        # 创建不使用代理的 opener
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        )

        with opener.open(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))

            if data.get("data") and data["data"].get("klines"):
                klines = data["data"]["klines"]

                # 解析数据
                columns = ["trade_date", "open", "close", "high", "low", "volume", "amount",
                           "amplitude", "change_pct", "change_amount", "turnover_rate"]

                rows = []
                for line in klines[:limit]:
                    parts = line.split(",")
                    if len(parts) >= 11:
                        rows.append({
                            "trade_date": parts[0],
                            "open": float(parts[1]),
                            "close": float(parts[2]),
                            "high": float(parts[3]),
                            "low": float(parts[4]),
                            "volume": float(parts[5]),
                            "amount": float(parts[6]),
                            "amplitude": float(parts[7]),
                            "change_pct": float(parts[8]),
                            "change_amount": float(parts[9]),
                            "turnover_rate": float(parts[10]) if len(parts) > 10 else 0,
                        })

                df = pd.DataFrame(rows)
                if not df.empty:
                    # 添加 pre_close 列
                    df["pre_close"] = df["close"].shift(1)
                    logger.info(f"直接从东方财富 API 获取 {len(df)} 条数据")
                    return df

            return None

    def _get_minute_kline(self, code: str, period: str) -> Optional[pd.DataFrame]:
        """获取分钟线数据"""
        try:
            period_map = {
                "1m": "1",
                "5m": "5",
                "15m": "15",
                "30m": "30",
                "60m": "60",
            }
            ak_period = period_map.get(period, "5")

            df = self._akshare.stock_zh_a_hist_min_em(
                symbol=code,
                period=ak_period,
                adjust="qfq"
            )

            return df

        except Exception as e:
            logger.error(f"获取分钟线数据失败：{e}")
            return None

    def _standardize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化列名"""
        # 东方财富列名映射
        column_map = {
            "日期": "trade_date",
            "时间": "trade_time",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
            "振幅": "amplitude",
            "涨跌幅": "change_pct",
            "涨跌额": "change_amount",
            "换手率": "turnover_rate",
            "收盘价": "close",
            "今开": "open",
            "最高": "high",
            "最低": "low",
            "昨收": "pre_close",
        }

        df = df.rename(columns={k: v for k, v in column_map.items() if k in df.columns})

        # 确保日期列存在
        if "trade_date" not in df.columns and "trade_time" in df.columns:
            df["trade_date"] = pd.to_datetime(df["trade_time"]).dt.date

        return df

    def get_index_quote(self, index_code: str) -> Optional[Dict]:
        """
        获取指数行情

        Args:
            index_code: 指数代码 (如：000300 沪深 300)

        Returns:
            指数行情数据
        """
        if self._akshare is None:
            return None

        try:
            df = self._akshare.stock_zh_index_spot()

            if df is not None and not df.empty:
                # 查找对应指数
                symbol = index_code.zfill(6)
                index_data = df[df["代码"] == symbol]

                if not index_data.empty:
                    row = index_data.iloc[0]
                    return {
                        "code": symbol,
                        "name": row.get("名称", ""),
                        "price": float(row.get("最新价", 0)),
                        "change_pct": float(row.get("涨跌幅", 0)),
                        "timestamp": datetime.now(),
                    }

            return None

        except Exception as e:
            logger.error(f"获取指数行情失败：{e}")
            return None

    def get_all_stocks(self) -> List[Dict]:
        """
        获取所有 A 股股票列表

        Returns:
            股票列表
        """
        if self._akshare is None:
            return []

        try:
            df = self._akshare.stock_zh_a_spot_em()

            if df is not None and not df.empty:
                stocks = []
                for _, row in df.iterrows():
                    stocks.append({
                        "code": row.get("代码", ""),
                        "name": row.get("名称", ""),
                        "latest_price": float(row.get("最新价", 0)),
                        "change_pct": float(row.get("涨跌幅", 0)),
                        "volume": float(row.get("成交量", 0)),
                        "amount": float(row.get("成交额", 0)),
                    })
                return stocks

            return []

        except Exception as e:
            logger.error(f"获取股票列表失败：{e}")
            return []

    def get_stock_info(self, stock_code: str) -> Optional[Dict]:
        """
        获取单只股票基本信息

        Args:
            stock_code: 股票代码

        Returns:
            股票信息字典，包含 code, name 等字段
        """
        if self._akshare is None:
            return None

        try:
            # 标准化股票代码
            code = self._normalize_code(stock_code)

            # 获取实时行情
            df = self._akshare.stock_zh_a_spot_em()

            if df is not None and not df.empty:
                stock_data = df[df["代码"] == code]
                if not stock_data.empty:
                    row = stock_data.iloc[0]
                    return {
                        "code": code,
                        "name": row.get("名称", ""),
                        "latest_price": float(row.get("最新价", 0)),
                        "change_pct": float(row.get("涨跌幅", 0)),
                    }
            logger.warning(f"未找到股票 {code} 的信息")
            return None

        except Exception as e:
            logger.error(f"获取股票信息失败：{e}")
            return None

    def get_hs300_stocks(self) -> List[Dict]:
        """
        获取沪深 300 成分股

        Returns:
            沪深 300 成分股列表
        """
        if self._akshare is None:
            return []

        try:
            df = self._akshare.index_stock_cons(symbol="000300")

            if df is not None and not df.empty:
                stocks = []
                for _, row in df.iterrows():
                    code = row.get("品种代码", "") if "品种代码" in row else row.get("股票代码", "")
                    name = row.get("品种名称", "") if "品种名称" in row else row.get("股票简称", "")
                    stocks.append({
                        "code": str(code).zfill(6),
                        "name": name,
                    })
                return stocks

            return []

        except Exception as e:
            logger.error(f"获取沪深 300 成分股失败：{e}")
            return []

    def _normalize_code(self, stock_code: str) -> str:
        """标准化股票代码"""
        code = stock_code.strip()

        # 如果已经包含市场后缀，直接返回
        if code.endswith(".SZ") or code.endswith(".SH"):
            return code[:6]

        # 根据前缀判断市场
        if code.startswith(("6", "9")):
            return code[:6]  # 沪市
        elif code.startswith(("0", "3")):
            return code[:6]  # 深市
        else:
            return code.zfill(6)

    def is_trading_time(self) -> bool:
        """
        判断是否在交易时间内

        Returns:
            是否在交易时间
        """
        now = datetime.now()

        # 周末不交易
        if now.weekday() >= 5:
            return False

        # 交易时段：9:30-11:30, 13:00-15:00
        hour = now.hour
        minute = now.minute

        if hour < 9 or hour >= 15:
            return False
        if hour == 9 and minute < 30:
            return False
        if hour == 11 and minute >= 30:
            if hour == 13 or (hour == 12 and minute < 30):
                return False

        return True


__all__ = ["PriceCollector"]
