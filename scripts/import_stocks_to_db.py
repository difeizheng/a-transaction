"""
股票基础数据导入脚本（增强版）

将 data/stocks/ 目录下的 CSV 股票列表导入到数据库 stocks 表中
支持：
- A 股完整行业分类（东方财富行业分类）
- 港股导入
- 自动识别 ST、科创板、北交所等
"""
import pandas as pd
import sqlite3
from pathlib import Path
import sys
from datetime import datetime
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.logger import get_logger
from src.config.industry_standard import get_industry_by_code

logger = get_logger(__name__)

DB_PATH = "data/trading.db"
STOCKS_CSV = "data/stocks/a_shares.csv"
HK_STOCKS_CSV = "data/stocks/hk_stocks.csv"
INDUSTRY_CSV = "data/stocks/stock_industry.csv"


def is_st_stock(name: str) -> bool:
    """判断是否为 ST 股票"""
    return "*ST" in name or "ST" in name


def is_kcb_stock(code: str) -> bool:
    """判断是否为科创板股票 (688xxx)"""
    return code.startswith("688")


def is_bse_stock(code: str) -> bool:
    """判断是否为北交所股票 (8xxxxx)"""
    return code.startswith("8") and len(code) == 6


def get_industry_mapping() -> Dict[str, str]:
    """
    获取东方财富行业分类映射

    使用东方财富行业分类标准
    来源：http://quote.eastmoney.com/center/gridlist.html#industry
    """
    # 东方财富行业分类（一级行业）
    industry_map = {
        # 金融行业
        "银行": ["银行", "国有大型银行", "股份制银行", "城商行", "农商行"],
        "证券": ["证券"],
        "保险": ["保险"],
        "多元金融": ["信托", "期货", "租赁", "资产管理"],

        # 周期行业
        "房地产": ["房地产开发", "房地产服务"],
        "建筑材料": ["水泥", "玻璃", "陶瓷", "其他建材"],
        "建筑装饰": ["房屋建设", "基础建设", "专业工程", "装修装饰"],
        "钢铁": ["钢铁"],
        "有色金属": ["工业金属", "贵金属", "稀有金属", "能源金属", "小金属"],
        "煤炭": ["煤炭"],
        "石油石化": ["石油开采", "石化工程", "炼油化工", "油品销售"],
        "基础化工": ["化学原料", "化学制品", "化学纤维", "塑料橡胶", "农药", "化肥"],

        # 制造业
        "汽车": ["汽车整车", "汽车零部件", "摩托车", "其他汽车"],
        "机械设备": ["通用机械", "专用机械", "仪器仪表", "金属制品", "设备"],
        "轻工制造": ["造纸", "包装", "家具", "文具用品", "其他轻工"],
        "纺织服饰": ["纺织", "服装", "鞋帽", "皮革"],
        "家用电器": ["白色家电", "黑色家电", "小家电"],
        "食品饮料": ["白酒", "啤酒", "饮料", "食品", "调味品"],
        "医药生物": ["化学制药", "中药", "生物制品", "医疗器械", "医疗服务"],
        "电力设备": ["电池", "光伏", "风电", "核电", "电网设备", "电机"],
        "电子": ["半导体", "元件", "光学光电子", "消费电子", "其他电子"],
        "计算机": ["计算机设备", "计算机软件", "IT 服务"],
        "通信": ["通信设备", "通信服务", "电信运营"],
        "传媒": ["游戏", "影视", "广告", "出版", "互联网传媒"],

        # 消费行业
        "商贸零售": ["百货", "超市", "专业零售", "电商"],
        "社会服务": ["餐饮", "酒店", "旅游", "教育", "人力", "美容护理"],
        "农林牧渔": ["农业", "林业", "畜牧业", "渔业", "饲料", "农产品加工"],

        # 其他行业
        "交通运输": ["铁路", "公路", "港口", "航运", "航空", "物流"],
        "公用事业": ["电力", "燃气", "水务", "环保"],
        "综合": ["综合"],
    }

    return industry_map


def load_industry_data() -> Dict[str, str]:
    """
    获取行业分类数据

    优先使用本地行业分类标准，网络接口作为备用

    Returns:
        股票代码->行业的映射字典
    """
    industry_mapping = {}

    # 方法 1: 使用本地行业分类标准
    try:
        from src.config.industry_standard import INDUSTRY_STANDARD

        for industry, data in INDUSTRY_STANDARD.items():
            if "codes" in data and data["codes"]:
                for code in data["codes"]:
                    industry_mapping[code] = industry

        if industry_mapping:
            logger.info(f"从本地标准加载 {len(industry_mapping)} 只股票的行业分类")

    except Exception as e:
        logger.warning(f"加载本地行业分类失败：{e}")

    # 方法 2: 尝试获取东方财富行业数据（网络）
    try:
        import akshare as ak

        industry_list = ak.stock_board_industry_name_em()

        if industry_list is not None and not industry_list.empty:
            logger.info(f"获取到 {len(industry_list)} 个行业板块")

            online_count = 0
            for _, row in industry_list.iterrows():
                board_name = row.get("板块名称", "")

                try:
                    stocks_df = ak.stock_board_industry_cons_em(symbol=board_name)

                    if stocks_df is not None and not stocks_df.empty:
                        for _, stock_row in stocks_df.iterrows():
                            code = str(stock_row.get("代码", "")).zfill(6)
                            if code and code not in industry_mapping:
                                industry_mapping[code] = board_name
                                online_count += 1
                except Exception as e:
                    logger.debug(f"获取行业 {board_name} 成分股失败：{e}")
                    continue

            logger.info(f"从东方财富补充 {online_count} 只股票的行业分类")

    except Exception as e:
        logger.debug(f"获取东方财富行业数据失败：{e}")

    return industry_mapping


