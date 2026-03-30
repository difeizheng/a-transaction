"""
Paper Trading Engine - 模拟撮合引擎

功能：
- 虚拟账户管理（现金、持仓、净值）
- 模拟买入/卖出（含真实 A 股费率和滑点）
- 动态追踪止损更新
- 止盈止损自动触发
- 全部持久化到 DB，重启后可恢复

A 股费率模型：
  买入：手续费 max(成交额×0.03%, 5元) + 过户费(沪市 成交额×0.006%)
  卖出：手续费 max(成交额×0.03%, 5元) + 印花税(成交额×0.1%) + 过户费(沪市 成交额×0.006%)
  滑点：买入+0.05%，卖出-0.05%
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from src.utils.logger import get_logger

logger = get_logger(__name__)

# ── A 股费率常量 ──────────────────────────────────────────────
SLIPPAGE_BUY     = 0.0005   # 买入滑点 0.05%
SLIPPAGE_SELL    = 0.0005   # 卖出滑点 0.05%
COMMISSION_RATE  = 0.0003   # 手续费率万三
COMMISSION_MIN   = 5.0      # 最低手续费 5 元
STAMP_TAX        = 0.001    # 印花税千一（仅卖出）
TRANSFER_FEE_SH  = 0.00006  # 沪市过户费（双向，深市免）


def _is_shanghai(stock_code: str) -> bool:
    """判断是否为沪市股票（60/68开头）"""
    return stock_code.startswith("60") or stock_code.startswith("68")


def _calc_buy_cost(amount: float, stock_code: str) -> Tuple[float, float, float]:
    """计算买入总费用，返回 (commission, transfer_fee, total_cost)"""
    commission = max(amount * COMMISSION_RATE, COMMISSION_MIN)
    transfer_fee = amount * TRANSFER_FEE_SH if _is_shanghai(stock_code) else 0.0
    return commission, transfer_fee, commission + transfer_fee


def _calc_sell_cost(amount: float, stock_code: str) -> Tuple[float, float, float, float]:
    """计算卖出总费用，返回 (commission, stamp_tax, transfer_fee, total_cost)"""
    commission = max(amount * COMMISSION_RATE, COMMISSION_MIN)
    stamp = amount * STAMP_TAX
    transfer_fee = amount * TRANSFER_FEE_SH if _is_shanghai(stock_code) else 0.0
    return commission, stamp, transfer_fee, commission + stamp + transfer_fee


# ── 数据结构 ──────────────────────────────────────────────────

@dataclass
class VirtualPosition:
    """虚拟持仓"""
    stock_code: str
    stock_name: str
    quantity: int           # 持股数量（100 的整数倍）
    avg_cost: float         # 平均成本（含手续费摊薄）
    entry_price: float      # 入场成交价（含滑点）
    entry_time: datetime
    stop_loss_price: float
    take_profit_price: float
    highest_price: float    # 持仓期间最高价（追踪止损用）
    signal_type: str        # buy / strong_buy
    signal_score: float
    db_id: int              # 对应 simulated_positions.id

    @property
    def market_value(self) -> float:
        return self.current_price * self.quantity

    # current_price 运行时更新，不存储在 dataclass 初始化中
    current_price: float = field(default=0.0)

    def unrealized_pnl(self) -> float:
        return (self.current_price - self.avg_cost) * self.quantity

    def unrealized_pnl_rate(self) -> float:
        if self.avg_cost == 0:
            return 0.0
        return (self.current_price - self.avg_cost) / self.avg_cost


# ── 主引擎 ────────────────────────────────────────────────────

class PaperTrader:
    """
    模拟撮合引擎

    使用方式：
        pt = PaperTrader(initial_capital=20000, db=db_instance)
        pt.load_positions_from_db()   # 重启恢复持仓

        # 每轮监控结束后：
        pt.update_prices({"000948": 12.5, ...})
        triggered = pt.check_stops()
        pt.save_equity_snapshot()
    """

    def __init__(self, initial_capital: float, db):
        self.initial_capital = initial_capital
        self.db = db

        # 运行时账户状态
        self.cash: float = initial_capital
        self.positions: Dict[str, VirtualPosition] = {}
        self.peak_equity: float = initial_capital

        # 从 DB 恢复持仓（重启不丢失）
        self._initialized = False

    def load_positions_from_db(self) -> None:
        """从 DB 恢复持仓和现金状态（启动时调用一次）"""
        if self._initialized:
            return
        self._initialized = True

        # 重新计算现金：初始资金 - 所有买入净额 + 所有卖出净额
        trades = self.db.get_simulated_trades(limit=0)
        cash = self.initial_capital
        for t in trades:
            if t["trade_type"] == "buy":
                cash -= t["net_amount"]   # net_amount = 成交额 + 费用
            elif t["trade_type"] == "sell":
                cash += t["net_amount"]   # net_amount = 成交额 - 费用
        self.cash = cash

        # 恢复当前持仓
        rows = self.db.get_open_positions()
        for row in rows:
            pos = VirtualPosition(
                stock_code=row["stock_code"],
                stock_name=row["stock_name"] or "",
                quantity=row["quantity"],
                avg_cost=row["entry_price"],
                entry_price=row["entry_price"],
                entry_time=datetime.fromisoformat(row["entry_date"]),
                stop_loss_price=row["stop_loss_price"] or 0.0,
                take_profit_price=row["take_profit_price"] or 0.0,
                highest_price=row["highest_price"] or row["entry_price"],
                signal_type=row.get("signal_type", ""),
                signal_score=row.get("signal_score", 0.0),
                db_id=row["id"],
                current_price=row["current_price"] or row["entry_price"],
            )
            self.positions[row["stock_code"]] = pos

        # 恢复历史峰值净值
        equity_rows = self.db.get_equity_curve(limit=1000)
        if equity_rows:
            self.peak_equity = max(r["total_equity"] for r in equity_rows)

        logger.info(
            f"Paper Trader 恢复：现金 {self.cash:.2f}，"
            f"持仓 {len(self.positions)} 只，峰值净值 {self.peak_equity:.2f}"
        )

    @property
    def position_value(self) -> float:
        return sum(p.current_price * p.quantity for p in self.positions.values())

    @property
    def total_equity(self) -> float:
        return self.cash + self.position_value

    # ── 买入 ────────────────────────────────────────────────

    def execute_buy(
        self,
        stock_code: str,
        stock_name: str,
        signal_price: float,
        signal_type: str,
        signal_score: float,
        quantity: int,
        stop_loss_price: float,
        take_profit_price: float,
        reason: str = "",
    ) -> bool:
        """
        模拟买入。

        Returns:
            True 表示成功，False 表示失败（资金不足 / 已持有）
        """
        if quantity <= 0:
            return False
        if stock_code in self.positions:
            logger.debug(f"[PaperTrader] {stock_code} 已持仓，跳过买入")
            return False

        # 含滑点的成交价
        exec_price = round(signal_price * (1 + SLIPPAGE_BUY), 3)
        gross_amount = exec_price * quantity
        commission, transfer_fee, total_cost = _calc_buy_cost(gross_amount, stock_code)
        net_amount = gross_amount + total_cost   # 实际扣款

        if net_amount > self.cash:
            logger.warning(
                f"[PaperTrader] {stock_code} 资金不足：需 {net_amount:.2f}，"
                f"可用 {self.cash:.2f}"
            )
            return False

        # 更新账户
        self.cash -= net_amount
        avg_cost = net_amount / quantity   # 含手续费的均价

        # 写 DB：持仓记录
        now = datetime.now()
        db_id = self.db.insert_simulated_position(
            stock_code=stock_code,
            stock_name=stock_name,
            entry_price=exec_price,
            quantity=quantity,
            entry_date=now,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            signal_type=signal_type,
            signal_score=signal_score,
        )

        # 写 DB：交易流水
        self.db.insert_simulated_trade(
            stock_code=stock_code,
            stock_name=stock_name,
            trade_type="buy",
            price=exec_price,
            quantity=quantity,
            amount=gross_amount,
            commission=commission,
            stamp_tax=0.0,
            transfer_fee=transfer_fee,
            net_amount=net_amount,
            signal_type=signal_type,
            signal_score=signal_score,
            reason=reason,
            trade_date=now,
            position_id=db_id,
        )

        # 内存持仓
        pos = VirtualPosition(
            stock_code=stock_code,
            stock_name=stock_name,
            quantity=quantity,
            avg_cost=avg_cost,
            entry_price=exec_price,
            entry_time=now,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            highest_price=exec_price,
            signal_type=signal_type,
            signal_score=signal_score,
            db_id=db_id,
            current_price=exec_price,
        )
        self.positions[stock_code] = pos

        logger.info(
            f"[PaperTrader] 买入 {stock_code} {stock_name} "
            f"× {quantity} @ {exec_price:.3f}，"
            f"成本 {net_amount:.2f}（含费 {total_cost:.2f}），"
            f"止损 {stop_loss_price:.3f}，止盈 {take_profit_price:.3f}"
        )
        return True

    # ── 卖出 ────────────────────────────────────────────────

    def execute_sell(
        self,
        stock_code: str,
        current_price: float,
        reason: str = "signal",
    ) -> Optional[float]:
        """
        模拟卖出。

        Returns:
            realized_pnl（实现盈亏），如果不持仓返回 None
        """
        pos = self.positions.get(stock_code)
        if pos is None:
            return None

        exec_price = round(current_price * (1 - SLIPPAGE_SELL), 3)
        gross_amount = exec_price * pos.quantity
        commission, stamp, transfer_fee, total_cost = _calc_sell_cost(gross_amount, stock_code)
        net_amount = gross_amount - total_cost   # 实际到账

        realized_pnl = net_amount - pos.avg_cost * pos.quantity
        profit_rate = realized_pnl / (pos.avg_cost * pos.quantity) if pos.avg_cost > 0 else 0.0

        # 更新账户
        self.cash += net_amount
        now = datetime.now()

        # 写 DB：平仓
        self.db.close_simulated_position(
            position_id=pos.db_id,
            exit_price=exec_price,
            exit_date=now,
            exit_reason=reason,
            profit_loss=realized_pnl,
            profit_rate=profit_rate,
        )

        # 写 DB：交易流水
        self.db.insert_simulated_trade(
            stock_code=stock_code,
            stock_name=pos.stock_name,
            trade_type="sell",
            price=exec_price,
            quantity=pos.quantity,
            amount=gross_amount,
            commission=commission,
            stamp_tax=stamp,
            transfer_fee=transfer_fee,
            net_amount=net_amount,
            signal_type="sell",
            signal_score=0.0,
            reason=reason,
            trade_date=now,
            position_id=pos.db_id,
            realized_pnl=realized_pnl,
        )

        pnl_str = f"+{realized_pnl:.2f}" if realized_pnl >= 0 else f"{realized_pnl:.2f}"
        logger.info(
            f"[PaperTrader] 卖出 {stock_code} {pos.stock_name} "
            f"× {pos.quantity} @ {exec_price:.3f}，"
            f"实现盈亏 {pnl_str}（{profit_rate:.1%}），原因：{reason}"
        )

        del self.positions[stock_code]
        return realized_pnl

    # ── 价格更新 + 止损检查 ─────────────────────────────────

    def update_prices(self, price_dict: Dict[str, float]) -> None:
        """
        更新所有持仓的当前价格，同时更新追踪止损。

        Args:
            price_dict: {stock_code: current_price}
        """
        for code, price in price_dict.items():
            pos = self.positions.get(code)
            if pos is None:
                continue
            pos.current_price = price

            # 追踪止损：若价格创新高，上移止损线
            if price > pos.highest_price:
                pos.highest_price = price
                # 追踪止损距离：最高价 × (1 - 3%)
                trailing_stop = round(pos.highest_price * 0.97, 3)
                if trailing_stop > pos.stop_loss_price:
                    pos.stop_loss_price = trailing_stop

            # 同步更新 DB 中的当前价格
            self.db.update_simulated_position_price(
                position_id=pos.db_id,
                current_price=price,
                highest_price=pos.highest_price,
                stop_loss_price=pos.stop_loss_price,
            )

    def check_stops(self) -> List[str]:
        """
        检查所有持仓是否触发止损/止盈，触发则自动卖出。

        Returns:
            被触发的股票代码列表
        """
        triggered = []
        for code in list(self.positions.keys()):
            pos = self.positions[code]
            price = pos.current_price
            if price <= 0:
                continue

            if price <= pos.stop_loss_price:
                self.execute_sell(code, price, reason="stop_loss")
                triggered.append(code)
            elif price >= pos.take_profit_price:
                self.execute_sell(code, price, reason="take_profit")
                triggered.append(code)

        return triggered

    def apply_signal_sell(self, stock_code: str, current_price: float) -> Optional[float]:
        """策略发出卖出信号时调用"""
        if stock_code not in self.positions:
            return None
        return self.execute_sell(stock_code, current_price, reason="signal")

    # ── 净值快照 ────────────────────────────────────────────

    def save_equity_snapshot(self) -> None:
        """保存当前净值快照到 DB"""
        equity = self.total_equity
        pos_val = self.position_value

        # 计算回撤
        if equity > self.peak_equity:
            self.peak_equity = equity
        drawdown = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0.0

        self.db.insert_equity_snapshot(
            timestamp=datetime.now(),
            total_equity=equity,
            cash=self.cash,
            position_value=pos_val,
            drawdown=drawdown,
        )

    # ── 统计 ────────────────────────────────────────────────

    def get_account_summary(self) -> Dict:
        """返回账户概览数据"""
        equity = self.total_equity
        pos_val = self.position_value
        total_pnl = equity - self.initial_capital
        total_pnl_rate = total_pnl / self.initial_capital if self.initial_capital > 0 else 0.0
        drawdown = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0.0

        return {
            "initial_capital": self.initial_capital,
            "cash": self.cash,
            "position_value": pos_val,
            "total_equity": equity,
            "total_pnl": total_pnl,
            "total_pnl_rate": total_pnl_rate,
            "peak_equity": self.peak_equity,
            "drawdown": drawdown,
            "position_count": len(self.positions),
        }

    def get_positions_detail(self) -> List[Dict]:
        """返回当前持仓详情列表"""
        result = []
        for code, pos in self.positions.items():
            pnl = pos.unrealized_pnl()
            result.append({
                "stock_code": code,
                "stock_name": pos.stock_name,
                "quantity": pos.quantity,
                "avg_cost": pos.avg_cost,
                "current_price": pos.current_price,
                "market_value": pos.current_price * pos.quantity,
                "unrealized_pnl": pnl,
                "unrealized_pnl_rate": pos.unrealized_pnl_rate(),
                "stop_loss_price": pos.stop_loss_price,
                "take_profit_price": pos.take_profit_price,
                "entry_time": pos.entry_time.strftime("%Y-%m-%d %H:%M"),
                "signal_type": pos.signal_type,
                "signal_score": pos.signal_score,
            })
        return result
