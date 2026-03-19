"""
决策引擎 - 交易决策生成
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

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


class DecisionEngine:
    """
    交易决策引擎

    根据融合信号生成具体的交易决策：
    - 买入/卖出/持有
    - 仓位管理
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
        """
        self.initial_capital = initial_capital
        self.max_position_per_stock = max_position_per_stock
        self.max_total_position = max_total_position
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.min_buy_score = min_buy_score
        self.max_sell_score = max_sell_score

        # 当前状态
        self.available_cash = initial_capital
        self.positions: Dict[str, Dict] = {}  # 持仓

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

        # 计算建议仓位
        position_ratio = self._calculate_position(action, strength, score, position_info)

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

        # 买入仓位计算
        base_position = self.max_position_per_stock

        # 根据信号强度调整
        if strength == "strong":
            position = base_position
        elif strength == "normal":
            position = base_position * 0.7
        else:
            position = base_position * 0.3

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
    ):
        """
        更新持仓信息

        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            action: 操作 (buy/sell)
            quantity: 数量
            price: 价格
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
                }

            self.available_cash -= price * quantity

        elif action == "sell":
            if stock_code in self.positions:
                pos = self.positions[stock_code]
                sell_qty = min(quantity, pos["quantity"])
                pos["quantity"] -= sell_qty
                self.available_cash += price * sell_qty

                if pos["quantity"] <= 0:
                    del self.positions[stock_code]

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


__all__ = ["DecisionEngine", "TradeDecision"]
