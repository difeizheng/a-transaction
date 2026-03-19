"""
系统导入测试脚本
运行此脚本验证所有模块是否可以正常导入
"""
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """测试所有模块导入"""
    print("测试模块导入...")
    print("=" * 50)

    modules = [
        # 配置
        ("src.config.settings", "配置模块"),
        # 工具
        ("src.utils.logger", "日志模块"),
        ("src.utils.db", "数据库模块"),
        ("src.utils.notification", "通知模块"),
        # 采集器
        ("src.collectors.news_collector", "新闻采集器"),
        ("src.collectors.price_collector", "行情采集器"),
        ("src.collectors.fund_collector", "资金采集器"),
        # 分析器
        ("src.analyzers.sentiment_analyzer", "情感分析器"),
        ("src.analyzers.technical_analyzer", "技术分析器"),
        ("src.analyzers.fund_analyzer", "资金分析器"),
        # 引擎
        ("src.engine.signal_fusion", "信号融合"),
        ("src.engine.decision_engine", "决策引擎"),
        ("src.engine.risk_manager", "风险管理"),
    ]

    passed = 0
    failed = 0

    for module_name, description in modules:
        try:
            __import__(module_name)
            print(f"[OK] {description}: {module_name}")
            passed += 1
        except Exception as e:
            print(f"[FAIL] {description}: {module_name}")
            print(f"  错误：{e}")
            failed += 1

    print("=" * 50)
    print(f"通过：{passed}, 失败：{failed}")

    if failed == 0:
        print("所有模块导入成功！")
    else:
        print("部分模块导入失败，请检查依赖安装。")

    return failed == 0


if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)
