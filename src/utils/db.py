"""
数据库模块 - SQLite 数据存储
"""
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from contextlib import contextmanager
from datetime import datetime

from src.utils.logger import get_logger

logger = get_logger(__name__)


class Database:
    """数据库管理类"""

    def __init__(self, db_path: str = "data/trading.db"):
        """
        初始化数据库

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self._ensure_db_dir()
        self.init_tables()

    def _ensure_db_dir(self) -> None:
        """确保数据库目录存在"""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def get_connection(self):
        """获取数据库连接上下文管理器"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"数据库操作失败：{e}")
            raise
        finally:
            conn.close()

    def init_tables(self) -> None:
        """初始化数据表"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 股票信息表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    market TEXT,
                    industry TEXT,
                    is_st BOOLEAN DEFAULT 0,
                    is_kcb BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 新闻数据表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS news (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT,
                    source TEXT,
                    url TEXT,
                    publish_time TIMESTAMP,
                    sentiment_score REAL,
                    sentiment_label TEXT,
                    keywords TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (stock_code) REFERENCES stocks(code)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_stock ON news(stock_code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_time ON news(publish_time)")

            # 行情数据表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT NOT NULL,
                    trade_date DATE NOT NULL,
                    trade_time TIMESTAMP,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    pre_close REAL,
                    volume REAL,
                    amount REAL,
                    amplitude REAL,
                    change_pct REAL,
                    change_amount REAL,
                    turnover_rate REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(stock_code, trade_date),
                    FOREIGN KEY (stock_code) REFERENCES stocks(code)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_prices_stock ON prices(stock_code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_prices_date ON prices(trade_date)")

            # 资金流向表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fund_flows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT NOT NULL,
                    trade_date DATE NOT NULL,
                    trade_time TIMESTAMP,
                    main_net_in REAL,
                    large_order_net_in REAL,
                    medium_order_net_in REAL,
                    small_order_net_in REAL,
                    northbound_net_in REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(stock_code, trade_date),
                    FOREIGN KEY (stock_code) REFERENCES stocks(code)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_fund_stock ON fund_flows(stock_code)")

            # 技术指标表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS technical_indicators (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT NOT NULL,
                    trade_date DATE NOT NULL,
                    ma5 REAL,
                    ma10 REAL,
                    ma20 REAL,
                    ma60 REAL,
                    macd REAL,
                    macd_signal REAL,
                    macd_hist REAL,
                    rsi REAL,
                    kdj_k REAL,
                    kdj_d REAL,
                    kdj_j REAL,
                    boll_upper REAL,
                    boll_middle REAL,
                    boll_lower REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(stock_code, trade_date),
                    FOREIGN KEY (stock_code) REFERENCES stocks(code)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tech_stock ON technical_indicators(stock_code)")

            # 交易信号表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trading_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    signal_score REAL,
                    news_score REAL,
                    technical_score REAL,
                    fund_score REAL,
                    sentiment_score REAL,
                    decision TEXT,
                    price REAL,
                    reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (stock_code) REFERENCES stocks(code)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_signal_stock ON trading_signals(stock_code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_signal_time ON trading_signals(created_at)")

            # 持仓记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT NOT NULL,
                    stock_name TEXT,
                    quantity INTEGER,
                    avg_cost REAL,
                    current_price REAL,
                    market_value REAL,
                    profit_loss REAL,
                    profit_rate REAL,
                    status TEXT DEFAULT 'holding',
                    buy_date TIMESTAMP,
                    sell_date TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (stock_code) REFERENCES stocks(code)
                )
            """)

            # 交易记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT NOT NULL,
                    trade_type TEXT NOT NULL,
                    quantity INTEGER,
                    price REAL,
                    amount REAL,
                    commission REAL,
                    trade_date TIMESTAMP,
                    remark TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (stock_code) REFERENCES stocks(code)
                )
            """)

            # 账户资金表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS account (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    total_assets REAL,
                    available_cash REAL,
                    frozen_cash REAL,
                    market_value REAL,
                    profit_loss REAL,
                    profit_rate REAL,
                    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 插入初始账户记录
            cursor.execute("SELECT COUNT(*) FROM account")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO account (total_assets, available_cash, frozen_cash, market_value, profit_loss, profit_rate)
                    VALUES (1000000, 1000000, 0, 0, 0, 0)
                """)

            # 系统日志表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT,
                    module TEXT,
                    message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            logger.info("数据库表初始化完成")

    # ==================== 股票相关操作 ====================

    def add_stock(self, code: str, name: str, market: str = "",
                  industry: str = "", is_st: bool = False, is_kcb: bool = False) -> bool:
        """添加股票"""
        with self.get_connection() as conn:
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO stocks (code, name, market, industry, is_st, is_kcb, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (code, name, market, industry, is_st, is_kcb))
                return True
            except Exception as e:
                logger.error(f"添加股票失败：{e}")
                return False

    def get_stock(self, code: str) -> Optional[Dict[str, Any]]:
        """获取股票信息"""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM stocks WHERE code = ?", (code,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_stocks(self) -> List[Dict[str, Any]]:
        """获取所有股票"""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM stocks ORDER BY code")
            return [dict(row) for row in cursor.fetchall()]

    # ==================== 新闻相关操作 ====================

    def add_news(self, stock_code: str, title: str, content: str = "",
                 source: str = "", url: str = "", publish_time: datetime = None,
                 sentiment_score: float = None, sentiment_label: str = "",
                 keywords: str = "") -> bool:
        """添加新闻"""
        with self.get_connection() as conn:
            try:
                conn.execute("""
                    INSERT INTO news (stock_code, title, content, source, url,
                                      publish_time, sentiment_score, sentiment_label, keywords)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (stock_code, title, content, source, url,
                      publish_time or datetime.now(), sentiment_score, sentiment_label, keywords))
                return True
            except Exception as e:
                logger.error(f"添加新闻失败：{e}")
                return False

    def get_news(self, stock_code: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取新闻列表"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM news WHERE stock_code = ? ORDER BY publish_time DESC LIMIT ?",
                (stock_code, limit)
            )
            return [dict(row) for row in cursor.fetchall()]

    # ==================== 行情相关操作 ====================

    def add_price(self, stock_code: str, trade_date: str, **kwargs) -> bool:
        """添加行情数据"""
        with self.get_connection() as conn:
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO prices
                    (stock_code, trade_date, open, high, low, close, pre_close,
                     volume, amount, amplitude, change_pct, change_amount, turnover_rate, trade_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (stock_code, trade_date,
                      kwargs.get("open"), kwargs.get("high"), kwargs.get("low"),
                      kwargs.get("close"), kwargs.get("pre_close"),
                      kwargs.get("volume"), kwargs.get("amount"),
                      kwargs.get("amplitude"), kwargs.get("change_pct"),
                      kwargs.get("change_amount"), kwargs.get("turnover_rate"),
                      kwargs.get("trade_time", datetime.now())))
                return True
            except Exception as e:
                logger.error(f"添加行情数据失败：{e}")
                return False

    def get_prices(self, stock_code: str, start_date: str = None,
                   end_date: str = None, limit: int = None) -> List[Dict[str, Any]]:
        """获取行情数据"""
        query = "SELECT * FROM prices WHERE stock_code = ?"
        params = [stock_code]

        if start_date:
            query += " AND trade_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND trade_date <= ?"
            params.append(end_date)

        query += " ORDER BY trade_date DESC"
        if limit:
            query += " LIMIT ?"
            params.append(limit)

        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    # ==================== 信号相关操作 ====================

    def add_signal(self, stock_code: str, signal_type: str, signal_score: float,
                   news_score: float = None, technical_score: float = None,
                   fund_score: float = None, sentiment_score: float = None,
                   decision: str = "", price: float = None, reason: str = "") -> bool:
        """添加交易信号"""
        with self.get_connection() as conn:
            try:
                conn.execute("""
                    INSERT INTO trading_signals
                    (stock_code, signal_type, signal_score, news_score, technical_score,
                     fund_score, sentiment_score, decision, price, reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (stock_code, signal_type, signal_score, news_score, technical_score,
                      fund_score, sentiment_score, decision, price, reason))
                return True
            except Exception as e:
                logger.error(f"添加交易信号失败：{e}")
                return False

    def get_signals(self, stock_code: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """获取交易信号"""
        query = "SELECT * FROM trading_signals"
        params = []

        if stock_code:
            query += " WHERE stock_code = ?"
            params.append(stock_code)

        query += " ORDER BY created_at DESC"
        if limit:
            query += f" LIMIT {limit}"

        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    # ==================== 账户相关操作 ====================

    def update_account(self, total_assets: float, available_cash: float,
                       market_value: float, profit_loss: float, profit_rate: float) -> bool:
        """更新账户信息"""
        with self.get_connection() as conn:
            try:
                conn.execute("""
                    UPDATE account SET
                    total_assets = ?, available_cash = ?, market_value = ?,
                    profit_loss = ?, profit_rate = ?, update_time = CURRENT_TIMESTAMP
                    WHERE id = 1
                """, (total_assets, available_cash, market_value, profit_loss, profit_rate))
                return True
            except Exception as e:
                logger.error(f"更新账户信息失败：{e}")
                return False

    def get_account(self) -> Optional[Dict[str, Any]]:
        """获取账户信息"""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM account WHERE id = 1")
            row = cursor.fetchone()
            return dict(row) if row else None

    def log_system(self, level: str, module: str, message: str) -> None:
        """记录系统日志到数据库"""
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO system_logs (level, module, message) VALUES (?, ?, ?)",
                (level, module, message)
            )
