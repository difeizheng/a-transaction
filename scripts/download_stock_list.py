"""
下载 A 股和港股股票基础数据

获取所有股票代码、名称、市场等基本信息，保存到本地 CSV 文件
"""
import pandas as pd
import akshare as ak
from datetime import datetime
from pathlib import Path
import sys

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.logger import get_logger

logger = get_logger(__name__)

# 输出目录
OUTPUT_DIR = Path("data/stocks")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def download_a_shares():
    """
    下载 A 股所有股票列表
    使用 Baostock 为主接口（更稳定）

    Returns:
        DataFrame: A 股股票列表
    """
    logger.info("正在下载 A 股股票列表...")

    # 方法 1: 使用 Baostock
    try:
        import baostock as bs
        bs.login()
        logger.info("Baostock 登录成功")

        # 查询沪深 A 股基本资料
        rs = bs.query_all_stock(day=datetime.now().strftime("%Y-%m-%d"))

        if rs.error_code == "0":
            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())

            if data_list:
                df = pd.DataFrame(data_list, columns=rs.fields)
                logger.info(f"Baostock 获取成功，原始数据条数：{len(df)}")

                # 过滤 A 股
                stocks = []
                for _, row in df.iterrows():
                    code = row.get("code", "")
                    name = row.get("code_name", "")
                    ipo_date = row.get("ipoDate", "")

                    # 跳过已退市
                    if row.get("isRetire") == "1":
                        continue

                    # 判断市场
                    if code.startswith("6"):
                        market = "SH"
                    elif code.startswith(("0", "3")):
                        market = "SZ"
                    else:
                        continue  # 跳过其他市场

                    if code and name:
                        stocks.append({
                            "code": code,
                            "name": name,
                            "market": market,
                            "type": "A 股",
                            "latest_price": 0,
                            "change_pct": 0,
                            "volume": 0,
                            "amount": 0,
                            "market_cap": 0,
                            "pe_ratio": 0,
                            "pb_ratio": 0,
                        })

                logger.info(f"A 股股票数量：{len(stocks)}")
                bs.logout()
                return pd.DataFrame(stocks)

        bs.logout()
        logger.warning("Baostock 获取数据为空")

    except ImportError:
        logger.warning("Baostock 未安装，尝试其他接口")
    except Exception as e:
        logger.warning(f"Baostock 失败：{e}")

    # 方法 2: 使用 AkShare 东方财富接口
    try:
        logger.info("尝试使用东方财富接口...")
        df = ak.stock_zh_a_spot_em()

        if df is not None and not df.empty:
            stocks = []
            for _, row in df.iterrows():
                code = row.get("代码", "")
                name = row.get("名称", "")

                if code.startswith("6"):
                    market = "SH"
                elif code.startswith(("0", "3")):
                    market = "SZ"
                else:
                    continue

                stocks.append({
                    "code": code,
                    "name": name,
                    "market": market,
                    "type": "A 股",
                    "latest_price": float(row.get("最新价", 0)) if row.get("最新价") else 0,
                    "change_pct": float(row.get("涨跌幅", 0)) if row.get("涨跌幅") else 0,
                    "volume": float(row.get("成交量", 0)) if row.get("成交量") else 0,
                    "amount": float(row.get("成交额", 0)) if row.get("成交额") else 0,
                    "market_cap": float(row.get("总市值", 0)) if row.get("总市值") else 0,
                    "pe_ratio": float(row.get("市盈率 - 动态", 0)) if row.get("市盈率 - 动态") else 0,
                    "pb_ratio": float(row.get("市净率", 0)) if row.get("市净率") else 0,
                })

            result_df = pd.DataFrame(stocks)
            logger.info(f"A 股股票数量：{len(result_df)}")
            return result_df
    except Exception as e:
        logger.error(f"东方财富接口失败：{e}")

    # 方法 3: 使用 AkShare 股票名称接口
    try:
        logger.info("尝试使用 stock_info_a_code_name 接口...")
        df = ak.stock_info_a_code_name()

        if df is not None and not df.empty:
            stocks = []
            for _, row in df.iterrows():
                code = row.get("code", "") if "code" in row else row.get("股票代码", "")
                name = row.get("name", "") if "name" in row else row.get("股票简称", "")

                if code:
                    if str(code).startswith("6"):
                        market = "SH"
                    elif str(code).startswith(("0", "3")):
                        market = "SZ"
                    else:
                        continue

                    stocks.append({
                        "code": str(code).zfill(6),
                        "name": name,
                        "market": market,
                        "type": "A 股",
                        "latest_price": 0,
                        "change_pct": 0,
                        "volume": 0,
                        "amount": 0,
                        "market_cap": 0,
                        "pe_ratio": 0,
                        "pb_ratio": 0,
                    })

            logger.info(f"使用备用接口获取成功，股票数量：{len(stocks)}")
            return pd.DataFrame(stocks)
    except Exception as e:
        logger.error(f"备用接口失败：{e}")

    return None


