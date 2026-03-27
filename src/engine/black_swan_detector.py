"""
黑天鹅事件检测模块
功能：市场异常波动检测、恐慌指数计算、应急响应
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from enum import Enum

from src.utils.logger import get_logger

logger = get_logger(__name__)


class AlertLevel(Enum):
    """警报级别"""
    NORMAL = "normal"           # 正常
    WATCH = "watch"             # 关注
    WARNING = "warning"         # 警告
    CRITICAL = "critical"       # 严重
    EMERGENCY = "emergency"     # 紧急


@dataclass
class MarketShock:
    """市场冲击事件"""
    event_id: str
    event_type: str             # 类型：flash_crash/volume_spike/volatility_spike/correlation_breakdown
    severity: AlertLevel        # 严重程度
    description: str            # 描述
    detected_at: datetime       # 检测时间
    affected_stocks: List[str]  # 受影响股票
    impact_score: float         # 影响得分 [0, 1]
    suggested_action: str       # 建议操作


@dataclass
class BlackSwanResult:
    """黑天鹅检测结果"""
    market_status: str                  # 市场状态
    alert_level: AlertLevel             # 警报级别
    panic_index: float                  # 恐慌指数 [0, 100]
    active_shocks: List[MarketShock]    # 活跃冲击事件
    risk_factors: Dict[str, float]      # 风险因子
    suggested_position: float           # 建议仓位 [0, 1]
    detected_at: datetime = field(default_factory=datetime.now)


class BlackSwanDetector:
    """
    黑天鹅事件检测器

    检测类型：
    1. 闪崩检测 - 短时间内价格暴跌
    2. 成交量异常 - 成交量暴增/暴减
    3. 波动率异常 - VIX 恐慌指数飙升
    4. 相关性崩溃 - 股票间相关性异常
    5. 流动性危机 - 买卖价差异常
    """

    def __init__(
        self,
        flash_crash_threshold: float = 0.05,      # 闪崩阈值 5%
        volume_spike_threshold: float = 3.0,      # 成交量异常阈值 3 倍
        volatility_spike_threshold: float = 2.5,  # 波动率异常阈值 2.5 倍
        correlation_breakdown_threshold: float = 0.7,  # 相关性崩溃阈值
    ):
        """
        初始化检测器

        Args:
            flash_crash_threshold: 闪崩检测阈值（跌幅）
            volume_spike_threshold: 成交量异常倍数
            volatility_spike_threshold: 波动率异常倍数
            correlation_breakdown_threshold: 相关性崩溃阈值
        """
        self.flash_crash_threshold = flash_crash_threshold
        self.volume_spike_threshold = volume_spike_threshold
        self.volatility_spike_threshold = volatility_spike_threshold
        self.correlation_breakdown_threshold = correlation_breakdown_threshold

        # 历史基线数据
        self.baseline_volatility = 0.02  # 正常波动率 2%
        self.baseline_volume = 1.0       # 正常成交量基准
        self.baseline_correlation = 0.3  # 正常相关性

    def detect(
        self,
        price_data: Dict[str, pd.DataFrame],
        market_data: Optional[Dict] = None,
    ) -> BlackSwanResult:
        """
        检测黑天鹅事件

        Args:
            price_data: 价格数据 {stock_code: DataFrame}
            market_data: 市场数据（可选）

        Returns:
            黑天鹅检测结果
        """
        shocks = []

        # 1. 检测闪崩
        flash_crash_shocks = self._detect_flash_crash(price_data)
        shocks.extend(flash_crash_shocks)

        # 2. 检测成交量异常
        volume_shocks = self._detect_volume_spike(price_data)
        shocks.extend(volume_shocks)

        # 3. 检测波动率异常
        vol_shocks = self._detect_volatility_spike(price_data)
        shocks.extend(vol_shocks)

        # 4. 检测相关性崩溃
        corr_shocks = self._detect_correlation_breakdown(price_data)
        shocks.extend(corr_shocks)

        # 计算恐慌指数
        panic_index = self._calculate_panic_index(shocks)

        # 确定警报级别
        alert_level = self._determine_alert_level(shocks, panic_index)

        # 计算建议仓位
        suggested_position = self._calculate_suggested_position(alert_level, panic_index)

        # 确定市场状态
        market_status = self._determine_market_status(alert_level)

        # 提取风险因子
        risk_factors = self._extract_risk_factors(shocks)

        return BlackSwanResult(
            market_status=market_status,
            alert_level=alert_level,
            panic_index=panic_index,
            active_shocks=shocks,
            risk_factors=risk_factors,
            suggested_position=suggested_position,
        )

    def _detect_flash_crash(
        self,
        price_data: Dict[str, pd.DataFrame],
    ) -> List[MarketShock]:
        """检测闪崩"""
        shocks = []

        for code, df in price_data.items():
            if len(df) < 5:
                continue

            # 检查 5 分钟内跌幅
            if "close" not in df.columns:
                continue

            # 计算短期跌幅
            returns = df["close"].pct_change()

            # 检测大幅下跌
            large_drops = returns[returns < -self.flash_crash_threshold]

            if len(large_drops) > 0:
                max_drop = large_drops.min()
                shock = MarketShock(
                    event_id=f"flash_crash_{code}_{datetime.now().strftime('%H%M%S')}",
                    event_type="flash_crash",
                    severity=AlertLevel.CRITICAL if max_drop < -0.07 else AlertLevel.WARNING,
                    description=f"{code} 短期暴跌 {abs(max_drop):.1%}",
                    detected_at=datetime.now(),
                    affected_stocks=[code],
                    impact_score=min(1.0, abs(max_drop) / 0.1),
                    suggested_action="立即减仓或清仓",
                )
                shocks.append(shock)

        return shocks

    def _detect_volume_spike(
        self,
        price_data: Dict[str, pd.DataFrame],
    ) -> List[MarketShock]:
        """检测成交量异常"""
        shocks = []

        for code, df in price_data.items():
            if len(df) < 20:
                continue

            if "volume" not in df.columns:
                continue

            # 计算平均成交量
            avg_volume = df["volume"].rolling(20).mean()
            current_volume = df["volume"].iloc[-1]
            recent_avg = avg_volume.iloc[-1]

            if recent_avg > 0:
                volume_ratio = current_volume / recent_avg

                if volume_ratio > self.volume_spike_threshold:
                    severity = (
                        AlertLevel.CRITICAL if volume_ratio > 5.0
                        else AlertLevel.WARNING if volume_ratio > 3.0
                        else AlertLevel.WATCH
                    )

                    shock = MarketShock(
                        event_id=f"volume_spike_{code}_{datetime.now().strftime('%H%M%S')}",
                        event_type="volume_spike",
                        severity=severity,
                        description=f"{code} 成交量暴增 {volume_ratio:.1f}倍",
                        detected_at=datetime.now(),
                        affected_stocks=[code],
                        impact_score=min(1.0, (volume_ratio - 1) / 10),
                        suggested_action="警惕异常波动，考虑减仓",
                    )
                    shocks.append(shock)

        return shocks

    def _detect_volatility_spike(
        self,
        price_data: Dict[str, pd.DataFrame],
    ) -> List[MarketShock]:
        """检测波动率异常"""
        shocks = []

        for code, df in price_data.items():
            if len(df) < 30:
                continue

            # 计算波动率（使用 ATR 或标准差）
            returns = df["close"].pct_change()
            current_vol = returns.tail(5).std() * np.sqrt(252)  # 年化波动率

            vol_ratio = current_vol / self.baseline_volatility

            if vol_ratio > self.volatility_spike_threshold:
                severity = (
                    AlertLevel.CRITICAL if vol_ratio > 4.0
                    else AlertLevel.WARNING if vol_ratio > 2.5
                    else AlertLevel.WATCH
                )

                shock = MarketShock(
                    event_id=f"volatility_spike_{code}_{datetime.now().strftime('%H%M%S')}",
                    event_type="volatility_spike",
                    severity=severity,
                    description=f"{code} 波动率飙升 {vol_ratio:.1f}倍",
                    detected_at=datetime.now(),
                    affected_stocks=[code],
                    impact_score=min(1.0, (vol_ratio - 1) / 5),
                    suggested_action="降低仓位，收紧止损",
                )
                shocks.append(shock)

        return shocks

    def _detect_correlation_breakdown(
        self,
        price_data: Dict[str, pd.DataFrame],
    ) -> List[MarketShock]:
        """检测相关性崩溃"""
        if len(price_data) < 3:
            return []

        # 计算收益率矩阵
        returns_df = pd.DataFrame()
        for code, df in price_data.items():
            if len(df) >= 20 and "close" in df.columns:
                returns_df[code] = df["close"].pct_change().tail(20)

        if len(returns_df.columns) < 3 or len(returns_df) < 10:
            return []

        # 计算相关系数矩阵
        corr_matrix = returns_df.corr()

        # 计算平均相关性（去除对角线）
        n = len(corr_matrix)
        avg_corr = (corr_matrix.values.sum() - n) / (n * (n - 1))

        # 检测相关性异常升高（市场恐慌时所有股票相关性趋近 1）
        if avg_corr > self.correlation_breakdown_threshold:
            shock = MarketShock(
                event_id=f"correlation_breakdown_{datetime.now().strftime('%H%M%S')}",
                event_type="correlation_breakdown",
                severity=AlertLevel.WARNING,
                description=f"市场平均相关性飙升至 {avg_corr:.2f}",
                detected_at=datetime.now(),
                affected_stocks=list(price_data.keys()),
                impact_score=min(1.0, (avg_corr - 0.5) / 0.5),
                suggested_action="分散投资失效，降低总仓位",
            )
            return [shock]

        return []

    def _calculate_panic_index(self, shocks: List[MarketShock]) -> float:
        """计算恐慌指数 [0, 100]"""
        if not shocks:
            return 0.0

        # 基于冲击事件计算恐慌指数
        total_impact = sum(s.impact_score for s in shocks)
        critical_count = sum(1 for s in shocks if s.severity == AlertLevel.CRITICAL)

        # 恐慌指数 = 基础影响 + 严重事件加成
        panic_index = min(100, total_impact * 20 + critical_count * 15)

        return panic_index

    def _determine_alert_level(
        self,
        shocks: List[MarketShock],
        panic_index: float,
    ) -> AlertLevel:
        """确定警报级别"""
        if not shocks:
            return AlertLevel.NORMAL

        critical_count = sum(1 for s in shocks if s.severity == AlertLevel.CRITICAL)
        warning_count = sum(1 for s in shocks if s.severity == AlertLevel.WARNING)

        if critical_count >= 3 or panic_index >= 80:
            return AlertLevel.EMERGENCY
        elif critical_count >= 1 or panic_index >= 60:
            return AlertLevel.CRITICAL
        elif warning_count >= 3 or panic_index >= 40:
            return AlertLevel.WARNING
        elif panic_index >= 20:
            return AlertLevel.WATCH

        return AlertLevel.NORMAL

    def _calculate_suggested_position(
        self,
        alert_level: AlertLevel,
        panic_index: float,
    ) -> float:
        """计算建议仓位"""
        # 根据警报级别调整仓位
        position_map = {
            AlertLevel.NORMAL: 1.0,       # 满仓
            AlertLevel.WATCH: 0.7,        # 7 成仓
            AlertLevel.WARNING: 0.5,      # 5 成仓
            AlertLevel.CRITICAL: 0.2,     # 2 成仓
            AlertLevel.EMERGENCY: 0.0,    # 空仓
        }

        base_position = position_map.get(alert_level, 0.5)

        # 恐慌指数微调
        panic_adjustment = (100 - panic_index) / 100 * 0.2

        return max(0, min(1, base_position * (0.8 + panic_adjustment)))

    def _determine_market_status(self, alert_level: AlertLevel) -> str:
        """确定市场状态"""
        status_map = {
            AlertLevel.NORMAL: "正常",
            AlertLevel.WATCH: "关注",
            AlertLevel.WARNING: "风险",
            AlertLevel.CRITICAL: "高危",
            AlertLevel.EMERGENCY: "紧急",
        }
        return status_map.get(alert_level, "未知")

    def _extract_risk_factors(
        self,
        shocks: List[MarketShock],
    ) -> Dict[str, float]:
        """提取风险因子"""
        risk_factors = {
            "flash_crash_risk": 0.0,
            "volume_risk": 0.0,
            "volatility_risk": 0.0,
            "correlation_risk": 0.0,
            "overall_risk": 0.0,
        }

        for shock in shocks:
            if shock.event_type == "flash_crash":
                risk_factors["flash_crash_risk"] = max(
                    risk_factors["flash_crash_risk"],
                    shock.impact_score
                )
            elif shock.event_type == "volume_spike":
                risk_factors["volume_risk"] = max(
                    risk_factors["volume_risk"],
                    shock.impact_score
                )
            elif shock.event_type == "volatility_spike":
                risk_factors["volatility_risk"] = max(
                    risk_factors["volatility_risk"],
                    shock.impact_score
                )
            elif shock.event_type == "correlation_breakdown":
                risk_factors["correlation_risk"] = max(
                    risk_factors["correlation_risk"],
                    shock.impact_score
                )

        risk_factors["overall_risk"] = max(risk_factors.values())

        return risk_factors


def run_black_swan_demo():
    """黑天鹅检测演示"""
    print("=" * 60)
    print("黑天鹅事件检测演示")
    print("=" * 60)

    # 创建模拟数据
    dates = pd.date_range("2024-01-01", periods=100, freq="D")

    # 正常股票
    normal_df = pd.DataFrame({
        "close": 100 * (1 + np.random.randn(100) * 0.02).cumprod(),
        "volume": np.random.randint(1000000, 5000000, 100),
    }, index=dates)

    # 闪崩股票
    crash_df = normal_df.copy()
    crash_df["close"].iloc[-5:] = crash_df["close"].iloc[-5] * 0.9  # 暴跌 10%

    # 成交量异常股票
    volume_df = normal_df.copy()
    volume_df["volume"].iloc[-1] = volume_df["volume"].mean() * 5  # 5 倍成交量

    price_data = {
        "000001": normal_df,
        "600000": crash_df,
        "000002": volume_df,
    }

    # 创建检测器
    detector = BlackSwanDetector()

    # 检测
    result = detector.detect(price_data)

    # 输出结果
    print("\n" + "=" * 60)
    print("检测结果")
    print("=" * 60)
    print(f"市场状态：{result.market_status}")
    print(f"警报级别：{result.alert_level.value}")
    print(f"恐慌指数：{result.panic_index:.1f}")
    print(f"建议仓位：{result.suggested_position:.0%}")

    print(f"\n风险因子:")
    for k, v in result.risk_factors.items():
        print(f"  {k}: {v:.2f}")

    print(f"\n活跃冲击事件 ({len(result.active_shocks)}):")
    for shock in result.active_shocks:
        print(f"  [{shock.severity.value}] {shock.event_type}: {shock.description}")
        print(f"      建议：{shock.suggested_action}")

    return result


if __name__ == "__main__":
    run_black_swan_demo()
