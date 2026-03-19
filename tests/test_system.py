"""
系统测试模块
"""
import pytest
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestConfig:
    """配置模块测试"""

    def test_config_load(self):
        """测试配置加载"""
        from src.config.settings import load_config

        config = load_config("config.yaml")
        assert config is not None
        assert config.monitor_interval > 0
        assert config.news_weight + config.technical_weight + config.fund_weight + config.sentiment_weight == 1.0


class TestSentimentAnalyzer:
    """情感分析器测试"""

    def test_positive_news(self):
        """测试利好新闻分析"""
        from src.analyzers.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer(model="rule")
        result = analyzer.analyze("公司业绩大幅增长，净利润翻倍")

        assert result.score > 0
        assert result.label == "positive"

    def test_negative_news(self):
        """测试利空新闻分析"""
        from src.analyzers.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer(model="rule")
        result = analyzer.analyze("公司亏损，业绩下滑严重")

        assert result.score < 0
        assert result.label == "negative"


class TestTechnicalAnalyzer:
    """技术分析器测试"""

    def test_ma_calculation(self):
        """测试均线计算"""
        import pandas as pd
        from src.analyzers.technical_analyzer import TechnicalAnalyzer

        # 创建测试数据
        df = pd.DataFrame({
            "close": list(range(100, 120))
        })

        analyzer = TechnicalAnalyzer()
        ma_data = analyzer.calculate_ma(df)

        assert "ma5" in ma_data
        assert len(ma_data["ma5"]) == len(df)

    def test_rsi_calculation(self):
        """测试 RSI 计算"""
        import pandas as pd
        from src.analyzers.technical_analyzer import TechnicalAnalyzer

        df = pd.DataFrame({
            "close": [100, 102, 101, 103, 105, 104, 106, 108, 107, 109,
                      111, 110, 112, 114, 113, 115, 117, 116, 118, 120]
        })

        analyzer = TechnicalAnalyzer()
        rsi = analyzer.calculate_rsi(df)

        assert len(rsi) == len(df)
        assert all(0 <= rsi <= 100)


class TestSignalFusion:
    """信号融合测试"""

    def test_fusion_positive(self):
        """测试全利好信号融合"""
        from src.engine.signal_fusion import SignalFusionEngine

        engine = SignalFusionEngine()
        result = engine.fuse(
            stock_code="000001",
            stock_name="平安银行",
            news_score=0.8,
            technical_score=0.7,
            fund_score=0.6,
            sentiment_score=0.5,
        )

        assert result.total_score > 0.5
        assert result.signal in ["buy", "strong_buy"]

    def test_fusion_negative(self):
        """测试全利空信号融合"""
        from src.engine.signal_fusion import SignalFusionEngine

        engine = SignalFusionEngine()
        result = engine.fuse(
            stock_code="000001",
            stock_name="平安银行",
            news_score=-0.8,
            technical_score=-0.7,
            fund_score=-0.6,
            sentiment_score=-0.5,
        )

        assert result.total_score < -0.5
        assert result.signal in ["sell", "strong_sell"]


class TestRiskManager:
    """风险管理测试"""

    def test_blacklist_check(self):
        """测试黑名单检查"""
        from src.engine.risk_manager import RiskManager

        manager = RiskManager(blacklist=["000001"])

        allowed, reason = manager.check_stock("000001")
        assert not allowed
        assert "黑名单" in reason

        allowed, reason = manager.check_stock("000002")
        assert allowed

    def test_stop_loss_check(self):
        """测试止损检查"""
        from src.engine.risk_manager import RiskManager

        manager = RiskManager(stop_loss=0.08)

        # 亏损 10%，触发止损
        triggered, reason = manager.check_stop_loss("000001", 9.0, 10.0)
        assert triggered
        assert "止损" in reason

        # 亏损 5%，未触发止损
        triggered, reason = manager.check_stop_loss("000001", 9.5, 10.0)
        assert not triggered


class TestDatabase:
    """数据库测试"""

    def test_init_tables(self):
        """测试数据库表初始化"""
        import tempfile
        from src.utils.db import Database

        # 创建临时数据库
        with tempfile.NamedTemporaryFile(suffix=".db") as f:
            db = Database(f.name)

            # 验证表已创建
            with db.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
                tables = [row[0] for row in cursor.fetchall()]

                assert "stocks" in tables
                assert "news" in tables
                assert "prices" in tables
                assert "trading_signals" in tables

    def test_add_signal(self):
        """测试添加信号"""
        import tempfile
        from src.utils.db import Database

        with tempfile.NamedTemporaryFile(suffix=".db") as f:
            db = Database(f.name)

            result = db.add_signal(
                stock_code="000001",
                signal_type="buy",
                signal_score=0.7,
                news_score=0.6,
                technical_score=0.8,
                fund_score=0.5,
                sentiment_score=0.4,
                decision="买入",
                price=10.5,
                reason="测试信号",
            )

            assert result is True

            signals = db.get_signals(stock_code="000001", limit=1)
            assert len(signals) == 1
            assert signals[0]["signal_type"] == "buy"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
