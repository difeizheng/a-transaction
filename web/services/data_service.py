"""
数据服务层 - 封装数据获取逻辑

提供统一的数据接口，供 Web 页面调用
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import streamlit as st

from src.collectors.price_collector import PriceCollector
from src.collectors.fund_collector import FundCollector
from src.collectors.news_collector import CompositeNewsCollector

from src.analyzers.technical_analyzer import TechnicalAnalyzer
from src.analyzers.fund_analyzer import FundAnalyzer
from src.analyzers.sentiment_analyzer import SentimentAnalyzer
from src.analyzers.volatility_analyzer import VolatilityAnalyzer
from src.analyzers.market_regime_analyzer import MarketRegimeAnalyzer
from src.analyzers.sector_analyzer import SectorAnalyzer

from src.engine.signal_fusion import SignalFusionEngine
from src.engine.decision_engine import DecisionEngine
from src.engine.risk_manager import RiskManager
from src.engine.black_swan_detector import BlackSwanDetector

from src.strategy.archived.improved_strategy import ImprovedStrategy

from src.utils.db import Database


class DataService:
    """
    数据服务类

    提供统一的数据获取接口，缓存数据以提高性能
    """

    def __init__(self):
        # 初始化数据采集器
        self.price_collector = PriceCollector()
        self.fund_collector = FundCollector()
        self.news_collector = CompositeNewsCollector()

        # 初始化分析器
        self.technical_analyzer = TechnicalAnalyzer()
        self.fund_analyzer = FundAnalyzer()
        self.sentiment_analyzer = SentimentAnalyzer()
        self.volatility_analyzer = VolatilityAnalyzer()
        self.market_regime_analyzer = MarketRegimeAnalyzer()
        self.sector_analyzer = SectorAnalyzer()

        # 初始化引擎
        self.signal_fusion = SignalFusionEngine()
        self.decision_engine = DecisionEngine()
        self.risk_manager = RiskManager()
        self.black_swan_detector = BlackSwanDetector()

        # 初始化策略
        self.strategy = ImprovedStrategy()

        # 初始化数据库
        self.db = Database()

        # 缓存数据
        self._cache = {}

    def get_stock_price(self, stock_code: str, days: int = 30) -> Optional[pd.DataFrame]:
        """获取股票价格数据"""
        cache_key = f"price_{stock_code}_{days}"

        if cache_key not in self._cache:
            df = self.price_collector.get_kline(
                stock_code,
                period='daily',
                limit=days + 30
            )
            self._cache[cache_key] = df

        return self._cache.get(cache_key)

    def get_realtime_quote(self, stock_code: str) -> Optional[Dict]:
        """获取实时行情"""
        return self.price_collector.get_realtime_quote(stock_code)

    def get_stock_batch_quotes(self, stock_codes: List[str]) -> List[Dict]:
        """批量获取实时行情"""
        return [self.get_realtime_quote(code) for code in stock_codes]

    def get_technical_indicators(self, stock_code: str, days: int = 60) -> Optional[Dict]:
        """获取技术指标"""
        df = self.get_stock_price(stock_code, days)
        if df is None or len(df) < 20:
            return None

        # 计算技术指标
        indicators = {}

        # MA
        for period in [5, 10, 20, 60]:
            ma = df['close'].rolling(period).mean()
            indicators[f'ma{period}'] = ma.iloc[-1] if not pd.isna(ma.iloc[-1]) else None

        # MACD
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        macd_dif = exp1 - exp2
        macd_dea = macd_dif.ewm(span=9, adjust=False).mean()
        macd_hist = macd_dif - macd_dea

        indicators['macd_dif'] = macd_dif.iloc[-1]
        indicators['macd_dea'] = macd_dea.iloc[-1]
        indicators['macd_hist'] = macd_hist.iloc[-1]

        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        indicators['rsi'] = rsi.iloc[-1]

        # KDJ
        low_min = df['low'].rolling(9).min()
        high_max = df['high'].rolling(9).max()
        k = 100 * (df['close'] - low_min) / (high_max - low_min)
        d = k.rolling(3).mean()
        j = 3 * k - 2 * d

        indicators['kdj_k'] = k.iloc[-1]
        indicators['kdj_d'] = d.iloc[-1]
        indicators['kdj_j'] = j.iloc[-1]

        # 布林带
        bb_ma = df['close'].rolling(20).mean()
        bb_std = df['close'].rolling(20).std()
        bb_upper = bb_ma + 2 * bb_std
        bb_lower = bb_ma - 2 * bb_std

        indicators['bb_upper'] = bb_upper.iloc[-1]
        indicators['bb_middle'] = bb_ma.iloc[-1]
        indicators['bb_lower'] = bb_lower.iloc[-1]

        # ATR
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        indicators['atr'] = atr.iloc[-1]

        return indicators

    def get_fund_flow(self, stock_code: str) -> Optional[Dict]:
        """获取资金流向"""
        return self.fund_collector.get_fund_flow(stock_code)

    def get_news(self, stock_code: str, limit: int = 10) -> List[Dict]:
        """获取新闻资讯"""
        return self.news_collector.collect_news(stock_code, limit)

    def get_sentiment(self, stock_code: str) -> Optional[Dict]:
        """获取情感分析"""
        news = self.get_news(stock_code, limit=20)
        if not news:
            return None

        # 分析情感
        sentiment_score = self.sentiment_analyzer.analyze(
            news[0].get('title', '') + ' ' + news[0].get('content', '')
        )

        return {
            'score': sentiment_score,
            'news_count': len(news),
            'latest_news': news[0] if news else None
        }

    def get_market_regime(self) -> Dict:
        """获取市场状态"""
        return self.market_regime_analyzer.analyze()

    def get_sector_flow(self) -> List[Dict]:
        """获取板块资金流向"""
        return self.sector_analyzer.get_sector_fund_flow()

    def get_signals(self, stock_codes: List[str]) -> List[Dict]:
        """获取交易信号"""
        signals = []

        for stock_code in stock_codes:
            # 获取数据
            df = self.get_stock_price(stock_code, days=60)
            if df is None or len(df) < 30:
                continue

            # 技术分析
            indicators = self.get_technical_indicators(stock_code)
            fund_flow = self.get_fund_flow(stock_code)
            sentiment = self.get_sentiment(stock_code)

            if not indicators:
                continue

            # 信号融合
            signal_scores = self.signal_fusion.fuse(
                technical=indicators,
                fund=fund_flow,
                sentiment=sentiment
            )

            # 决策
            decision = self.decision_engine.make_decision(
                signal_scores=signal_scores,
                stock_code=stock_code,
                current_price=df['close'].iloc[-1]
            )

            # 风险检查
            risk_check = self.risk_manager.check_risk(
                stock_code=stock_code,
                position_size=0,
                signals=decision
            )

            if decision['action'] != 'hold' and risk_check['allowed']:
                signals.append({
                    'stock_code': stock_code,
                    'action': decision['action'],
                    'price': df['close'].iloc[-1],
                    'score': decision.get('score', 0),
                    'reason': decision.get('reason', '')
                })

        return signals

    def get_black_swan_status(self) -> Dict:
        """获取黑天鹅检测状态"""
        return self.black_swan_detector.detect()

    def get_trading_history(self, limit: int = 100) -> List[Dict]:
        """获取交易历史"""
        return self.db.query(
            "SELECT * FROM trading_signals ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )

    def get_simulated_positions(self) -> List[Dict]:
        """获取模拟持仓"""
        return self.db.query("SELECT * FROM simulated_positions WHERE quantity > 0")

    def get_simulated_trades(self, limit: int = 50) -> List[Dict]:
        """获取模拟交易记录"""
        return self.db.query(
            "SELECT * FROM simulated_trades ORDER BY trade_time DESC LIMIT ?",
            (limit,)
        )

    def clear_cache(self):
        """清理缓存"""
        self._cache.clear()


# 全局数据服务实例
_data_service: Optional[DataService] = None


def get_data_service() -> DataService:
    """获取数据服务实例（单例）"""
    global _data_service

    if _data_service is None:
        _data_service = DataService()

    return _data_service