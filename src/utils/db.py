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

            # 模拟持仓表（Paper Trading）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS simulated_positions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code  TEXT NOT NULL,
                    stock_name  TEXT,
                    entry_price REAL NOT NULL,
                    quantity    INTEGER NOT NULL,
                    entry_date  TIMESTAMP NOT NULL,
                    current_price   REAL,
                    stop_loss_price REAL,
                    take_profit_price REAL,
                    highest_price   REAL,
                    status      TEXT DEFAULT 'holding',
                    exit_price  REAL,
                    exit_date   TIMESTAMP,
                    exit_reason TEXT,
                    profit_loss REAL,
                    profit_rate REAL,
                    signal_type TEXT,
                    signal_score REAL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_simpos_code ON simulated_positions(stock_code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_simpos_status ON simulated_positions(status)")

            # 模拟交易流水表（Paper Trading）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS simulated_trades (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code  TEXT NOT NULL,
                    stock_name  TEXT,
                    trade_type  TEXT NOT NULL,
                    price       REAL NOT NULL,
                    quantity    INTEGER NOT NULL,
                    amount      REAL NOT NULL,
                    commission  REAL DEFAULT 0.0,
                    stamp_tax   REAL DEFAULT 0.0,
                    transfer_fee REAL DEFAULT 0.0,
                    net_amount  REAL,
                    signal_type TEXT,
                    signal_score REAL,
                    reason      TEXT,
                    trade_date  TIMESTAMP NOT NULL,
                    position_id INTEGER,
                    realized_pnl REAL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_simtrade_code ON simulated_trades(stock_code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_simtrade_date ON simulated_trades(trade_date)")

            # 净值曲线表（Paper Trading）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS equity_curve (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp       TIMESTAMP NOT NULL,
                    total_equity    REAL NOT NULL,
                    cash            REAL NOT NULL,
                    position_value  REAL NOT NULL,
                    daily_return    REAL DEFAULT 0.0,
                    drawdown        REAL DEFAULT 0.0
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_equity_ts ON equity_curve(timestamp)")

            # 迁移：为旧版 simulated_positions 表补齐新字段
            self._migrate_simulated_positions(cursor)

            logger.info("数据库表初始化完成")

    def _migrate_simulated_positions(self, cursor) -> None:
        """为旧版 simulated_positions 表添加缺失字段（幂等）"""
        cursor.execute("PRAGMA table_info(simulated_positions)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        new_cols = {
            "highest_price":    "REAL",
            "signal_type":      "TEXT",
            "signal_score":     "REAL",
            "profit_rate":      "REAL",
        }
        for col, col_type in new_cols.items():
            if col not in existing_cols:
                cursor.execute(
                    f"ALTER TABLE simulated_positions ADD COLUMN {col} {col_type}"
                )

        # simulated_trades 同理
        cursor.execute("PRAGMA table_info(simulated_trades)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        new_trade_cols = {
            "commission":    "REAL DEFAULT 0.0",
            "stamp_tax":     "REAL DEFAULT 0.0",
            "transfer_fee":  "REAL DEFAULT 0.0",
            "net_amount":    "REAL",
            "position_id":   "INTEGER",
            "realized_pnl":  "REAL",
        }
        for col, col_def in new_trade_cols.items():
            if col not in existing_cols:
                cursor.execute(
                    f"ALTER TABLE simulated_trades ADD COLUMN {col} {col_def}"
                )

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

    # ==================== 模拟交易 (Paper Trading) ====================

    def insert_simulated_position(
        self,
        stock_code: str,
        stock_name: str,
        entry_price: float,
        quantity: int,
        entry_date: datetime,
        stop_loss_price: float,
        take_profit_price: float,
        signal_type: str = "",
        signal_score: float = 0.0,
    ) -> int:
        """新增模拟持仓记录，返回新记录的 id"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO simulated_positions
                (stock_code, stock_name, entry_price, quantity, entry_date,
                 current_price, stop_loss_price, take_profit_price, highest_price,
                 status, signal_type, signal_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'holding', ?, ?)
            """, (
                stock_code, stock_name, entry_price, quantity,
                entry_date.strftime("%Y-%m-%d %H:%M:%S"),
                entry_price, stop_loss_price, take_profit_price, entry_price,
                signal_type, signal_score,
            ))
            return cursor.lastrowid

    def update_simulated_position_price(
        self,
        position_id: int,
        current_price: float,
        highest_price: float,
        stop_loss_price: float,
    ) -> None:
        """更新模拟持仓的当前价格和动态止损价"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE simulated_positions
                SET current_price = ?, highest_price = ?, stop_loss_price = ?
                WHERE id = ?
            """, (current_price, highest_price, stop_loss_price, position_id))

    def close_simulated_position(
        self,
        position_id: int,
        exit_price: float,
        exit_date: datetime,
        exit_reason: str,
        profit_loss: float,
        profit_rate: float,
    ) -> None:
        """平仓：更新 simulated_positions 状态为 closed"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE simulated_positions
                SET status = 'closed', exit_price = ?, exit_date = ?,
                    exit_reason = ?, profit_loss = ?, profit_rate = ?
                WHERE id = ?
            """, (
                exit_price,
                exit_date.strftime("%Y-%m-%d %H:%M:%S"),
                exit_reason, profit_loss, profit_rate,
                position_id,
            ))

    def insert_simulated_trade(
        self,
        stock_code: str,
        stock_name: str,
        trade_type: str,
        price: float,
        quantity: int,
        amount: float,
        commission: float,
        stamp_tax: float,
        transfer_fee: float,
        net_amount: float,
        signal_type: str,
        signal_score: float,
        reason: str,
        trade_date: datetime,
        position_id: int = None,
        realized_pnl: float = None,
    ) -> int:
        """写入模拟交易流水，返回新记录 id"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO simulated_trades
                (stock_code, stock_name, trade_type, price, quantity, amount,
                 commission, stamp_tax, transfer_fee, net_amount,
                 signal_type, signal_score, reason, trade_date,
                 position_id, realized_pnl)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                stock_code, stock_name, trade_type, price, quantity, amount,
                commission, stamp_tax, transfer_fee, net_amount,
                signal_type, signal_score, reason,
                trade_date.strftime("%Y-%m-%d %H:%M:%S"),
                position_id, realized_pnl,
            ))
            return cursor.lastrowid

    def insert_equity_snapshot(
        self,
        timestamp: datetime,
        total_equity: float,
        cash: float,
        position_value: float,
        daily_return: float = 0.0,
        drawdown: float = 0.0,
    ) -> None:
        """写入净值快照"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO equity_curve
                (timestamp, total_equity, cash, position_value, daily_return, drawdown)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                total_equity, cash, position_value, daily_return, drawdown,
            ))

    def get_open_positions(self) -> List[Dict[str, Any]]:
        """获取当前所有持仓（status='holding'）"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM simulated_positions
                WHERE status = 'holding'
                ORDER BY entry_date DESC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def get_closed_trades(self, limit: int = 0) -> List[Dict[str, Any]]:
        """获取所有已平仓记录（用于统计胜率/期望值等）"""
        query = """
            SELECT * FROM simulated_positions
            WHERE status = 'closed'
            ORDER BY exit_date DESC
        """
        if limit > 0:
            query += f" LIMIT {limit}"
        with self.get_connection() as conn:
            cursor = conn.execute(query)
            return [dict(row) for row in cursor.fetchall()]

    def get_simulated_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取模拟交易流水记录"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM simulated_trades
                ORDER BY trade_date DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_equity_curve(self, limit: int = 500) -> List[Dict[str, Any]]:
        """获取净值曲线数据"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM equity_curve
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            rows = [dict(row) for row in cursor.fetchall()]
            return list(reversed(rows))  # 返回时间正序