def download_hk_stocks():
    """
    下载港股所有股票列表

    Returns:
        DataFrame: 港股股票列表
    """
    logger.info("正在下载港股股票列表...")

    # 方法 1: 使用 AkShare 港股实时行情 - 多次重试
    retry_count = 5
    for i in range(retry_count):
        try:
            logger.info(f"尝试东方财富接口 (第 {i+1}/{retry_count} 次)...")
            df = ak.stock_hk_spot_em()

            if df is not None and not df.empty:
                stocks = []
                for _, row in df.iterrows():
                    code = row.get("代码", "")
                    name = row.get("名称", "")

                    stocks.append({
                        "code": code,
                        "name": name,
                        "market": "HK",
                        "type": "港股",
                        "latest_price": float(row.get("最新价", 0)) if row.get("最新价") else 0,
                        "change_pct": float(row.get("涨跌幅", 0)) if row.get("涨跌幅") else 0,
                        "volume": float(row.get("成交量", 0)) if row.get("成交量") else 0,
                        "amount": float(row.get("成交额", 0)) if row.get("成交额") else 0,
                        "market_cap": float(row.get("市值", 0)) if row.get("市值") else 0,
                        "pe_ratio": float(row.get("市盈率", 0)) if row.get("市盈率") else 0,
                        "pb_ratio": float(row.get("市净率", 0)) if row.get("市净率") else 0,
                    })

                result_df = pd.DataFrame(stocks)
                logger.info(f"港股股票数量：{len(result_df)}")
                return result_df

        except Exception as e:
            logger.warning(f"东方财富接口失败 (第 {i+1} 次): {e}")
            if i < retry_count - 1:
                import time
                time.sleep(3)

    # 方法 2: 使用 AkShare 港股通成分股
    try:
        logger.info("尝试使用 stock_hk_ggt_components_em 接口 (港股通)...")
        df = ak.stock_hk_ggt_components_em()

        if df is not None and not df.empty:
            stocks = []
            for _, row in df.iterrows():
                code = row.get("代码", "") if "代码" in row else ""
                name = row.get("名称", "") if "名称" in row else ""
                if code:
                    stocks.append({
                        "code": str(code).zfill(5),
                        "name": name,
                        "market": "HK",
                        "type": "港股通",
                        "latest_price": 0,
                        "change_pct": 0,
                        "volume": 0,
                        "amount": 0,
                        "market_cap": 0,
                        "pe_ratio": 0,
                        "pb_ratio": 0,
                    })
            logger.info(f"使用港股通接口获取成功，股票数量：{len(stocks)}")
            return pd.DataFrame(stocks)
    except Exception as e:
        logger.warning(f"港股通接口失败：{e}")

    logger.warning("所有港股接口均失败，跳过港股下载")
    return None


def download_index_stocks():
    """
    下载主要指数成分股

    Returns:
        dict: 各指数成分股 DataFrame
    """
    logger.info("正在下载指数成分股...")

    indices = {
        "000300": "沪深 300",
        "000001": "上证指数",
        "000016": "上证 50",
        "000905": "中证 500",
        "399001": "深证成指",
        "399006": "创业板指",
    }

    result = {}

    try:
        for index_code, index_name in indices.items():
            try:
                df = ak.index_stock_cons(symbol=index_code)
                if df is not None and not df.empty:
                    result[index_code] = {
                        "name": index_name,
                        "data": df
                    }
                    logger.info(f"{index_name} 成分股数量：{len(df)}")
            except Exception as e:
                logger.warning(f"下载 {index_name} 成分股失败：{e}")

    except Exception as e:
        logger.error(f"下载指数成分股失败：{e}")

    return result


def save_to_csv(df: pd.DataFrame, filename: str):
    """保存 DataFrame 到 CSV"""
    output_path = OUTPUT_DIR / filename
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    logger.info(f"已保存到：{output_path}")


def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("开始下载股票基础数据")
    logger.info("=" * 50)

    start_time = datetime.now()

    # 下载 A 股
    a_shares_df = download_a_shares()
    if a_shares_df is not None:
        save_to_csv(a_shares_df, "a_shares.csv")

    # 下载港股
    hk_stocks_df = download_hk_stocks()
    if hk_stocks_df is not None:
        save_to_csv(hk_stocks_df, "hk_stocks.csv")

    # 下载指数成分股
    indices_data = download_index_stocks()
    for index_code, data in indices_data.items():
        if data["data"] is not None:
            save_to_csv(data["data"], f"index_{index_code}.csv")

    # 创建合并文件
    if a_shares_df is not None or hk_stocks_df is not None:
        all_stocks = []

        if a_shares_df is not None:
            # A 股简化版
            a_simple = a_shares_df[["code", "name", "market", "type"]].copy()
            all_stocks.append(a_simple)

        if hk_stocks_df is not None:
            # 港股简化版
            h_simple = hk_stocks_df[["code", "name", "market", "type"]].copy()
            all_stocks.append(h_simple)

        if all_stocks:
            combined_df = pd.concat(all_stocks, ignore_index=True)
            save_to_csv(combined_df, "all_stocks_basic.csv")
            logger.info(f"合并股票总数：{len(combined_df)}")

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    logger.info("=" * 50)
    logger.info(f"下载完成！耗时：{duration:.2f} 秒")
    logger.info(f"输出目录：{OUTPUT_DIR.absolute()}")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