def get_simplified_industry(name: str) -> str:
    """
    根据股票名称获取简化行业分类（备用方案）

    Args:
        name: 股票名称

    Returns:
        行业名称
    """
    industry_keywords = {
        "银行": ["银行"],
        "证券": ["证券", "券商"],
        "保险": ["保险"],
        "房地产": ["地产", "置业", "物业"],
        "医药生物": ["医药", "药业", "生物", "医疗", "制药"],
        "计算机": ["计算机", "软件", "信息", "网络", "系统"],
        "电子": ["电子", "微电子", "光电"],
        "通信": ["通信", "电信"],
        "汽车": ["汽车", "车辆", "摩托"],
        "机械设备": ["机械", "设备", "机床", "机器人"],
        "电力设备": ["电气", "电力", "电池", "光伏", "风电", "核电"],
        "有色金属": ["有色", "金属", "铜", "铝", "金", "银", "锂", "钴"],
        "钢铁": ["钢铁", "钢材"],
        "煤炭": ["煤炭", "焦煤"],
        "石油石化": ["石油", "石化", "油气"],
        "基础化工": ["化工", "化学", "化肥", "农药", "塑料", "橡胶"],
        "建筑材料": ["建材", "水泥", "玻璃", "陶瓷", "防水"],
        "建筑装饰": ["建筑", "装饰", "工程", "建设"],
        "轻工制造": ["造纸", "包装", "家具", "文具", "轻工"],
        "纺织服饰": ["纺织", "服装", "服饰", "鞋帽", "皮革"],
        "家用电器": ["家电", "电器"],
        "食品饮料": ["食品", "饮料", "白酒", "啤酒", "调味品", "乳品"],
        "农林牧渔": ["农业", "林业", "畜牧", "渔业", "饲料", "粮油"],
        "交通运输": ["铁路", "公路", "港口", "航运", "航空", "物流"],
        "公用事业": ["电力", "燃气", "水务", "环保", "能源"],
        "商贸零售": ["百货", "超市", "零售", "贸易", "商业"],
        "社会服务": ["餐饮", "酒店", "旅游", "教育", "美容", "人力"],
        "传媒": ["传媒", "游戏", "影视", "广告", "出版", "互联网"],
        "综合": ["综合"],
    }

    for industry, keywords in industry_keywords.items():
        if any(kw in name for kw in keywords):
            return industry

    return ""


def import_a_shares():
    """导入 A 股数据（带完整行业分类）"""
    logger.info("开始导入 A 股数据...")

    if not Path(STOCKS_CSV).exists():
        logger.error(f"文件不存在：{STOCKS_CSV}")
        return 0

    df = pd.read_csv(STOCKS_CSV)
    logger.info(f"读取 CSV，共 {len(df)} 条记录")

    # 尝试获取东方财富行业数据
    industry_data = load_industry_data()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    inserted = 0
    updated = 0
    skipped = 0

    for _, row in df.iterrows():
        code = str(row.get("code", "")).zfill(6)
        name = row.get("name", "")
        market = row.get("market", "")

        if not code or not name:
            skipped += 1
            continue

        # 计算衍生字段
        is_st = is_st_stock(name)
        is_kcb = is_kcb_stock(code)
        is_bse = is_bse_stock(code)

        # 获取行业 - 优先使用传入的行业映射
        industry = industry_data.get(code, "")
        if not industry:
            # 尝试使用本地行业分类标准
            industry = get_industry_by_code(code)
        if not industry:
            # 备用：根据名称判断
            industry = get_simplified_industry(name)

        try:
            # 尝试更新
            cursor.execute("""
                UPDATE stocks
                SET name=?, market=?, industry=?, is_st=?, is_kcb=?, updated_at=?
                WHERE code=?
            """, (name, market, industry, is_st, is_kcb, datetime.now(), code))

            if cursor.rowcount > 0:
                updated += 1
            else:
                # 插入新记录
                cursor.execute("""
                    INSERT INTO stocks (code, name, market, industry, is_st, is_kcb)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (code, name, market, industry, is_st, is_kcb))
                inserted += 1

        except Exception as e:
            logger.warning(f"导入失败 {code}: {e}")
            skipped += 1

    conn.commit()
    conn.close()

    logger.info(f"A 股导入完成：新增 {inserted} 条，更新 {updated} 条，跳过 {skipped} 条")
    return inserted + updated


def import_hk_stocks():
    """导入港股数据"""
    logger.info("开始导入港股数据...")

    if not Path(HK_STOCKS_CSV).exists():
        logger.warning(f"港股文件不存在：{HK_STOCKS_CSV}")
        return 0

    df = pd.read_csv(HK_STOCKS_CSV)
    logger.info(f"读取 CSV，共 {len(df)} 条记录")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    inserted = 0
    updated = 0
    skipped = 0

    for _, row in df.iterrows():
        code = str(row.get("code", "")).zfill(5)
        name = row.get("name", "")
        market = "HK"
        stock_type = row.get("type", "港股")

        if not code or not name:
            skipped += 1
            continue

        # 港股行业分类（简化）
        industry = get_hk_industry(name)

        try:
            cursor.execute("""
                UPDATE stocks
                SET name=?, market=?, industry=?, is_st=?, is_kcb=?, updated_at=?
                WHERE code=?
            """, (name, market, industry, False, False, datetime.now(), code))

            if cursor.rowcount > 0:
                updated += 1
            else:
                cursor.execute("""
                    INSERT INTO stocks (code, name, market, industry, is_st, is_kcb)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (code, name, market, industry, False, False))
                inserted += 1

        except Exception as e:
            logger.warning(f"导入失败 {code}: {e}")
            skipped += 1

    conn.commit()
    conn.close()

    logger.info(f"港股导入完成：新增 {inserted} 条，更新 {updated} 条，跳过 {skipped} 条")
    return inserted + updated


