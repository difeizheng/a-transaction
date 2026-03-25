"""
下载港股股票列表

使用 AkShare 东方财富接口获取港股数据
"""
import pandas as pd
from pathlib import Path
import sys
import time
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.logger import get_logger

logger = get_logger(__name__)

OUTPUT_DIR = Path("data/stocks")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
HK_CSV = OUTPUT_DIR / "hk_stocks.csv"


def download_hk_stocks():
    """
    下载港股所有股票列表

    多种接口尝试：
    1. stock_hk_spot_em - 港股实时行情
    2. stock_hk_ggt_components_em - 港股通成分股
    """
    logger.info("开始下载港股数据...")

    # 方法 1: 东方财富港股实时行情 - 多次重试
    retry_count = 5
    for i in range(retry_count):
        try:
            logger.info(f"尝试东方财富接口 (第 {i+1}/{retry_count} 次)...")
            import akshare as ak

            df = ak.stock_hk_spot_em()

            if df is not None and not df.empty:
                logger.info(f"成功获取 {len(df)} 只港股")

                stocks = []
                for _, row in df.iterrows():
                    code = str(row.get("代码", "")).zfill(5)
                    name = row.get("名称", "")
                    if code and name:
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
                        })

                result_df = pd.DataFrame(stocks)
                result_df.to_csv(HK_CSV, index=False, encoding="utf-8-sig")
                logger.info(f"已保存到：{HK_CSV}")
                return len(stocks)

        except Exception as e:
            logger.warning(f"东方财富接口失败 (第 {i+1} 次): {e}")
            if i < retry_count - 1:
                time.sleep(5)

    # 方法 2: 港股通成分股
    try:
        logger.info("尝试港股通成分股接口...")
        import akshare as ak

        df = ak.stock_hk_ggt_components_em()

        if df is not None and not df.empty:
            logger.info(f"成功获取 {len(df)} 只港股通股票")

            stocks = []
            for _, row in df.iterrows():
                code = str(row.get("代码", "")).zfill(5)
                name = row.get("名称", "")
                if code and name:
                    stocks.append({
                        "code": code,
                        "name": name,
                        "market": "HK",
                        "type": "港股通",
                    })

            result_df = pd.DataFrame(stocks)
            result_df.to_csv(HK_CSV, index=False, encoding="utf-8-sig")
            logger.info(f"已保存到：{HK_CSV}")
            return len(stocks)

    except Exception as e:
        logger.error(f"港股通接口失败：{e}")

    logger.error("所有接口均失败")
    return 0


def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("港股数据下载")
    logger.info("=" * 50)

    count = download_hk_stocks()

    logger.info("=" * 50)
    if count > 0:
        logger.info(f"下载成功！共 {count} 只港股")
    else:
        logger.info("下载失败，请检查网络连接后重试")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
