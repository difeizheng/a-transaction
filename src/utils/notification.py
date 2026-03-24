"""
通知模块 - 消息推送管理
"""
import json
import hmac
import hashlib
import base64
import time
import urllib.parse
import requests
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SignalMessage:
    """交易信号消息"""
    stock_code: str
    stock_name: str
    signal_type: str  # buy/sell/hold
    signal_score: float
    decision: str  # 强烈买入/买入/持有/卖出/强烈卖出
    price: float
    reason: str
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class NotificationManager:
    """通知管理器"""

    def __init__(
        self,
        wechat_webhook: str = "",
        dingtalk_webhook: str = "",
        dingtalk_secret: str = "",
        hook_url: str = "",
        console_output: bool = True,
    ):
        """
        初始化通知管理器

        Args:
            wechat_webhook: 微信机器人 Webhook URL
            dingtalk_webhook: 钉钉机器人 Webhook URL
            dingtalk_secret: 钉钉机器人签名 secret
            hook_url: 通用 Webhook URL
            console_output: 是否输出到控制台
        """
        self.wechat_webhook = wechat_webhook
        self.dingtalk_webhook = dingtalk_webhook
        self.dingtalk_secret = dingtalk_secret
        self.hook_url = hook_url
        self.console_output = console_output
        self._message_queue: List[SignalMessage] = []

    def send_signal(
        self,
        stock_code: str,
        stock_name: str,
        signal_type: str,
        signal_score: float,
        decision: str,
        price: float,
        reason: str,
    ) -> bool:
        """
        发送交易信号通知

        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            signal_type: 信号类型 (buy/sell/hold)
            signal_score: 信号得分
            decision: 决策结果
            price: 当前价格
            reason: 信号原因

        Returns:
            是否发送成功
        """
        msg = SignalMessage(
            stock_code=stock_code,
            stock_name=stock_name,
            signal_type=signal_type,
            signal_score=signal_score,
            decision=decision,
            price=price,
            reason=reason,
        )

        self._message_queue.append(msg)

        if self.console_output:
            self._print_to_console(msg)

        # 发送到 Webhook
        success = True
        if self.wechat_webhook:
            success &= self._send_wechat(msg)
        if self.dingtalk_webhook:
            success &= self._send_dingtalk(msg)
        if self.hook_url:
            success &= self._send_hook(msg)

        return success

    def _print_to_console(self, msg: SignalMessage) -> None:
        """控制台输出"""
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        console = Console()

        # 根据信号类型选择颜色
        color_map = {
            "buy": "green",
            "sell": "red",
            "hold": "yellow",
        }
        color = color_map.get(msg.signal_type, "white")

        # 创建信号表格
        table = Table(show_header=False, box=None)
        table.add_row("股票代码", msg.stock_code)
        table.add_row("股票名称", msg.stock_name)
        table.add_row("信号类型", f"[{color}]{msg.signal_type.upper()}[/{color}]")
        table.add_row("信号得分", f"{msg.signal_score:.2f}")
        table.add_row("决策结果", f"[{color}]{msg.decision}[/{color}]")
        table.add_row("当前价格", f"{msg.price:.2f}")
        table.add_row("信号原因", msg.reason)
        table.add_row("时间", msg.timestamp.strftime("%Y-%m-%d %H:%M:%S"))

        # 面板标题
        title = f"🚀 交易信号 - {msg.stock_name}({msg.stock_code})"

        console.print(Panel(table, title=title, border_style=color))

    def _send_wechat(self, msg: SignalMessage) -> bool:
        """
        发送微信通知（企业微信机器人）

        Args:
            msg: 信号消息

        Returns:
            是否发送成功
        """
        if not self.wechat_webhook:
            return False

        try:
            # 根据信号类型选择颜色
            color_map = {
                "buy": "info",
                "sell": "warning",
                "hold": "comment",
            }
            color = color_map.get(msg.signal_type, "info")

            markdown_content = f"""### 🚀 交易信号通知

**股票**: {msg.stock_name}({msg.stock_code})
**信号类型**: {msg.signal_type.upper()}
**信号得分**: {msg.signal_score:.2f}
**决策结果**: {msg.decision}
**当前价格**: {msg.price:.2f} 元
**信号原因**: {msg.reason}
**时间**: {msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
"""

            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "content": markdown_content
                }
            }

            response = requests.post(
                self.wechat_webhook,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("errcode") == 0:
                    logger.info(f"微信通知发送成功：{msg.stock_code}")
                    return True
                else:
                    logger.warning(f"微信通知发送失败：{result}")
                    return False
            else:
                logger.warning(f"微信通知 HTTP 错误：{response.status_code}")
                return False

        except Exception as e:
            logger.error(f"发送微信通知失败：{e}")
            return False

    def _send_dingtalk(self, msg: SignalMessage) -> bool:
        """
        发送钉钉通知（支持签名）

        Args:
            msg: 信号消息

        Returns:
            是否发送成功
        """
        if not self.dingtalk_webhook:
            return False

        try:
            # 生成签名
            timestamp = str(round(time.time() * 1000))
            secret = self.dingtalk_secret or ""

            if secret:
                # 使用 HMAC-SHA256 生成签名
                secret_enc = secret.encode('utf-8')
                string_to_sign = f'{timestamp}\n{secret}'
                string_to_sign_enc = string_to_sign.encode('utf-8')
                hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
                sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))

                # 拼接带签名的 URL
                webhook_url = f"{self.dingtalk_webhook}&timestamp={timestamp}&sign={sign}"
            else:
                # 无签名模式
                webhook_url = self.dingtalk_webhook

            # 根据信号类型选择图标
            icon_map = {
                "buy": "🟦",
                "sell": "🟥",
                "hold": "⚪",
            }
            icon = icon_map.get(msg.signal_type, "⚪")

            markdown_content = f"""#### {icon} 交易信号 - {msg.stock_name}({msg.stock_code})

| 项目 | 详情 |
|------|------|
| 信号类型 | {msg.signal_type.upper()} |
| 决策结果 | {msg.decision} |
| 信号得分 | {msg.signal_score:.2f} |
| 当前价格 | {msg.price:.2f} 元 |
| 信号原因 | {msg.reason} |
| 时间 | {msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')} |"""

            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": f"交易信号 - {msg.stock_name}",
                    "text": markdown_content
                }
            }

            response = requests.post(
                webhook_url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("errcode") == 0:
                    logger.info(f"钉钉通知发送成功：{msg.stock_code}")
                    return True
                else:
                    logger.warning(f"钉钉通知发送失败：{result}")
                    return False
            else:
                logger.warning(f"钉钉通知 HTTP 错误：{response.status_code}")
                return False

        except Exception as e:
            logger.error(f"发送钉钉通知失败：{e}")
            return False

    def _send_hook(self, msg: SignalMessage) -> bool:
        """
        发送通用 hook 通知

        Args:
            msg: 信号消息

        Returns:
            是否发送成功
        """
        if not self.hook_url:
            return False

        try:
            payload = {
                "event": "trading_signal",
                "stock_code": msg.stock_code,
                "stock_name": msg.stock_name,
                "signal_type": msg.signal_type,
                "signal_score": msg.signal_score,
                "decision": msg.decision,
                "price": msg.price,
                "reason": msg.reason,
                "timestamp": msg.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            }

            response = requests.post(
                self.hook_url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=10
            )

            if response.status_code == 200:
                logger.info(f"Hook 通知发送成功：{msg.stock_code}")
                return True
            else:
                logger.warning(f"Hook 通知 HTTP 错误：{response.status_code}")
                return False

        except Exception as e:
            logger.error(f"发送 Hook 通知失败：{e}")
            return False

    def send_market_summary(
        self,
        total_stocks: int,
        bullish_count: int,
        bearish_count: int,
        neutral_count: int,
        top_signals: List[Dict] = None,
        positions: List[Dict] = None,
        exits: List[Dict] = None,
    ) -> bool:
        """
        发送市场监控摘要

        Args:
            total_stocks: 监控股票总数
            bullish_count: 看多数量
            bearish_count: 看空数量
            neutral_count: 中性数量
            top_signals: 重要信号列表 (字典格式)
            positions: 新建持仓列表
            exits: 退出持仓列表

        Returns:
            是否发送成功
        """
        # 发送 Webhook
        success = True

        # 构建摘要内容
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 通用 webhook payload
        hook_payload = {
            "event": "monitor_summary",
            "timestamp": timestamp,
            "summary": {
                "total_stocks": total_stocks,
                "bullish_count": bullish_count,
                "bearish_count": bearish_count,
                "neutral_count": neutral_count,
            },
            "signals": top_signals or [],
            "new_positions": positions or [],
            "exits": exits or [],
        }

        # 发送到通用 webhook
        if self.hook_url:
            try:
                response = requests.post(
                    self.hook_url,
                    data=json.dumps(hook_payload),
                    headers={"Content-Type": "application/json"},
                    timeout=10
                )
                if response.status_code == 200:
                    logger.info("监控摘要发送到 Hook 成功")
                else:
                    logger.warning(f"Hook 通知 HTTP 错误：{response.status_code}")
                    success = False
            except Exception as e:
                logger.error(f"发送监控摘要到 Hook 失败：{e}")
                success = False

        # === 构建易读的摘要内容（钉钉 Markdown 优化版）===
        # 信号类型映射
        signal_names = {
            "buy": "买入",
            "strong_buy": "强烈买入",
            "sell": "卖出",
            "strong_sell": "强烈卖出",
        }

        # 钉钉 Markdown 支持有限，使用纯文本 + 简单标记
        # 注意：钉钉会将 emoji 转为彩色图标，这里保留常用 emoji
        summary_lines = []
        summary_lines.append(f"#### A 股监控摘要 - {timestamp}")
        summary_lines.append("")
        summary_lines.append(f"**扫描股票**: {total_stocks} 只")
        summary_lines.append(f"> 买入：{bullish_count} 只 | 卖出：{bearish_count} 只 | 观望：{neutral_count} 只")

        # 添加重要信号（使用列表格式）
        if top_signals:
            summary_lines.append("")
            summary_lines.append("**重要信号**:")
            for sig in top_signals[:5]:
                sig_type = sig.get("signal", "")
                code = sig.get("stock_code", "")
                name = sig.get("stock_name", "") or ""
                buy_score = sig.get("buy_score", 0)
                sell_score = sig.get("sell_score", 0)
                rsi = sig.get("rsi", 0)
                stop_dist = sig.get("stop_distance", 0)
                take_profit_dist = sig.get("take_profit_distance", 0)
                conditions = sig.get("conditions", {})

                # 信号图标 - 使用钉钉支持的 emoji
                if sig_type in ["strong_buy"]:
                    icon = "🟢"
                elif sig_type in ["buy"]:
                    icon = "🟦"
                elif sig_type in ["strong_sell"]:
                    icon = "🔴"
                elif sig_type in ["sell"]:
                    icon = "🟥"
                else:
                    icon = "⚪"

                # 构建信号原因
                reason_parts = []
                if sig_type in ["buy", "strong_buy"]:
                    buy_details = conditions.get("buy_details", {}) if conditions else {}
                    if buy_details.get("above_ma20"):
                        reason_parts.append("趋势向上")
                    if buy_details.get("ma5_above_ma10"):
                        reason_parts.append("短期强势")
                    if buy_details.get("macd_bullish"):
                        reason_parts.append("MACD 金叉")
                    if buy_details.get("rsi_ok"):
                        reason_parts.append("RSI 健康")
                    if buy_details.get("volume_up"):
                        reason_parts.append("放量")
                    if buy_details.get("new_high"):
                        reason_parts.append("新高")
                else:
                    sell_details = conditions.get("sell_details", {}) if conditions else {}
                    if sell_details.get("below_ma20"):
                        reason_parts.append("趋势向下")
                    if sell_details.get("ma5_below_ma10"):
                        reason_parts.append("短期弱势")
                    if sell_details.get("macd_bearish"):
                        reason_parts.append("MACD 死叉")
                    if sell_details.get("rsi_overbought"):
                        reason_parts.append("超买")
                    if sell_details.get("volume_down"):
                        reason_parts.append("缩量")

                reason_str = ",".join(reason_parts) if reason_parts else "信号触发"

                summary_lines.append(f"- {icon} **{name}({code})**: {signal_names.get(sig_type, sig_type)}")
                summary_lines.append(f"  - 原因：{reason_str} | 评分:{buy_score if sig_type in ['buy', 'strong_buy'] else sell_score:.2f} | RSI:{rsi:.0f}")
                summary_lines.append(f"  - 止损:{stop_dist:.1%} | 止盈:{take_profit_dist:.1%}")

        # 添加新建持仓
        if positions:
            summary_lines.append("")
            summary_lines.append("**新建持仓**:")
            for pos in positions:
                name = pos.get("stock_name", "") or ""
                code = pos.get("stock_code", "")
                price = pos.get("price", 0)
                stop = pos.get("stop_price", 0)
                target = pos.get("take_profit", 0)

                summary_lines.append(f"- 🟢 **{name}({code})**")
                summary_lines.append(f"  - 入场：{price:.2f} | 止损：{stop:.2f} | 止盈：{target:.2f}")

        # 添加退出持仓
        if exits:
            summary_lines.append("")
            summary_lines.append("**退出持仓**:")
            for exit_pos in exits:
                code = exit_pos.get("stock_code", "")
                reason = exit_pos.get("reason", "")
                price = exit_pos.get("exit_price", 0)

                reason_text = "止损" if "止损" in reason else "止盈" if "止盈" in reason else reason
                summary_lines.append(f"- ❌ **{code}**: {reason_text} ({price:.2f})")

        # 底部署名
        summary_lines.append("")
        summary_lines.append("---")
        summary_lines.append(f"*发送时间：{timestamp}*")

        markdown_text = "\n".join(summary_lines)

        # 钉钉通知（带签名）
        if self.dingtalk_webhook:
            try:
                timestamp_ms = str(round(time.time() * 1000))
                if self.dingtalk_secret:
                    secret_enc = self.dingtalk_secret.encode('utf-8')
                    string_to_sign = f'{timestamp_ms}\n{self.dingtalk_secret}'
                    string_to_sign_enc = string_to_sign.encode('utf-8')
                    hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
                    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
                    webhook_url = f"{self.dingtalk_webhook}&timestamp={timestamp_ms}&sign={sign}"
                else:
                    webhook_url = self.dingtalk_webhook

                payload = {
                    "msgtype": "markdown",
                    "markdown": {
                        "title": "A 股监控摘要",
                        "text": markdown_text
                    }
                }

                resp = requests.post(webhook_url, json=payload, timeout=10)
                if resp.status_code == 200 and resp.json().get("errcode") == 0:
                    logger.info("监控摘要发送到钉钉成功")
                else:
                    logger.warning(f"钉钉发送失败：{resp.json()}")
                    success = False
            except Exception as e:
                logger.error(f"发送监控摘要到钉钉失败：{e}")
                success = False

        # 微信通知
        if self.wechat_webhook:
            try:
                payload = {
                    "msgtype": "markdown",
                    "markdown": {
                        "content": markdown_text
                    }
                }
                resp = requests.post(self.wechat_webhook, json=payload, timeout=10)
                if resp.status_code == 200 and resp.json().get("errcode") == 0:
                    logger.info("监控摘要发送到微信成功")
                else:
                    logger.warning(f"微信发送失败：{resp.json()}")
                    success = False
            except Exception as e:
                logger.error(f"发送监控摘要到微信失败：{e}")
                success = False

        return success

    def flush_queue(self) -> List[SignalMessage]:
        """清空并返回消息队列"""
        messages = self._message_queue.copy()
        self._message_queue.clear()
        return messages
