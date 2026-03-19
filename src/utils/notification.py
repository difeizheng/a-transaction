"""
通知模块 - 消息推送管理
"""
import json
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
        console_output: bool = True,
    ):
        """
        初始化通知管理器

        Args:
            wechat_webhook: 微信机器人 Webhook URL
            dingtalk_webhook: 钉钉机器人 Webhook URL
            console_output: 是否输出到控制台
        """
        self.wechat_webhook = wechat_webhook
        self.dingtalk_webhook = dingtalk_webhook
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
        发送钉钉通知

        Args:
            msg: 信号消息

        Returns:
            是否发送成功
        """
        if not self.dingtalk_webhook:
            return False

        try:
            # 根据信号类型选择颜色
            color_map = {
                "buy": "008800",
                "sell": "DD0000",
                "hold": "FF8800",
            }
            color = color_map.get(msg.signal_type, "008800")

            markdown_content = f"""### 🚀 交易信号通知

- **股票**: {msg.stock_name}({msg.stock_code})
- **信号类型**: {msg.signal_type.upper()}
- **信号得分**: {msg.signal_score:.2f}
- **决策结果**: {msg.decision}
- **当前价格**: {msg.price:.2f} 元
- **信号原因**: {msg.reason}
- **时间**: {msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
"""

            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": f"交易信号 - {msg.stock_name}",
                    "text": markdown_content
                }
            }

            response = requests.post(
                self.dingtalk_webhook,
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

    def send_market_summary(
        self,
        total_stocks: int,
        bullish_count: int,
        bearish_count: int,
        neutral_count: int,
        top_signals: List[SignalMessage] = None,
    ) -> bool:
        """
        发送市场_summary

        Args:
            total_stocks: 监控股票总数
            bullish_count: 看多数量
            bearish_count: 看空数量
            neutral_count: 中性数量
            top_signals: 重要信号列表

        Returns:
            是否发送成功
        """
        if not self.console_output and not self.wechat_webhook and not self.dingtalk_webhook:
            return True

        from rich.console import Console
        from rich.table import Table

        console = Console()

        # 控制台输出
        if self.console_output:
            table = Table(title="📊 市场监控摘要")
            table.add_column("指标", style="cyan")
            table.add_column("数值", style="white")

            table.add_row("监控股票总数", str(total_stocks))
            table.add_row("看多信号", f"[green]{bullish_count}[/green]")
            table.add_row("看空信号", f"[red]{bearish_count}[/red]")
            table.add_row("中性信号", str(neutral_count))

            console.print(table)

            if top_signals:
                console.print("\n[bold]重要信号:[/bold]")
                for sig in top_signals[:5]:
                    console.print(
                        f"  {sig.stock_name}({sig.stock_code}): "
                        f"[green]{sig.decision}[/green] ({sig.signal_score:.2f})"
                    )

        # 发送 Webhook
        success = True
        markdown_text = f"""### 📊 市场监控摘要

**监控股票总数**: {total_stocks}
**看多信号**: {bullish_count}
**看空信号**: {bearish_count}
**中性信号**: {neutral_count}
**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

        if top_signals:
            markdown_text += "\n**重要信号**:\n"
            for sig in top_signals[:5]:
                markdown_text += f"- {sig.stock_name}({sig.stock_code}): {sig.decision} ({sig.signal_score:.2f})\n"

        payload = {
            "msgtype": "markdown",
            "markdown": {"content": markdown_text}
        }

        if self.wechat_webhook:
            try:
                resp = requests.post(self.wechat_webhook, json=payload, timeout=10)
                success &= (resp.status_code == 200)
            except Exception as e:
                logger.error(f"发送市场摘要到微信失败：{e}")
                success = False

        return success

    def flush_queue(self) -> List[SignalMessage]:
        """清空并返回消息队列"""
        messages = self._message_queue.copy()
        self._message_queue.clear()
        return messages
