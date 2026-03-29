"""
决策引擎 - 交易决策生成
支持：凯利公式仓位管理、波动率调整仓位、连胜/连败调整
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import numpy as np

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TradeDecision:
    """交易决策"""
    stock_code: str
    stock_name: str
    action: str              # buy/sell/hold
    strength: str            # strong/normal/weak
    price: float             # 当前价格
    target_price: float      # 目标价
    stop_loss: float         # 止损价
    position_ratio: float    # 建议仓位比例
    reason: str              # 决策原因
    confidence: float        # 置信度
    timestamp: datetime


class PositionManager:
    """
    动态仓位管理器

    支持：
    - 凯利公式计算最优仓位
    - 波动率调整仓位
    - 连胜/连败调整
    """

    def __init__(
        self,
        max_position_per_stock: float = 0.2,
        max_total_position: float = 0.95,
        kelly_ceiling: float = 0.25,  # 凯利公式上限
        volatility_lookback: int = 20,
    ):
        """
        初始化仓位管理器

        Args:
            max_position_per_stock: 单只股票最大仓位
            max_total_position: 最大总仓位
            kelly_ceiling: 凯利公式计算结果上限（防止过度集中）
            volatility_lookback: 波动率计算周期
        """
        self.max_position_per_stock = max_position_per_stock
        self.max_total_position = max_total_position
        self.kelly_ceiling = kelly_ceiling
        self.volatility_lookback = volatility_lookback

        # 绩效跟踪
        self.win_streak = 0
        self.loss_streak = 0
        self.consecutive_wins_max = 0
        self.consecutive_losses_max = 0

    def calculate_kelly_position(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        confidence: float = 1.0,
    ) -> float:
        """
        使用凯利公式计算最优仓位

        凯利公式：f* = (p * b - q) / b
        其中：p = 胜率，q = 败率，b = 盈亏比

        Args:
            win_rate: 胜率 [0, 1]
            avg_win: 平均盈利
            avg_loss: 平均亏损（正数）
            confidence: 信号置信度 [0, 1]

        Returns:
            建议仓位比例 [0, max_position_per_stock]
        """
        if avg_loss <= 0:
            avg_loss = 0.01  # 避免除零

        # 计算盈亏比
        win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 1.0

        # 凯利公式
        p = win_rate
        q = 1 - win_rate
        b = win_loss_ratio

        kelly = (p * b - q) / b

        # 应用置信度调整
        kelly *= confidence

        # 限制在合理范围内
        kelly = max(0, min(kelly, self.kelly_ceiling))

        # 不超过单只股票最大仓位
        kelly = min(kelly, self.max_position_per_stock)

        return round(kelly, 3)

    def adjust_for_volatility(
        self,
        base_position: float,
        current_volatility: float,
        target_volatility: float = 0.02,
    ) -> float:
        """
        根据波动率调整仓位

        波动率越高，仓位越低

        Args:
            base_position: 基础仓位
            current_volatility: 当前波动率（如 ATR 或历史波动率）
            target_volatility: 目标波动率

        Returns:
            调整后的仓位
        """
        if current_volatility <= 0:
            return base_position

        # 波动率调整因子
        vol_adjustment = target_volatility / current_volatility

        # 限制调整因子在 [0.5, 2.0] 范围内
        vol_adjustment = max(0.5, min(2.0, vol_adjustment))

        adjusted_position = base_position * vol_adjustment

        # 不超过最大仓位限制
        adjusted_position = min(adjusted_position, self.max_position_per_stock)

        return round(adjusted_position, 3)

    def adjust_for_streak(
        self,
        base_position: float,
        is_win: bool,
    ) -> float:
        """
        根据连胜/连败调整仓位

        Args:
            base_position: 基础仓位
            is_win: 最近一次交易是否盈利

        Returns:
            调整后的仓位
        """
        # 更新连胜/连败计数
        if is_win:
            self.win_streak += 1
            self.loss_streak = 0
        else:
            self.loss_streak += 1
            self.win_streak = 0

        # 更新最大值
        self.consecutive_wins_max = max(self.consecutive_wins_max, self.win_streak)
        self.consecutive_losses_max = max(self.consecutive_losses_max, self.loss_streak)

        # 连胜时适度增加仓位（信心增强）
        # 连败时降低仓位（风险控制）
        streak_adjustment = 1.0

        if self.win_streak >= 5:
            streak_adjustment = 1.15  # 连胜 5 场以上，增加 15%
        elif self.win_streak >= 3:
            streak_adjustment = 1.10  # 连胜 3 场以上，增加 10%
        elif self.win_streak >= 2:
            streak_adjustment = 1.05  # 连胜 2 场，增加 5%

        if self.loss_streak >= 5:
            streak_adjustment = 0.7  # 连败 5 场以上，降低 30%
        elif self.loss_streak >= 3:
            streak_adjustment = 0.8  # 连败 3 场以上，降低 20%
        elif self.loss_streak >= 2:
            streak_adjustment = 0.9  # 连败 2 场，降低 10%

        adjusted_position = base_position * streak_adjustment

        # 不超过最大仓位限制
        adjusted_position = min(adjusted_position, self.max_position_per_stock)

        # 不低于最小仓位
        adjusted_position = max(adjusted_position, 0.05)

        return round(adjusted_position, 3)

    def get_dynamic_position(
        self,
        base_position: float,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        current_volatility: float,
        target_volatility: float = 0.02,
        confidence: float = 1.0,
        last_trade_result: Optional[bool] = None,
    ) -> float:
        """
        综合计算动态仓位

        Args:
            base_position: 基础仓位
            win_rate: 胜率
            avg_win: 平均盈利
            avg_loss: 平均亏损
            current_volatility: 当前波动率
            target_volatility: 目标波动率
            confidence: 信号置信度
            last_trade_result: 最近一次交易结果

        Returns:
            动态调整后的仓位
        """
        # 1. 凯利公式计算
        kelly_position = self.calculate_kelly_position(
            win_rate, avg_win, avg_loss, confidence
        )

        # 2. 波动率调整
        vol_adjusted = self.adjust_for_volatility(
            kelly_position, current_volatility, target_volatility
        )

        # 3. 连胜/连败调整（如果有交易历史）
        if last_trade_result is not None:
            streak_adjusted = self.adjust_for_streak(vol_adjusted, last_trade_result)
        else:
            streak_adjusted = vol_adjusted

        # 4. 与基础仓位取较小值（更保守）
        final_position = min(streak_adjusted, base_position)

        # 确保不超过最大仓位
        final_position = min(final_position, self.max_position_per_stock)

        return round(final_position, 3)

    def reset(self):
        """重置连胜/连败计数"""
        self.win_streak = 0
        self.loss_streak = 0


class DecisionEngine:
    """
    交易决策引擎

    根据融合信号生成具体的交易决策：
    - 买入/卖出/持有
    - 仓位管理（支持凯利公式、波动率调整、连胜/连败调整）
    - 止盈止损
    """

    def __init__(
        self,
        initial_capital: float = 1000000.0,
        max_position_per_stock: float = 0.2,
        max_total_position: float = 0.95,
        stop_loss: float = 0.08,
        take_profit: float = 0.20,
        min_buy_score: float = 0.5,
        max_sell_score: float = -0.6,
        use_dynamic_position: bool = True,
        target_volatility: float = 0.02,
        kelly_ceiling: float = 0.25,
    ):
        """
        初始化决策引擎

        Args:
            initial_capital: 初始资金
            max_position_per_stock: 单只股票最大仓位
            max_total_position: 最大总仓位
            stop_loss: 止损比例
            take_profit: 止盈比例
            min_buy_score: 最小买入得分
            max_sell_score: 最大卖出得分
            use_dynamic_position: 是否使用动态仓位管理
            target_volatility: 目标波动率
            kelly_ceiling: 凯利公式上限
        """
        self.initial_capital = initial_capital
        self.max_position_per_stock = max_position_per_stock
        self.max_total_position = max_total_position
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.min_buy_score = min_buy_score
        self.max_sell_score = max_sell_score

        # 动态仓位管理
        self.use_dynamic_position = use_dynamic_position
        self.position_manager = PositionManager(
            max_position_per_stock=max_position_per_stock,
            max_total_position=max_total_position,
            kelly_ceiling=kelly_ceiling,
        )
        self.target_volatility = target_volatility

        # 当前状态
        self.available_cash = initial_capital
        self.positions: Dict[str, Dict] = {}  # 持仓
        self.trade_history: List[Dict] = field(default_factory=list)  # 交易历史
        self.stock_volatility: Dict[str, float] = {}  # 股票波动率

    def set_stock_volatility(self, stock_code: str, volatility: float):
        """设置股票波动率（用于动态仓位管理）"""
        self.stock_volatility[stock_code] = volatility

    def get_stock_volatility(self, stock_code: str) -> float:
        """获取股票波动率"""
        return self.stock_volatility.get(stock_code, self.target_volatility)

    def generate_decision(
        self,
        fusion_result,
        current_price: float,
        position_info: Optional[Dict] = None,
    ) -> TradeDecision:
        """
        生成交易决策

        Args:
            fusion_result: 信号融合结果
            current_price: 当前价格
            position_info: 持仓信息（可选）

        Returns:
            交易决策
        """
        stock_code = fusion_result.stock_code
        stock_name = fusion_result.stock_name
        score = fusion_result.total_score
        signal = fusion_result.signal
        confidence = fusion_result.confidence

        # 确定操作
        action, strength = self._determine_action(signal, score, position_info)

        # 计算建议仓位（传入置信度和股票代码）
        position_ratio = self._calculate_position(
            action, strength, score, position_info, confidence, stock_code
        )

        # 计算目标价和止损价
        target_price, stop_loss_price = self._calculate_price_levels(
            action, current_price, score
        )

        # 生成决策原因
        reason = self._generate_reason(
            action, strength, signal, score, fusion_result
        )

        return TradeDecision(
            stock_code=stock_code,
            stock_name=stock_name,
            action=action,
            strength=strength,
            price=current_price,
            target_price=target_price,
            stop_loss=stop_loss_price,
            position_ratio=position_ratio,
            reason=reason,
            confidence=confidence,
            timestamp=datetime.now(),
        )

    def _determine_action(
        self,
        signal: str,
        score: float,
        position_info: Optional[Dict],
    ) -> Tuple[str, str]:
        """
        确定操作

        Returns:
            (action, strength)
        """
        # 检查是否已持仓
        has_position = position_info is not None and position_info.get("quantity", 0) > 0

        if signal == "strong_buy":
            if has_position:
                return ("buy", "strong")  # 加仓
            else:
                return ("buy", "strong")

        elif signal == "buy":
            if score >= self.min_buy_score:
                if has_position:
                    return ("buy", "normal")  # 加仓
                else:
                    return ("buy", "normal")
            else:
                return ("hold", "weak")

        elif signal == "hold":
            return ("hold", "normal")

        elif signal == "sell":
            if has_position:
                if score <= self.max_sell_score:
                    return ("sell", "strong")  # 清仓
                else:
                    return ("sell", "normal")  # 减仓
            else:
                return ("hold", "weak")  # 空仓观望

        elif signal == "strong_sell":
            if has_position:
                return ("sell", "strong")  # 清仓
            else:
                return ("hold", "weak")

        return ("hold", "normal")

    def _calculate_position(
        self,
        action: str,
        strength: str,
        score: float,
        position_info: Optional[Dict],
        confidence: float = 1.0,
        stock_code: str = "",
    ) -> float:
        """
        计算建议仓位比例

        Returns:
            仓位比例 [0, 1]
        """
        if action == "hold":
            return 0.0

        if action == "sell":
            if strength == "strong":
                return 1.0  # 清仓
            else:
                return 0.5  # 减仓一半

        # 基础仓位
        base_position = self.max_position_per_stock

        # 根据信号强度调整
        if strength == "strong":
            position = base_position
        elif strength == "normal":
            position = base_position * 0.7
        else:
            position = base_position * 0.3

        # 如果启用动态仓位管理，使用综合计算
        if self.use_dynamic_position and stock_code:
            # 获取绩效数据
            perf = self.get_performance_summary()
            win_rate = perf.get("win_rate", 0.5)
            avg_win = perf.get("avg_win", 0.1)
            avg_loss = perf.get("avg_loss", 0.05)

            # 确保有合理的默认值
            if avg_loss <= 0:
                avg_loss = 0.05
            if avg_win <= 0:
                avg_win = 0.1

            # 获取波动率
            current_volatility = self.get_stock_volatility(stock_code)

            # 获取最近交易结果
            last_trade_result = None
            if self.trade_history:
                last_trade = self.trade_history[-1]
                last_trade_result = last_trade.get("pnl", 0) > 0

            # 计算动态仓位
            dynamic_position = self.position_manager.get_dynamic_position(
                base_position=position,
                win_rate=win_rate,
                avg_win=avg_win,
                avg_loss=avg_loss,
                current_volatility=current_volatility,
                target_volatility=self.target_volatility,
                confidence=confidence,
                last_trade_result=last_trade_result,
            )

            position = dynamic_position
        else:
            # 传统仓位计算
            # 根据得分微调
            position *= (0.5 + score)  # score 在 [-1, 1]，结果在 [0, 1]

        # 考虑剩余可用资金
        if position_info:
            current_quantity = position_info.get("quantity", 0)
            if current_quantity > 0:
                # 已持仓，计算可加仓比例
                max_allowed = self.max_position_per_stock
                position = min(position, max_allowed)

        # 确保不超过最大仓位限制
        position = min(position, self.max_position_per_stock)

        return round(position, 3)

    def _calculate_price_levels(
        self,
        action: str,
        current_price: float,
        score: float,
    ) -> Tuple[float, float]:
        """
        计算目标价和止损价

        Returns:
            (target_price, stop_loss_price)
        """
        if action == "hold":
            return (current_price, current_price)

        # 动态调整止盈止损
        # 信号越强，止盈可以设得越高，止损可以设得越紧
        if score >= 0.7:
            take_profit_adj = self.take_profit * 1.5  # 更宽松止盈
            stop_loss_adj = self.stop_loss * 0.7      # 更紧止损
        elif score >= 0.5:
            take_profit_adj = self.take_profit
            stop_loss_adj = self.stop_loss
        else:
            take_profit_adj = self.take_profit * 0.7  # 更紧止盈
            stop_loss_adj = self.stop_loss * 1.3      # 更宽松止损

        if action == "buy":
            target_price = current_price * (1 + take_profit_adj)
            stop_loss_price = current_price * (1 - stop_loss_adj)
        else:  # sell
            target_price = current_price  # 卖出时目标价为现价
            stop_loss_price = current_price * (1 + stop_loss_adj)  # 卖出的止损是价格上涨

        return (round(target_price, 2), round(stop_loss_price, 2))

    def _generate_reason(
        self,
        action: str,
        strength: str,
        signal: str,
        score: float,
        fusion_result,
    ) -> str:
        """生成决策原因"""
        reasons = []

        # 操作原因
        action_reasons = {
            "buy": {
                "strong": "强烈买入信号，多因子共振",
                "normal": "买入条件满足，建议建仓",
                "weak": "轻微买入信号，谨慎参与",
            },
            "sell": {
                "strong": "强烈卖出信号，建议清仓",
                "normal": "卖出条件满足，建议减仓",
                "weak": "轻微卖出信号，注意风险",
            },
            "hold": {
                "strong": "维持现状，等待明确信号",
                "normal": "暂无明确方向，观望为主",
                "weak": "信号不明确，保持观望",
            },
        }

        reasons.append(action_reasons.get(action, {}).get(strength, ""))

        # 各因子状态
        factor_status = []
        if fusion_result.news_score > 0.3:
            factor_status.append("新闻利好")
        elif fusion_result.news_score < -0.3:
            factor_status.append("新闻利空")

        if fusion_result.technical_score > 0.3:
            factor_status.append("技术面偏多")
        elif fusion_result.technical_score < -0.3:
            factor_status.append("技术面偏空")

        if fusion_result.fund_score > 0.3:
            factor_status.append("资金流入")
        elif fusion_result.fund_score < -0.3:
            factor_status.append("资金流出")

        if factor_status:
            reasons.append("; ".join(factor_status))

        # 综合得分
        reasons.append(f"综合得分：{score:.2f}")
        reasons.append(f"置信度：{fusion_result.confidence:.1%}")

        return " | ".join(reasons)

    def update_position(
        self,
        stock_code: str,
        stock_name: str,
        action: str,
        quantity: int,
        price: float,
        timestamp: Optional[datetime] = None,
    ):
        """
        更新持仓信息

        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            action: 操作 (buy/sell)
            quantity: 数量
            price: 价格
            timestamp: 时间戳
        """
        if action == "buy":
            if stock_code in self.positions:
                pos = self.positions[stock_code]
                total_cost = pos["avg_cost"] * pos["quantity"] + price * quantity
                pos["quantity"] += quantity
                pos["avg_cost"] = total_cost / pos["quantity"]
            else:
                self.positions[stock_code] = {
                    "stock_name": stock_name,
                    "quantity": quantity,
                    "avg_cost": price,
                    "entry_time": timestamp or datetime.now(),
                }

            self.available_cash -= price * quantity

        elif action == "sell":
            if stock_code in self.positions:
                pos = self.positions[stock_code]
                sell_qty = min(quantity, pos["quantity"])

                # 记录交易历史
                trade_record = {
                    "stock_code": stock_code,
                    "stock_name": pos.get("stock_name", stock_name),
                    "entry_price": pos["avg_cost"],
                    "exit_price": price,
                    "quantity": sell_qty,
                    "entry_time": pos.get("entry_time"),
                    "exit_time": timestamp or datetime.now(),
                    "pnl": (price - pos["avg_cost"]) * sell_qty,
                    "pnl_pct": (price - pos["avg_cost"]) / pos["avg_cost"],
                }
                self.trade_history.append(trade_record)

                pos["quantity"] -= sell_qty
                self.available_cash += price * sell_qty

                if pos["quantity"] <= 0:
                    del self.positions[stock_code]

    def get_trade_history(self) -> List[Dict]:
        """获取交易历史"""
        return self.trade_history

    def get_performance_summary(self) -> Dict:
        """获取绩效摘要"""
        if not self.trade_history:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.5,  # 默认 50% 胜率用于凯利公式
                "total_pnl": 0.0,
                "avg_pnl": 0.0,
                "avg_win": 0.1,  # 默认值
                "avg_loss": 0.05,  # 默认值
                "consecutive_wins": 0,
                "consecutive_losses": 0,
            }

        winning = [t for t in self.trade_history if t["pnl"] > 0]
        losing = [t for t in self.trade_history if t["pnl"] <= 0]
        total_pnl = sum(t["pnl"] for t in self.trade_history)

        return {
            "total_trades": len(self.trade_history),
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "win_rate": round(len(winning) / len(self.trade_history), 4) if self.trade_history else 0.5,
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(total_pnl / len(self.trade_history), 2),
            "avg_win": round(np.mean([t["pnl"] for t in winning]), 2) if winning else 0.1,
            "avg_loss": round(abs(np.mean([t["pnl"] for t in losing])), 2) if losing else 0.05,
            "consecutive_wins": self.position_manager.win_streak,
            "consecutive_losses": self.position_manager.loss_streak,
        }

    def get_kelly_recommendation(
        self,
        stock_code: str,
        confidence: float = 1.0,
    ) -> Dict:
        """
        获取凯利公式推荐的仓位

        Args:
            stock_code: 股票代码
            confidence: 信号置信度

        Returns:
            凯利公式推荐仓位详情
        """
        perf = self.get_performance_summary()
        volatility = self.get_stock_volatility(stock_code)

        kelly_raw = self.position_manager.calculate_kelly_position(
            win_rate=perf["win_rate"],
            avg_win=abs(perf["avg_win"]),
            avg_loss=abs(perf["avg_loss"]),
            confidence=confidence,
        )

        kelly_vol_adjusted = self.position_manager.adjust_for_volatility(
            kelly_raw,
            volatility,
            self.target_volatility,
        )

        return {
            "stock_code": stock_code,
            "kelly_raw": kelly_raw,
            "kelly_vol_adjusted": kelly_vol_adjusted,
            "win_rate": perf["win_rate"],
            "avg_win": perf["avg_win"],
            "avg_loss": perf["avg_loss"],
            "volatility": volatility,
            "consecutive_wins": perf["consecutive_wins"],
            "consecutive_losses": perf["consecutive_losses"],
        }

    def get_portfolio_summary(self) -> Dict:
        """获取投资组合摘要"""
        positions_value = 0
        for pos in self.positions.values():
            positions_value += pos["quantity"] * pos["avg_cost"]

        total_assets = self.available_cash + positions_value
        profit_loss = total_assets - self.initial_capital
        profit_rate = profit_loss / self.initial_capital

        return {
            "total_assets": round(total_assets, 2),
            "available_cash": round(self.available_cash, 2),
            "positions_value": round(positions_value, 2),
            "position_count": len(self.positions),
            "profit_loss": round(profit_loss, 2),
            "profit_rate": round(profit_rate, 4),
        }


__all__ = ["DecisionEngine", "TradeDecision", "PositionManager"]
