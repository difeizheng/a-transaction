"""
行情数据采集器 - 从 AkShare 等源获取 A 股行情数据

数据源优先级：
- K 线数据：Tushare > Baostock > AkShare > 东方财富 API
- 实时行情：AkShare > 东方财富 API > Tushare
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

    数据源优先级：
    - K 线数据：Tushare(优先) > Baostock > AkShare > 东方财富 API
    - 实时行情：AkShare(优先) > 东方财富 API > Tushare
    """

    def __init__(self, tushare_token: str = None):
        self._akshare = None
        self._baostock = None
        self._tushare = None
        self._init_tushare(tushare_token)
        self._init_baostock()
        self._init_akshare()

    def _init_tushare(self, token: str = None):
        """初始化 Tushare"""
        if not token:
            # 从配置文件读取 token
            try:
                config_path = os.path.join(os.path.dirname(__file__), "../../config.yaml")
                if os.path.exists(config_path):
                    import yaml
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = yaml.safe_load(f)
                        token = config.get("data_sources", {}).get("tushare", {}).get("token", "")
                        enabled = config.get("data_sources", {}).get("tushare", {}).get("enabled", False)
                        if not enabled:
                            token = None
            except Exception as e:
                logger.debug(f"读取 Tushare 配置失败：{e}")

        if token:
            try:
                from src.utils.tushare_client import TushareClient
                self._tushare = TushareClient(token=token)
                if self._tushare.is_available():
                    logger.info("Tushare 初始化成功 (K 线数据优先)")
                else:
                    logger.warning("Tushare 初始化失败，将使用备用数据源")
                    self._tushare = None
            except Exception as e:
                logger.error(f"Tushare 初始化失败：{e}")
                self._tushare = None

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

        数据源优先级：新浪财经 > 腾讯财经 > AkShare > 东方财富 API

        Args:
            stock_code: 股票代码 (如：000001 或 000001.SZ)

        Returns:
            实时行情数据字典
        """
        # 1. 优先尝试新浪财经（最稳定、最快）
        data = self._get_from_sina(stock_code)
        if data is not None:
            logger.debug(f"新浪财经获取实时行情成功 ({stock_code})")
            return data

        # 2. 尝试腾讯财经
        data = self._get_from_tencent(stock_code)
        if data is not None:
            logger.debug(f"腾讯财经获取实时行情成功 ({stock_code})")
            return data

        # 3. 尝试 AkShare
        if self._akshare is not None:
            try:
                code = self._normalize_code(stock_code)
                df = self._akshare.stock_zh_a_spot_em()
                if df is not None and not df.empty:
                    stock_data = df[df["代码"] == code]
                    if not stock_data.empty:
                        row = stock_data.iloc[0]
                        logger.debug(f"AkShare 获取实时行情成功 ({stock_code})")
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
            except Exception as e:
                logger.debug(f"AkShare 获取实时行情失败：{e}")

        # 4. 东方财富 API 降级
        return self._get_from_em_api(stock_code)

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

        数据源优先级：Tushare > Baostock > AkShare > 东方财富 API

        Args:
            stock_code: 股票代码
            period: 周期 (daily/weekly/monthly/1m/5m/15m/30m/60m)
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            limit: 数据条数限制

        Returns:
            DataFrame 包含 K 线数据
        """
        df = None

        # 1. 优先尝试 Tushare（仅支持日线/周线/月线）
        if self._tushare and self._tushare.is_available() and period in ["daily", "weekly", "monthly"]:
            try:
                ts_code = self._tushare._normalize_ts_code(stock_code)
                if period == "daily":
                    df = self._tushare.get_daily_kline(ts_code, start_date, end_date, limit)
                elif period == "weekly":
                    df = self._tushare.get_weekly_kline(ts_code, start_date, end_date, limit)
                elif period == "monthly":
                    df = self._tushare.get_monthly_kline(ts_code, start_date, end_date, limit)

                if df is not None and not df.empty:
                    logger.debug(f"Tushare 获取 {period}K 线成功 ({stock_code}): {len(df)} 条")
                    return self._standardize_columns(df)
            except Exception as e:
                logger.debug(f"Tushare 获取失败，尝试备用源：{e}")

        # 2. 尝试 Baostock
        if self._baostock and period in ["daily"]:
            try:
                df = self._get_from_baostock(stock_code, start_date, end_date, limit)
                if df is not None and not df.empty:
                    logger.debug(f"Baostock 获取 {period}K 线成功 ({stock_code}): {len(df)} 条")
                    return df
            except Exception as e:
                logger.debug(f"Baostock 获取失败，尝试备用源：{e}")

        # 3. 尝试 AkShare
        if self._akshare:
            try:
                code = self._normalize_code(stock_code)

                # 根据周期选择 API
                if period in ["1m", "5m", "15m", "30m", "60m"]:
                    df = self._get_minute_kline(code, period)
                else:
                    df = self._get_from_akshare(code, period, start_date, end_date, limit)

                if df is not None and not df.empty:
                    logger.debug(f"AkShare 获取 {period}K 线成功 ({stock_code}): {len(df)} 条")
                    return self._standardize_columns(df)
            except Exception as e:
                logger.debug(f"AkShare 获取失败，尝试备用源：{e}")

        # 4. 最后尝试：直接连接东方财富 API
        try:
            code = self._normalize_code(stock_code)
            df = self._fetch_from_em_api(code, start_date, end_date, limit)
            if df is not None and not df.empty:
                logger.debug(f"东方财富 API 获取 {period}K 线成功 ({stock_code}): {len(df)} 条")
                return self._standardize_columns(df)
        except Exception as e:
            logger.error(f"东方财富 API 获取失败：{e}")

        logger.warning(f"所有数据源获取失败：{stock_code} {period}")
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
            # Tushare 列名映射
            "vol": "volume",
            "trade_date": "trade_date",
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

    def _get_from_sina(self, stock_code: str) -> Optional[Dict]:
        """
        从新浪财经获取实时行情（优先级最高 - 最稳定）

        接口：http://hq.sinajs.cn/list=[市场前缀][股票代码]
        响应时间：100-300ms
        """
        try:
            import requests

            # 标准化股票代码
            code = self._normalize_code(stock_code)

            # 新浪财经前缀
            if code.startswith("6") or code.startswith("9"):
                symbol = f"sh{code}"
            else:
                symbol = f"sz{code}"

            url = f"http://hq.sinajs.cn/list={symbol}"
            headers = {
                "Referer": "http://finance.sina.com.cn/",
                "User-Agent": "Mozilla/5.0"
            }

            response = requests.get(url, headers=headers, timeout=5)
            response.raise_for_status()

            # 解析响应：var hq_str_sh000001="名称，开盘，昨收，当前，最高，最低，..."
            content = response.text.strip()
            if not content or "=" not in content:
                return None

            data_str = content.split("=")[1].strip().strip('"')
            elements = data_str.split(",")

            if len(elements) < 10 or elements[0] == "":
                return None

            name = elements[0]
            if not name:  # 名称为空说明停牌
                return None

            open_price = float(elements[1]) if elements[1] else 0
            pre_close = float(elements[2]) if elements[2] else 0
            current_price = float(elements[3]) if elements[3] else 0
            high = float(elements[4]) if elements[4] else 0
            low = float(elements[5]) if elements[5] else 0

            # 涨跌幅 = (当前 - 昨收) / 昨收 * 100
            change_pct = ((current_price - pre_close) / pre_close * 100) if pre_close else 0
            change_amount = current_price - pre_close

            # 成交量（股），成交额（元）
            volume = float(elements[8]) if elements[8] else 0
            amount = float(elements[9]) if elements[9] else 0

            return {
                "code": code,
                "name": name,
                "price": current_price,
                "change_pct": change_pct,
                "change_amount": change_amount,
                "open": open_price,
                "high": high,
                "low": low,
                "pre_close": pre_close,
                "volume": volume,
                "amount": amount,
                "timestamp": datetime.now(),
                "source": "新浪财经"
            }

        except Exception as e:
            logger.debug(f"新浪财经获取失败：{e}")
            return None

    def _get_from_tencent(self, stock_code: str) -> Optional[Dict]:
        """
        从腾讯财经获取实时行情（备用数据源）

        接口：http://qt.gtimg.cn/[市场前缀][股票代码]
        响应时间：150-400ms
        """
        try:
            import requests

            code = self._normalize_code(stock_code)

            # 腾讯财经前缀
            if code.startswith("6") or code.startswith("9"):
                symbol = f"sh{code}"
            else:
                symbol = f"sz{code}"

            url = f"http://qt.gtimg.cn/{symbol}"
            headers = {
                "Referer": "http://stockapp.finance.qq.com/",
                "User-Agent": "Mozilla/5.0"
            }

            response = requests.get(url, headers=headers, timeout=5)
            response.raise_for_status()

            # 解析响应：v_sh600000="51~浦发银行~600000~7.55~7.54~7.56..."
            content = response.text.strip()
            if not content or "=" not in content:
                return None

            data_str = content.split("=")[1].strip().strip('"')
            elements = data_str.split("~")

            if len(elements) < 10:
                return None

            name = elements[1]
            if not name:
                return None

            # 解析关键数据
            # 格式：f14(名称)~f3(当前价)~f4(昨收)~f5(开盘)~f6(最高)~f7(最低)
            current_price = float(elements[3]) if len(elements) > 3 and elements[3] else 0
            pre_close = float(elements[4]) if len(elements) > 4 and elements[4] else 0
            open_price = float(elements[5]) if len(elements) > 5 and elements[5] else 0
            high = float(elements[33]) if len(elements) > 33 and elements[33] else 0
            low = float(elements[34]) if len(elements) > 34 and elements[34] else 0

            # 如果高低收都是 0，尝试用开盘价
            if high == 0:
                high = float(elements[6]) if len(elements) > 6 and elements[6] else current_price
            if low == 0:
                low = float(elements[7]) if len(elements) > 7 and elements[7] else current_price

            # 涨跌幅 (腾讯直接提供)
            change_pct = float(elements[26]) if len(elements) > 26 and elements[26] else 0
            change_amount = current_price - pre_close

            # 成交量（手），成交额（万）
            volume = float(elements[6]) * 100 if len(elements) > 6 and elements[6] else 0  # 手转股
            amount = float(elements[37]) * 10000 if len(elements) > 37 and elements[37] else 0  # 万转元

            return {
                "code": code,
                "name": name,
                "price": current_price,
                "change_pct": change_pct,
                "change_amount": change_amount,
                "open": open_price,
                "high": high,
                "low": low,
                "pre_close": pre_close,
                "volume": volume,
                "amount": amount,
                "timestamp": datetime.now(),
                "source": "腾讯财经"
            }

        except Exception as e:
            logger.debug(f"腾讯财经获取失败：{e}")
            return None

    def _get_from_em_api(self, stock_code: str) -> Optional[Dict]:
        """
        从东方财富 API 获取实时行情（降级方案）
        """
        try:
            import requests

            code = self._normalize_code(stock_code)
            url = f"http://push2.eastmoney.com/api/qt/stock/get"
            params = {
                "secid": f"1.{code}" if code.startswith("6") else f"0.{code}",
                "fields": "f43,f44,f45,f46,f47,f119,f120,f121,f122,f124,f125,f126,f127,f128,f129,f130,f131,f132,f133,f134,f135,f136,f137,f138,f139,f140,f141,f142,f143,f144,f145,f146,f147,f148,f149,f150,f151,f152,f153,f154,f155,f156,f157,f158,f159,f160,f161,f162,f163,f164,f165,f166,f167,f168,f169,f170,f171,f172,f173,f174,f175,f176,f177,f178,f179,f180,f181,f182,f183,f184,f185,f186,f187,f188,f189,f190,f191,f192,f193,f194,f195,f196,f197,f198,f199,f200"
            }

            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()

            data = response.json()
            if data.get("data"):
                row = data["data"]
                return {
                    "code": code,
                    "name": row.get("f14", ""),
                    "price": float(row.get("f43", 0)) / 100 if row.get("f43") else 0,
                    "change_pct": float(row.get("f170", 0)) / 100 if row.get("f170") else 0,
                    "change_amount": float(row.get("f119", 0)) / 100 if row.get("f119") else 0,
                    "volume": float(row.get("f47", 0)) if row.get("f47") else 0,
                    "amount": float(row.get("f48", 0)) if row.get("f48") else 0,
                    "high": float(row.get("f46", 0)) / 100 if row.get("f46") else 0,
                    "low": float(row.get("f45", 0)) / 100 if row.get("f45") else 0,
                    "open": float(row.get("f44", 0)) / 100 if row.get("f44") else 0,
                    "pre_close": float(row.get("f60", 0)) / 100 if row.get("f60") else 0,
                    "timestamp": datetime.now(),
                    "source": "东方财富"
                }

            return None

        except Exception as e:
            logger.error(f"东方财富 API 获取实时行情失败：{e}")
            return None


__all__ = ["PriceCollector"]
