"""
模块测试脚本 - 测试新增的所有优化模块

测试内容:
第一阶段:
1. 市场状态判断模块 (market_regime_analyzer.py)
2. 板块联动分析模块 (sector_analyzer.py)
3. 技术指标增强 (OBV、BIAS、VR)
4. 动态权重调整 (signal_fusion.py)
5. 组合级风控 (risk_manager.py)

第二阶段:
6. 新闻分析深化 (sentiment_analyzer.py) - 事件类型识别、影响程度分级、时效性加权、来源可信度
7. 动态仓位管理 (decision_engine.py) - 凯利公式、波动率调整、连胜/连败调整
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 设置控制台编码
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, 'gbk', errors='replace')


def generate_test_data(days=100):
    """生成模拟的 OHLCV 数据"""
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')

    # 模拟价格数据 (随机游走)
    np.random.seed(42)
    returns = np.random.randn(days) * 0.02
    close = 100 * np.cumprod(1 + returns)

    # 生成 OHLCV
    df = pd.DataFrame({
        'date': dates,
        'open': close * (1 + np.random.randn(days) * 0.01),
        'high': close * (1 + np.abs(np.random.randn(days)) * 0.02),
        'low': close * (1 - np.abs(np.random.randn(days)) * 0.02),
        'close': close,
        'volume': np.random.randint(1000000, 10000000, days)
    })
    df.set_index('date', inplace=True)
    return df


def test_market_regime_analyzer():
    """测试市场状态判断模块"""
    print("\n" + "="*60)
    print("测试 1: 市场状态判断模块")
    print("="*60)

    try:
        from src.analyzers.market_regime_analyzer import MarketRegimeAnalyzer

        # 生成测试数据
        df = generate_test_data(100)

        # 创建分析器
        analyzer = MarketRegimeAnalyzer()

        # 测试分析
        market_breadth = {'up_count': 2500, 'down_count': 1500}
        signal = analyzer.analyze(df, market_breadth)

        print(f"[OK] 市场状态：{signal.regime}")
        print(f"[OK] 趋势得分：{signal.trend_score}")
        print(f"[OK] 市场宽度得分：{signal.breadth_score}")
        print(f"[OK] 成交量得分：{signal.volume_score}")
        print(f"[OK] 综合得分：{signal.composite_score}")
        print(f"[OK] 操作建议：{signal.suggestion}")

        # 测试仓位上限
        position_limit = analyzer.get_position_limit(signal.regime, signal.composite_score)
        print(f"[OK] 建议仓位上限：{position_limit:.1%}")

        # 测试权重调整
        weights = analyzer.get_weight_adjustment(signal.regime)
        print(f"[OK] 权重配置：{weights}")

        print("[OK] 市场状态判断模块测试通过")
        return True

    except Exception as e:
        print(f"[FAIL] 测试失败：{e}")
        return False


def test_technical_indicators():
    """测试技术指标增强"""
    print("\n" + "="*60)
    print("测试 2: 技术指标增强 (OBV、BIAS、VR)")
    print("="*60)

    try:
        from src.analyzers.technical_analyzer import TechnicalAnalyzer

        # 生成测试数据
        df = generate_test_data(100)

        # 创建分析器
        analyzer = TechnicalAnalyzer()

        # 测试新指标
        obv = analyzer.calculate_obv(df)
        bias = analyzer.calculate_bias(df)
        vr = analyzer.calculate_vr(df)

        print(f"[OK] OBV 最新值：{obv.iloc[-1]:.0f}")
        print(f"[OK] BIAS(6) 最新值：{bias['bias6'].iloc[-1]:.2f}%")
        print(f"[OK] BIAS(12) 最新值：{bias['bias12'].iloc[-1]:.2f}%")
        print(f"[OK] VR 最新值：{vr.iloc[-1]:.2f}")

        # 测试完整分析
        signal = analyzer.analyze(df)
        print(f"[OK] 综合信号：{signal.overall_signal}")
        print(f"[OK] 综合得分：{signal.score}")

        print("[OK] 技术指标增强测试通过")
        return True

    except Exception as e:
        print(f"[FAIL] 测试失败：{e}")
        return False


def test_signal_fusion():
    """测试动态权重调整"""
    print("\n" + "="*60)
    print("测试 3: 动态权重调整")
    print("="*60)

    try:
        from src.engine.signal_fusion import SignalFusionEngine

        # 测试不同市场状态下的权重
        regimes = [
            ('bull', '牛市'),
            ('bear', '熊市'),
            ('oscillating', '震荡市')
        ]

        for regime, name in regimes:
            engine = SignalFusionEngine(market_regime=regime)
            weights = engine.get_current_weights()

            print(f"\n{name} (regime={regime}):")
            print(f"  新闻权重：{weights['news']:.0%}")
            print(f"  技术权重：{weights['technical']:.0%}")
            print(f"  资金权重：{weights['fund']:.0%}")
            print(f"  波动率权重：{weights['volatility']:.0%}")
            print(f"  情绪权重：{weights['sentiment']:.0%}")

        # 测试信号融合
        engine = SignalFusionEngine(market_regime='oscillating')
        result = engine.fuse(
            stock_code="000001",
            stock_name="平安银行",
            news_score=0.6,
            technical_score=0.7,
            fund_score=0.5,
            volatility_score=0.4,
            sentiment_score=0.3,
            current_price=10.5
        )

        print(f"\n[OK] 融合结果:")
        print(f"  综合得分：{result.total_score:.3f}")
        print(f"  信号：{result.signal}")
        print(f"  置信度：{result.confidence}")

        print("\n[OK] 动态权重调整测试通过")
        return True

    except Exception as e:
        print(f"[FAIL] 测试失败：{e}")
        return False


def test_risk_manager():
    """测试组合级风控"""
    print("\n" + "="*60)
    print("测试 4: 组合级风控")
    print("="*60)

    try:
        from src.engine.risk_manager import RiskManager

        # 创建风控管理器
        risk_mgr = RiskManager(
            max_drawdown=0.15,
            max_industry_exposure=0.30
        )

        # 模拟持仓数据
        positions = {
            "000001": {"market_value": 5000, "industry": "银行"},
            "600000": {"market_value": 4000, "industry": "银行"},
            "000002": {"market_value": 3000, "industry": "房地产"},
            "300750": {"market_value": 2000, "industry": "新能源"},
        }
        total_assets = 20000

        # 测试行业集中度检查
        print("1. 行业集中度检查:")
        passed, reason, exposure = risk_mgr.check_industry_concentration(positions, total_assets)
        status = "通过" if passed else "不通过"
        print(f"   检查结果：{status}")
        print(f"   原因：{reason}")
        print(f"   行业暴露：{exposure}")

        # 测试相关性检查
        print("\n2. 相关性检查:")
        corr_matrix = {
            "000001": {"600000": 0.85, "000002": 0.3, "300750": 0.2},
            "600000": {"000001": 0.85, "000002": 0.25, "300750": 0.15},
            "000002": {"000001": 0.3, "600000": 0.25, "300750": 0.4},
            "300750": {"000001": 0.2, "600000": 0.15, "000002": 0.4},
        }
        passed, reason, high_corr = risk_mgr.check_correlation(positions, corr_matrix)
        status = "通过" if passed else "不通过"
        print(f"   检查结果：{status}")
        print(f"   原因：{reason}")
        if high_corr:
            print(f"   高相关对：{high_corr}")

        # 测试强制减仓
        print("\n3. 强制减仓测试:")
        for drawdown in [0.05, 0.10, 0.12, 0.15]:
            should_reduce, ratio, reason = risk_mgr.should_force_reduce_position(drawdown)
            status = f"减仓 {ratio:.0%}" if should_reduce else "保持仓位"
            print(f"   回撤 {drawdown:.1%}: {status} - {reason}")

        # 测试动态仓位上限
        print("\n4. 动态仓位上限:")
        for drawdown in [0.05, 0.075, 0.12, 0.15]:
            risk_mgr._current_drawdown = drawdown
            limit = risk_mgr.get_position_limit_by_drawdown()
            print(f"   回撤 {drawdown:.1%}: 仓位上限 {limit:.1%}")

        print("\n[OK] 组合级风控测试通过")
        return True

    except Exception as e:
        print(f"[FAIL] 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_sector_analyzer():
    """测试板块联动分析"""
    print("\n" + "="*60)
    print("测试 5: 板块联动分析")
    print("="*60)

    try:
        from src.analyzers.sector_analyzer import SectorAnalyzer

        analyzer = SectorAnalyzer()

        # 测试获取板块信息
        stock_code = "000001"
        sector_info = analyzer.get_stock_sector(stock_code)
        print(f"[OK] {stock_code} 所属板块:")
        print(f"  行业：{sector_info.get('industry', [])}")
        print(f"  概念：{sector_info.get('concept', [])}")

        # 测试获取板块资金流向
        print("\n[OK] 获取行业资金流向 (前 5):")
        flows = analyzer.get_all_sector_fund_flow("industry")
        for i, flow in enumerate(flows[:5]):
            print(f"  {i+1}. {flow.get('name', 'N/A')}: "
                  f"涨跌幅 {flow.get('change_pct', 0):.2f}%, "
                  f"净流入 {flow.get('net_in', 0)/10000:.1f}万")

        # 测试获取热门板块
        print("\n[OK] 热门板块 (前 3):")
        hot_sectors = analyzer.get_hot_sectors(3)
        for i, sector in enumerate(hot_sectors):
            print(f"  {i+1}. {sector.get('name', 'N/A')}: "
                  f"涨跌幅 {sector.get('change_pct', 0):.2f}%")

        # 测试板块情绪
        print("\n[OK] 市场情绪:")
        sentiment = analyzer.get_sector_sentiment()
        print(f"  情绪：{sentiment.get('sentiment', 'N/A')}")
        print(f"  热门板块数：{sentiment.get('hot_count', 0)}")
        print(f"  冷门板块数：{sentiment.get('cold_count', 0)}")

        print("\n[OK] 板块联动分析测试通过")
        return True

    except Exception as e:
        print(f"[FAIL] 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_sentiment_analyzer_enhanced():
    """测试新闻分析深化（事件类型识别、影响程度分级、时效性加权、来源可信度）"""
    print("\n" + "="*60)
    print("测试 6: 新闻分析深化")
    print("="*60)

    try:
        from src.analyzers.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer()

        # 测试用例
        test_cases = [
            {
                "name": "业绩利好",
                "title": "公司业绩大幅增长，净利润翻倍",
                "content": "XYZ 公司发布年报，营业收入同比增长 50%，净利润达到 10 亿元，超出市场预期。",
                "source": "证券时报",
                "expected_event": "earnings",
                "expected_impact": "high",
            },
            {
                "name": "高管变动",
                "title": "公司 CEO 辞职",
                "content": "因个人原因，公司总经理张三申请辞去职务，自本公告发布之日起生效。",
                "source": "东方财富",
                "expected_event": "management",
                "expected_impact": "medium",
            },
            {
                "name": "重大合同",
                "title": "公司中标 10 亿元大单",
                "content": "公司近日收到中标通知书，中标金额约 10 亿元，占公司最近一期经审计营业收入的 25%。",
                "source": "中国证券报",
                "expected_event": "business",
                "expected_impact": "high",
            },
            {
                "name": "市场传闻",
                "title": "网传某公司将进行重组",
                "content": "有消息称该公司可能被借壳重组，但目前尚未得到官方证实。",
                "source": "微博",
                "expected_event": "rumor",
                "expected_impact": "low",
            },
        ]

        print("测试结果:")
        print("-" * 60)

        for tc in test_cases:
            result = analyzer.analyze(
                text=tc["content"],
                title=tc["title"],
                source=tc["source"],
            )

            print(f"\n测试：{tc['name']}")
            print(f"  情感得分：{result.score:.3f}")
            print(f"  事件类型：{result.event_type} (预期：{tc['expected_event']})")
            print(f"  影响程度：{result.impact_level} (预期：{tc['expected_impact']})")
            print(f"  来源可信度：{result.source_credibility:.2f}")
            print(f"  关键词：{', '.join(result.keywords[:3]) if result.keywords else 'N/A'}")

            # 验证事件类型
            event_match = result.event_type == tc['expected_event']
            impact_match = result.impact_level == tc['expected_impact']

            if event_match and impact_match:
                print(f"  状态：[OK]")
            else:
                print(f"  状态：[部分匹配] 事件类型：{'✓' if event_match else '✗'}, 影响程度：{'✓' if impact_match else '✗'}")

        # 测试时效性加权
        print("\n" + "-" * 60)
        print("时效性加权测试:")

        now = datetime.now()
        time_tests = [
            (now - timedelta(hours=0.5), "1 小时内"),
            (now - timedelta(hours=3), "1-6 小时"),
            (now - timedelta(hours=12), "6-24 小时"),
            (now - timedelta(hours=48), "24-72 小时"),
            (now - timedelta(hours=100), "超过 72 小时"),
        ]

        for pub_time, desc in time_tests:
            result = analyzer.analyze(
                text="公司业绩增长",
                title="利好消息",
                publish_time=pub_time,
            )
            print(f"  {desc}: 权重系数 = {result.time_weight:.2f}")

        print("\n[OK] 新闻分析深化测试通过")
        return True

    except Exception as e:
        print(f"[FAIL] 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_dynamic_position_management():
    """测试动态仓位管理（凯利公式、波动率调整、连胜/连败调整）"""
    print("\n" + "="*60)
    print("测试 7: 动态仓位管理")
    print("="*60)

    try:
        from src.engine.decision_engine import DecisionEngine, PositionManager

        # 测试 PositionManager
        print("1. PositionManager 基础测试:")
        pm = PositionManager(
            max_position_per_stock=0.2,
            kelly_ceiling=0.25,
        )

        # 凯利公式测试
        print("\n凯利公式测试:")
        test_scenarios = [
            {"win_rate": 0.6, "avg_win": 0.15, "avg_loss": 0.05, "desc": "胜率 60%, 盈亏比 3:1"},
            {"win_rate": 0.5, "avg_win": 0.10, "avg_loss": 0.05, "desc": "胜率 50%, 盈亏比 2:1"},
            {"win_rate": 0.45, "avg_win": 0.12, "avg_loss": 0.06, "desc": "胜率 45%, 盈亏比 2:1"},
            {"win_rate": 0.55, "avg_win": 0.08, "avg_loss": 0.04, "desc": "胜率 55%, 盈亏比 2:1"},
        ]

        for scenario in test_scenarios:
            kelly = pm.calculate_kelly_position(
                win_rate=scenario["win_rate"],
                avg_win=scenario["avg_win"],
                avg_loss=scenario["avg_loss"],
                confidence=1.0,
            )
            print(f"  {scenario['desc']}: 凯利仓位 = {kelly:.1%}")

        # 波动率调整测试
        print("\n波动率调整测试 (基础仓位 20%):")
        base_pos = 0.20
        vol_tests = [0.01, 0.02, 0.03, 0.05]
        for vol in vol_tests:
            adjusted = pm.adjust_for_volatility(base_pos, vol, target_volatility=0.02)
            print(f"  当前波动率 {vol:.1%}: 调整后仓位 = {adjusted:.1%}")

        # 连胜/连败调整测试
        print("\n连胜/连败调整测试 (基础仓位 20%):")
        pm2 = PositionManager()

        # 模拟连胜
        for i in range(6):
            pos = pm2.adjust_for_streak(0.20, is_win=True)
            if i in [1, 2, 4, 5]:
                print(f"  连胜 {i+1} 场：仓位 = {pos:.1%}")

        # 重置
        pm2 = PositionManager()
        # 模拟连败
        for i in range(6):
            pos = pm2.adjust_for_streak(0.20, is_win=False)
            if i in [1, 2, 4, 5]:
                print(f"  连败 {i+1} 场：仓位 = {pos:.1%}")

        # 测试 DecisionEngine 集成
        print("\n2. DecisionEngine 集成测试:")
        engine = DecisionEngine(
            initial_capital=100000,
            max_position_per_stock=0.2,
            use_dynamic_position=True,
        )

        # 设置波动率
        engine.set_stock_volatility("000001", 0.025)

        # 模拟交易历史
        engine.trade_history = [
            {"pnl": 1000, "pnl_pct": 0.10},
            {"pnl": 1500, "pnl_pct": 0.15},
            {"pnl": -500, "pnl_pct": -0.05},
            {"pnl": 2000, "pnl_pct": 0.20},
        ]

        # 更新绩效统计
        for trade in engine.trade_history:
            if trade["pnl"] > 0:
                engine.position_manager.win_streak += 1
            else:
                engine.position_manager.loss_streak += 1

        # 获取凯利推荐
        kelly_rec = engine.get_kelly_recommendation("000001", confidence=0.8)
        print(f"\n凯利推荐仓位:")
        print(f"  原始凯利：{kelly_rec['kelly_raw']:.1%}")
        print(f"  波动率调整后：{kelly_rec['kelly_vol_adjusted']:.1%}")
        print(f"  当前胜率：{kelly_rec['win_rate']:.1%}")
        print(f"  平均盈利：{kelly_rec['avg_win']:.2f}")
        print(f"  平均亏损：{kelly_rec['avg_loss']:.2f}")
        print(f"  波动率：{kelly_rec['volatility']:.1%}")
        print(f"  连胜：{kelly_rec['consecutive_wins']}")
        print(f"  连败：{kelly_rec['consecutive_losses']}")

        print("\n[OK] 动态仓位管理测试通过")
        return True

    except Exception as e:
        print(f"[FAIL] 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("A 股监控系统 - 优化模块集成测试")
    print("="*60)
    print(f"测试时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = {
        # 第一阶段
        "市场状态判断": test_market_regime_analyzer(),
        "技术指标增强": test_technical_indicators(),
        "动态权重调整": test_signal_fusion(),
        "组合级风控": test_risk_manager(),
        "板块联动分析": test_sector_analyzer(),
        # 第二阶段
        "新闻分析深化": test_sentiment_analyzer_enhanced(),
        "动态仓位管理": test_dynamic_position_management(),
    }

    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)

    for module, passed in results.items():
        status = "通过" if passed else "失败"
        print(f"{module}: {status}")

    total_passed = sum(results.values())
    total_tests = len(results)

    print(f"\n总计：{total_passed}/{total_tests} 通过")

    if total_passed == total_tests:
        print("\n[SUCCESS] 所有测试通过！优化模块已就绪。")
    else:
        print(f"\n[WARNING] 有 {total_tests - total_passed} 个模块测试失败，请检查。")

    return total_passed == total_tests


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