def get_hk_industry(name: str) -> str:
    """
    根据港股名称判断行业（简化版）

    Args:
        name: 股票名称

    Returns:
        行业名称
    """
    industry_keywords = {
        "金融": ["银行", "证券", "保险", "金融", "信托"],
        "房地产": ["地产", "置业", "物业", "实业"],
        "科技": ["科技", "软件", "信息", "网络", "智能", "芯片", "半导体"],
        "医药": ["医药", "药业", "生物", "医疗", "健康"],
        "消费": ["消费", "食品", "饮料", "酒", "餐饮", "零售", "服装"],
        "工业": ["工业", "制造", "机械", "设备", "工程"],
        "能源": ["能源", "石油", "天然气", "化工", "资源"],
        "电信": ["通信", "电信", "移动"],
        "公用事业": ["电力", "燃气", "水务"],
        "交通运输": ["运输", "物流", "港口", "航运", "航空"],
        "互联网": ["互联网", "游戏", "电商", "科技"],
    }

    for industry, keywords in industry_keywords.items():
        if any(kw in name for kw in keywords):
            return industry

    return ""


def verify_import():
    """验证导入结果"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("\n" + "=" * 50)
    print("数据库股票统计")
    print("=" * 50)

    # 总数
    cursor.execute("SELECT COUNT(*) FROM stocks")
    total = cursor.fetchone()[0]
    print(f"总股票数：{total:,}")

    # 按市场统计
    cursor.execute("SELECT market, COUNT(*) FROM stocks GROUP BY market")
    by_market = cursor.fetchall()
    print("\n按市场分布:")
    for market, count in by_market:
        print(f"  {market or '未知'}: {count:,}")

    # ST 股票
    cursor.execute("SELECT COUNT(*) FROM stocks WHERE is_st = 1")
    st_count = cursor.fetchone()[0]
    print(f"\nST 股票：{st_count:,}")

    # 科创板
    cursor.execute("SELECT COUNT(*) FROM stocks WHERE is_kcb = 1")
    kcb_count = cursor.fetchone()[0]
    print(f"科创板：{kcb_count:,}")

    # 行业分布
    cursor.execute("""
        SELECT industry, COUNT(*) as cnt
        FROM stocks
        WHERE industry != ''
        GROUP BY industry
        ORDER BY cnt DESC
        LIMIT 15
    """)
    by_industry = cursor.fetchall()
    print("\n行业分布 (Top 15):")
    for industry, count in by_industry:
        print(f"  {industry}: {count:,}")

    # 示例数据
    print("\n前 10 条记录:")
    cursor.execute("SELECT code, name, market, industry, is_st, is_kcb FROM stocks LIMIT 10")
    for row in cursor.fetchall():
        st_flag = "ST" if row[4] else ""
        kcb_flag = "科创板" if row[5] else ""
        flags = " ".join(filter(None, [st_flag, kcb_flag]))
        print(f"  {row[0]} {row[1]} {row[2]} {row[3]} {flags}")

    conn.close()


def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("股票基础数据导入（增强版）")
    logger.info("=" * 50)

    # 导入 A 股（带完整行业分类）
    a_count = import_a_shares()

    # 导入港股
    hk_count = import_hk_stocks()

    # 验证
    verify_import()

    logger.info("=" * 50)
    logger.info(f"导入完成！总计：{a_count + hk_count:,} 条")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
