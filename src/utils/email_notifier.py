"""
邮件通知模块
功能：发送邮件通知、定时报告
"""
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import os
import json
import logging

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class EmailConfig:
    """邮件配置"""
    smtp_server: str
    smtp_port: int
    sender_email: str
    sender_password: str
    sender_name: str = "A 股监控系统"
    use_ssl: bool = True
    use_tls: bool = True


@dataclass
class EmailResult:
    """邮件发送结果"""
    success: bool
    message: str
    sent_to: List[str] = field(default_factory=list)
    sent_at: datetime = field(default_factory=datetime.now)


class EmailNotifier:
    """
    邮件通知器

    支持：
    - 普通文本邮件
    - HTML 邮件
    - 带附件邮件
    - 批量发送
    """

    def __init__(self, config: Optional[EmailConfig] = None):
        """
        初始化邮件通知器

        Args:
            config: 邮件配置
        """
        self.config = config
        self._last_result: Optional[EmailResult] = None

    def send_email(
        self,
        to_emails: List[str],
        subject: str,
        body: str,
        html: bool = False,
        attachments: Optional[List[str]] = None,
        cc_emails: Optional[List[str]] = None,
    ) -> EmailResult:
        """
        发送邮件

        Args:
            to_emails: 收件人列表
            subject: 邮件主题
            body: 邮件内容
            html: 是否 HTML 格式
            attachments: 附件路径列表
            cc_emails: 抄送人列表

        Returns:
            发送结果
        """
        if not self.config:
            return EmailResult(
                success=False,
                message="邮件配置未设置",
            )

        if not to_emails:
            return EmailResult(
                success=False,
                message="收件人列表为空",
            )

        try:
            # 创建邮件
            msg = MIMEMultipart()
            msg["From"] = f"{self.config.sender_name} <{self.config.sender_email}>"
            msg["To"] = ", ".join(to_emails)
            msg["Subject"] = subject

            if cc_emails:
                msg["Cc"] = ", ".join(cc_emails)

            # 添加正文
            content_type = "html" if html else "plain"
            msg.attach(MIMEText(body, content_type, "utf-8"))

            # 添加附件
            if attachments:
                for file_path in attachments:
                    if os.path.exists(file_path):
                        attachment = self._create_attachment(file_path)
                        msg.attach(attachment)

            # 发送邮件
            all_recipients = to_emails + (cc_emails or [])

            if self.config.use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(
                    self.config.smtp_server,
                    self.config.smtp_port,
                    context=context,
                ) as server:
                    server.login(
                        self.config.sender_email,
                        self.config.sender_password,
                    )
                    server.sendmail(
                        self.config.sender_email,
                        all_recipients,
                        msg.as_string(),
                    )
            else:
                with smtplib.SMTP(
                    self.config.smtp_server,
                    self.config.smtp_port,
                ) as server:
                    if self.config.use_tls:
                        server.starttls()
                    server.login(
                        self.config.sender_email,
                        self.config.sender_password,
                    )
                    server.sendmail(
                        self.config.sender_email,
                        all_recipients,
                        msg.as_string(),
                    )

            result = EmailResult(
                success=True,
                message="发送成功",
                sent_to=all_recipients,
            )
            self._last_result = result
            logger.info(f"邮件发送成功：{subject} -> {all_recipients}")
            return result

        except Exception as e:
            result = EmailResult(
                success=False,
                message=f"发送失败：{str(e)}",
            )
            self._last_result = result
            logger.error(f"邮件发送失败：{subject} - {e}")
            return result

    def _create_attachment(self, file_path: str) -> MIMEBase:
        """创建附件"""
        filename = os.path.basename(file_path)

        with open(file_path, "rb") as f:
            attachment = MIMEBase("application", "octet-stream")
            attachment.set_payload(f.read())

        encoders.encode_base64(attachment)
        attachment.add_header(
            "Content-Disposition",
            f"attachment; filename={filename}",
        )
        return attachment

    def send_daily_report(
        self,
        to_emails: List[str],
        report_data: Dict[str, Any],
    ) -> EmailResult:
        """
        发送日报

        Args:
            to_emails: 收件人列表
            report_data: 报告数据

        Returns:
            发送结果
        """
        subject = f"A 股监控日报 - {datetime.now().strftime('%Y-%m-%d')}"

        # 生成 HTML 报告
        html_body = self._generate_daily_report_html(report_data)

        return self.send_email(
            to_emails=to_emails,
            subject=subject,
            body=html_body,
            html=True,
        )

    def send_signal_alert(
        self,
        to_emails: List[str],
        stock_code: str,
        stock_name: str,
        signal_type: str,
        price: float,
        reason: str,
    ) -> EmailResult:
        """
        发送交易信号提醒

        Args:
            to_emails: 收件人列表
            stock_code: 股票代码
            stock_name: 股票名称
            signal_type: 信号类型
            price: 当前价格
            reason: 信号原因

        Returns:
            发送结果
        """
        subject = f"交易信号提醒 - {stock_name}({stock_code}) - {signal_type}"

        # 生成 HTML 内容
        signal_color = {
            "strong_buy": "#00cc44",
            "buy": "#00aa00",
            "hold": "#ffa500",
            "sell": "#ff4444",
            "strong_sell": "#cc0000",
        }.get(signal_type, "#666666")

        signal_name = {
            "strong_buy": "强烈买入",
            "buy": "买入",
            "hold": "持有",
            "sell": "卖出",
            "strong_sell": "强烈卖出",
        }.get(signal_type, signal_type)

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2 style="color: #333;">交易信号提醒</h2>
            <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 10px 0;">
                <p><strong>股票：</strong>{stock_name} ({stock_code})</p>
                <p><strong>信号：</strong><span style="color: {signal_color}; font-weight: bold;">{signal_name}</span></p>
                <p><strong>当前价格：</strong>¥{price:.2f}</p>
                <p><strong>信号原因：</strong>{reason}</p>
            </div>
            <p style="color: #888; font-size: 12px;">
                发送时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </p>
        </body>
        </html>
        """

        return self.send_email(
            to_emails=to_emails,
            subject=subject,
            body=html_body,
            html=True,
        )

    def send_market_alert(
        self,
        to_emails: List[str],
        alert_level: str,
        message: str,
        panic_index: float = 0,
    ) -> EmailResult:
        """
        发送市场警报

        Args:
            to_emails: 收件人列表
            alert_level: 警报级别
            message: 警报内容
            panic_index: 恐慌指数

        Returns:
            发送结果
        """
        subject = f"市场警报 - {alert_level}"

        alert_colors = {
            "normal": "#333333",
            "watch": "#ffa500",
            "warning": "#ff8800",
            "critical": "#ff4444",
            "emergency": "#cc0000",
        }

        color = alert_colors.get(alert_level, "#666666")

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2 style="color: {color};">⚠️ 市场警报</h2>
            <div style="background-color: #fff3f3; padding: 15px; border-radius: 5px; margin: 10px 0; border-left: 4px solid {color};">
                <p><strong>警报级别：</strong><span style="color: {color}; font-weight: bold;">{alert_level.upper()}</span></p>
                <p><strong>恐慌指数：</strong>{panic_index:.1f}</p>
                <p><strong>警报内容：</strong></p>
                <p>{message}</p>
            </div>
            <p style="color: #888; font-size: 12px;">
                发送时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </p>
        </body>
        </html>
        """

        return self.send_email(
            to_emails=to_emails,
            subject=subject,
            body=html_body,
            html=True,
        )

    def _generate_daily_report_html(self, data: Dict[str, Any]) -> str:
        """生成日报 HTML"""
        today = datetime.now().strftime("%Y-%m-%d")

        # 持仓信息
        positions_html = ""
        if "positions" in data:
            positions_html = """
            <h3>持仓情况</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr style="background-color: #f0f0f0;">
                    <th style="padding: 8px; border: 1px solid #ddd;">股票</th>
                    <th style="padding: 8px; border: 1px solid #ddd;">数量</th>
                    <th style="padding: 8px; border: 1px solid #ddd;">成本价</th>
                    <th style="padding: 8px; border: 1px solid #ddd;">当前价</th>
                    <th style="padding: 8px; border: 1px solid #ddd;">盈亏</th>
                </tr>
            """
            for pos in data["positions"]:
                pnl_color = "#00cc44" if pos.get("pnl", 0) >= 0 else "#ff4444"
                positions_html += f"""
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;">{pos.get('name', '')}({pos.get('code', '')})</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{pos.get('quantity', 0)}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">¥{pos.get('cost', 0):.2f}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">¥{pos.get('price', 0):.2f}</td>
                    <td style="padding: 8px; border: 1px solid #ddd; color: {pnl_color};">
                        {pos.get('pnl', 0):+.2f} ({pos.get('pnl_pct', 0):+.1f}%)
                    </td>
                </tr>
                """
            positions_html += "</table>"

        # 今日信号
        signals_html = ""
        if "signals" in data:
            signals_html = """
            <h3>今日信号</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr style="background-color: #f0f0f0;">
                    <th style="padding: 8px; border: 1px solid #ddd;">股票</th>
                    <th style="padding: 8px; border: 1px solid #ddd;">信号</th>
                    <th style="padding: 8px; border: 1px solid #ddd;">价格</th>
                    <th style="padding: 8px; border: 1px solid #ddd;">原因</th>
                </tr>
            """
            for sig in data["signals"]:
                sig_color = {
                    "strong_buy": "#00cc44",
                    "buy": "#00aa00",
                    "hold": "#ffa500",
                    "sell": "#ff4444",
                    "strong_sell": "#cc0000",
                }.get(sig.get("type", ""), "#666")
                signals_html += f"""
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;">{sig.get('name', '')}({sig.get('code', '')})</td>
                    <td style="padding: 8px; border: 1px solid #ddd; color: {sig_color};">{sig.get('type', '')}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">¥{sig.get('price', 0):.2f}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{sig.get('reason', '')[:50]}</td>
                </tr>
                """
            signals_html += "</table>"

        # 账户总览
        summary_html = ""
        if "summary" in data:
            s = data["summary"]
            total_color = "#00cc44" if s.get("total_return", 0) >= 0 else "#ff4444"
            summary_html = f"""
            <h3>账户总览</h3>
            <table style="width: 100%;">
                <tr>
                    <td><strong>总资产：</strong></td>
                    <td>¥{s.get('total_assets', 0):,.2f}</td>
                </tr>
                <tr>
                    <td><strong>可用资金：</strong></td>
                    <td>¥{s.get('available_cash', 0):,.2f}</td>
                </tr>
                <tr>
                    <td><strong>总盈亏：</strong></td>
                    <td style="color: {total_color};">
                        {s.get('total_return', 0):+.2f} ({s.get('total_return_pct', 0):+.1f}%)
                    </td>
                </tr>
            </table>
            """

        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                h2 {{ color: #333; }}
                h3 {{ color: #666; margin-top: 20px; }}
                table {{ width: 100%; margin: 10px 0; }}
            </style>
        </head>
        <body style="padding: 20px;">
            <h2>📈 A 股监控日报</h2>
            <p>报告日期：{today}</p>

            {summary_html}
            {positions_html}
            {signals_html}

            <p style="margin-top: 30px; color: #888; font-size: 12px; border-top: 1px solid #eee; padding-top: 10px;">
                此邮件由 A 股监控系统自动生成，仅供参考。
            </p>
        </body>
        </html>
        """

        return html


def create_email_notifier_from_config() -> Optional[EmailNotifier]:
    """从配置创建邮件通知器"""
    try:
        # 从配置文件读取
        config_path = os.path.join(os.path.dirname(__file__), "../../config.yaml")
        if not os.path.exists(config_path):
            logger.warning("配置文件不存在")
            return None

        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        email_config_data = config.get("notification", {}).get("email", {})
        if not email_config_data:
            logger.info("未配置邮件通知")
            return None

        email_config = EmailConfig(
            smtp_server=email_config_data.get("smtp_server", ""),
            smtp_port=email_config_data.get("smtp_port", 465),
            sender_email=email_config_data.get("sender_email", ""),
            sender_password=email_config_data.get("sender_password", ""),
            sender_name=email_config_data.get("sender_name", "A 股监控系统"),
            use_ssl=email_config_data.get("use_ssl", True),
            use_tls=email_config_data.get("use_tls", True),
        )

        return EmailNotifier(config=email_config)

    except Exception as e:
        logger.error(f"创建邮件通知器失败：{e}")
        return None


def run_email_demo():
    """邮件通知演示"""
    print("=" * 60)
    print("邮件通知演示")
    print("=" * 60)

    # 创建通知器（需要配置邮件信息）
    notifier = create_email_notifier_from_config()

    if not notifier:
        print("\n邮件通知未配置，跳过测试")
        print("\n请在 config.yaml 中添加以下配置:")
        print("""
notification:
  email:
    smtp_server: "smtp.example.com"
    smtp_port: 465
    sender_email: "your_email@example.com"
    sender_password: "your_password"
    sender_name: "A 股监控系统"
    recipients:
      - "recipient1@example.com"
      - "recipient2@example.com"
""")
        return None

    # 测试信号提醒
    print("\n[测试] 发送交易信号提醒...")
    result = notifier.send_signal_alert(
        to_emails=["test@example.com"],  # 替换为实际邮箱
        stock_code="000001",
        stock_name="平安银行",
        signal_type="buy",
        price=15.23,
        reason="技术面突破，MACD 金叉，RSI 进入强势区",
    )
    print(f"结果：{result.message}")

    # 测试市场警报
    print("\n[测试] 发送市场警报...")
    result = notifier.send_market_alert(
        to_emails=["test@example.com"],
        alert_level="warning",
        message="市场波动率异常，检测到多只股票成交量异常放大，建议降低仓位。",
        panic_index=45.5,
    )
    print(f"结果：{result.message}")

    # 测试日报
    print("\n[测试] 发送日报...")
    report_data = {
        "summary": {
            "total_assets": 125000,
            "available_cash": 35000,
            "total_return": 5200,
            "total_return_pct": 4.35,
        },
        "positions": [
            {"code": "000001", "name": "平安银行", "quantity": 1000, "cost": 14.5, "price": 15.23, "pnl": 730, "pnl_pct": 5.03},
            {"code": "600000", "name": "浦发银行", "quantity": 2000, "cost": 10.2, "price": 10.5, "pnl": 600, "pnl_pct": 2.94},
        ],
        "signals": [
            {"code": "000001", "name": "平安银行", "type": "buy", "price": 15.23, "reason": "技术面突破"},
        ],
    }

    result = notifier.send_daily_report(
        to_emails=["test@example.com"],
        report_data=report_data,
    )
    print(f"结果：{result.message}")

    return notifier


if __name__ == "__main__":
    run_email_demo()
