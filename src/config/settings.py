"""
设置模块 - 加载和管理系统配置
"""
import os
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class Settings:
    """系统设置数据类"""
    # 系统配置
    log_level: str = "INFO"
    log_dir: str = "logs"
    data_dir: str = "data"
    db_path: str = "data/trading.db"

    # 股票池配置
    stock_pool_type: str = "hs300"
    custom_stock_codes: List[str] = field(default_factory=list)
    max_stocks: int = 50

    # 监控配置
    monitor_interval: int = 300  # 秒
    market_hours_only: bool = True

    # 权重配置
    news_weight: float = 0.35
    technical_weight: float = 0.30
    fund_weight: float = 0.25
    sentiment_weight: float = 0.10

    # 交易配置
    initial_capital: float = 1000000.0
    max_position_per_stock: float = 0.2
    max_total_position: float = 0.95
    stop_loss: float = 0.08
    take_profit: float = 0.20
    min_buy_score: float = 0.5
    max_sell_score: float = -0.6

    # 风险配置
    max_drawdown: float = 0.15
    blacklist: List[str] = field(default_factory=list)
    exclude_st: bool = True
    exclude_kcb: bool = False

    # 通知配置
    notification_enabled: bool = True
    wechat_webhook: str = ""
    dingtalk_webhook: str = ""
    console_output: bool = True
    signal_threshold: float = 0.5

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Settings":
        """从字典创建 Settings"""
        system = data.get("system", {})
        stock_pool = data.get("stock_pool", {})
        monitor = data.get("monitor", {})
        sentiment = data.get("sentiment", {})
        technical = data.get("technical", {})
        fund_flow = data.get("fund_flow", {})
        market_sentiment = data.get("market_sentiment", {})
        trading = data.get("trading", {})
        risk = data.get("risk", {})
        notification = data.get("notification", {})

        return cls(
            log_level=system.get("log_level", "INFO"),
            log_dir=system.get("log_dir", "logs"),
            data_dir=system.get("data_dir", "data"),
            db_path=system.get("db_path", "data/trading.db"),
            stock_pool_type=stock_pool.get("type", "hs300"),
            custom_stock_codes=stock_pool.get("custom_codes", []),
            max_stocks=stock_pool.get("max_stocks", 50),
            monitor_interval=monitor.get("interval", 300),
            market_hours_only=monitor.get("market_hours", True),
            news_weight=sentiment.get("news_weight", 0.35),
            technical_weight=technical.get("weight", 0.30),
            fund_weight=fund_flow.get("weight", 0.25),
            sentiment_weight=market_sentiment.get("weight", 0.10),
            initial_capital=trading.get("initial_capital", 1000000),
            max_position_per_stock=trading.get("max_position_per_stock", 0.2),
            max_total_position=trading.get("max_total_position", 0.95),
            stop_loss=trading.get("stop_loss", 0.08),
            take_profit=trading.get("take_profit", 0.20),
            min_buy_score=trading.get("min_buy_score", 0.5),
            max_sell_score=trading.get("max_sell_score", -0.6),
            max_drawdown=risk.get("max_drawdown", 0.15),
            blacklist=risk.get("blacklist", []),
            exclude_st=risk.get("excluded_st", True),
            exclude_kcb=risk.get("excluded_kcb", False),
            notification_enabled=notification.get("enabled", True),
            wechat_webhook=notification.get("wechat_webhook", ""),
            dingtalk_webhook=notification.get("dingtalk_webhook", ""),
            console_output=notification.get("console", True),
            signal_threshold=notification.get("signal_threshold", 0.5),
        )


class Config:
    """配置管理主类"""

    _instance: Optional["Config"] = None
    _initialized: bool = False

    def __new__(cls) -> "Config":
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._config_path: Optional[Path] = None
        self._raw_config: Dict[str, Any] = {}
        self.settings: Settings = Settings()
        self._initialized = True

    def load(self, config_path: Optional[str] = None) -> "Config":
        """
        加载配置文件

        Args:
            config_path: 配置文件路径，默认当前目录的 config.yaml

        Returns:
            Config 实例
        """
        if config_path:
            self._config_path = Path(config_path)
        else:
            # 默认查找当前目录或项目根目录的 config.yaml
            search_paths = [
                Path("config.yaml"),
                Path(__file__).parent.parent.parent / "config.yaml",
            ]
            for p in search_paths:
                if p.exists():
                    self._config_path = p
                    break

        if self._config_path is None or not self._config_path.exists():
            raise FileNotFoundError(f"配置文件不存在：{self._config_path}")

        with open(self._config_path, "r", encoding="utf-8") as f:
            self._raw_config = yaml.safe_load(f)

        self.settings = Settings.from_dict(self._raw_config)
        return self

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key.split(".")
        value = self._raw_config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def ensure_dirs(self) -> None:
        """确保配置中涉及的目录存在"""
        dirs = [
            self.settings.log_dir,
            self.settings.data_dir,
            Path(self.settings.db_path).parent,
        ]
        for d in dirs:
            Path(d).mkdir(parents=True, exist_ok=True)


# 全局配置实例
config = Config()


def get_config() -> Config:
    """获取全局配置实例"""
    return config


def load_config(config_path: Optional[str] = None) -> Settings:
    """
    加载配置并返回 Settings

    Args:
        config_path: 配置文件路径

    Returns:
        Settings 实例
    """
    return config.load(config_path).settings
