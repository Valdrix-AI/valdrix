"""
Email Notification Service

Sends carbon budget alerts via email using SMTP.
"""

import smtplib
import html
import anyio
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any
import structlog

logger = structlog.get_logger()


def escape_html(text: str) -> str:
    """BE-NOTIF-1: Escape user-provided content to prevent HTML injection."""
    if not text:
        return ""
    return html.escape(str(text))


def _sanitize_header_value(value: str) -> str:
    """Prevent CRLF/header injection in email metadata fields."""
    text = str(value or "")
    if "\r" in text or "\n" in text:
        raise ValueError("Invalid email header value")
    return text.strip()


class EmailService:
    """
    Email notification service for carbon alerts.

    Uses SMTP to send HTML-formatted carbon budget alerts.
    Supports multiple recipients.
    """

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        from_email: str,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.from_email = from_email

    def _send_message_sync(self, message: MIMEMultipart, recipients: List[str]) -> None:
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            server.sendmail(self.from_email, recipients, message.as_string())

    async def _send_message(self, message: MIMEMultipart, recipients: List[str]) -> None:
        await anyio.to_thread.run_sync(self._send_message_sync, message, recipients)

    async def send_carbon_alert(
        self,
        recipients: List[str],
        budget_status: Dict[str, Any],
    ) -> bool:
        """
        Send carbon budget alert email.

        Args:
            recipients: List of email addresses
            budget_status: Budget status dict with usage info

        Returns:
            True if email sent successfully
        """
        if not recipients:
            logger.warning("email_alert_skipped", reason="No recipients")
            return False

        try:
            status = budget_status.get("alert_status", "unknown")
            subject = f"⚠️ Valdrix: Carbon Budget {'Exceeded' if status == 'exceeded' else 'Warning'}"

            html_body = self._build_email_html(budget_status)

            msg = MIMEMultipart("alternative")
            msg["Subject"] = _sanitize_header_value(subject)
            msg["From"] = _sanitize_header_value(self.from_email)
            msg["To"] = _sanitize_header_value(", ".join(recipients))

            msg.attach(MIMEText(html_body, "html"))

            await self._send_message(msg, recipients)

            logger.info(
                "carbon_email_sent",
                recipients=recipients,
                status=status,
            )
            return True

        except Exception as e:
            logger.error("carbon_email_failed", error=str(e))
            return False

    def _build_email_html(self, budget_status: Dict[str, Any]) -> str:
        """Build HTML email body."""
        status = budget_status.get("alert_status", "unknown")
        status_color = "#dc2626" if status == "exceeded" else "#f59e0b"
        status_text = "🚨 EXCEEDED" if status == "exceeded" else "⚠️ WARNING"

        recommendations = budget_status.get("recommendations", [])
        # BE-NOTIF-1: Escape user-provided content
        recs_html = "".join(f"<li>{escape_html(rec)}</li>" for rec in recommendations[:3])

        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #0f172a; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
        .content {{ background: #f8fafc; padding: 20px; border-radius: 0 0 8px 8px; }}
        .status {{ color: {status_color}; font-size: 24px; font-weight: bold; }}
        .metric {{ background: white; padding: 15px; border-radius: 8px; margin: 10px 0; }}
        .progress {{ background: #e5e7eb; height: 20px; border-radius: 10px; overflow: hidden; }}
        .progress-bar {{ background: {status_color}; height: 100%; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🌱 Valdrix Carbon Alert</h1>
        </div>
        <div class="content">
            <p class="status">{status_text}</p>

            <div class="metric">
                <h3>Monthly Carbon Usage</h3>
                <p><strong>{budget_status.get('current_usage_kg', 0):.2f} kg</strong> of {budget_status.get('budget_kg', 100):.0f} kg budget</p>
                <div class="progress">
                    <div class="progress-bar" style="width: {min(budget_status.get('usage_percent', 0), 100)}%"></div>
                </div>
                <p>{budget_status.get('usage_percent', 0):.1f}% used</p>
            </div>

            <div class="metric">
                <h3>💡 Recommendations</h3>
                <ul>{recs_html}</ul>
            </div>

            <p style="color: #64748b; font-size: 12px;">
                Sent by Valdrix GreenOps Dashboard<br>
                <a href="https://valdrix.io/greenops">View Dashboard</a>
            </p>
        </div>
    </div>
</body>
</html>
"""

    async def send_dunning_notification(
        self,
        to_email: str,
        attempt: int,
        max_attempts: int,
        next_retry_date: "datetime",
        tier: str,
    ) -> bool:
        """
        Send payment failed notification for dunning workflow.
        """
        
        try:
            subject = f"⚠️ Valdrix: Payment Failed ({attempt}/{max_attempts})"
            
            html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #dc2626; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
        .content {{ background: #f8fafc; padding: 20px; border-radius: 0 0 8px 8px; }}
        .warning {{ color: #dc2626; font-weight: bold; }}
        .cta {{ background: #2563eb; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; display: inline-block; margin: 15px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>💳 Payment Failed</h1>
        </div>
        <div class="content">
            <p>We were unable to process your subscription payment for the <strong>{escape_html(tier)}</strong> plan.</p>
            
            <p class="warning">Attempt {attempt} of {max_attempts}</p>
            
            <p>We will automatically retry your payment on <strong>{next_retry_date.strftime('%B %d, %Y')}</strong>.</p>
            
            <p>To avoid service interruption, please ensure your payment method is updated:</p>
            
            <a href="https://app.valdrix.io/settings/billing" class="cta">Update Payment Method</a>
            
            <p>If you have any questions, contact our support team.</p>
            
            <p style="color: #64748b; font-size: 12px;">
                Sent by Valdrix Billing
            </p>
        </div>
    </div>
</body>
</html>
"""

            msg = MIMEMultipart("alternative")
            msg["Subject"] = _sanitize_header_value(subject)
            msg["From"] = _sanitize_header_value(self.from_email)
            msg["To"] = _sanitize_header_value(to_email)

            msg.attach(MIMEText(html_body, "html"))

            await self._send_message(msg, [to_email])

            logger.info("dunning_email_sent", to_email=to_email, attempt=attempt)
            return True

        except Exception as e:
            logger.error("dunning_email_failed", error=str(e))
            return False

    async def send_payment_recovered_notification(self, to_email: str) -> bool:
        """Send payment recovered confirmation."""
        try:
            subject = "✅ Valdrix: Payment Successful - Account Reactivated"
            
            html_body = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background: #16a34a; color: white; padding: 20px; border-radius: 8px 8px 0 0; }
        .content { background: #f8fafc; padding: 20px; border-radius: 0 0 8px 8px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>✅ Payment Successful</h1>
        </div>
        <div class="content">
            <p>Great news! Your payment has been processed successfully.</p>
            
            <p>Your Valdrix subscription is now active and you have full access to all features.</p>
            
            <p>Thank you for your continued trust in Valdrix.</p>
            
            <p style="color: #64748b; font-size: 12px;">
                Sent by Valdrix Billing
            </p>
        </div>
    </div>
</body>
</html>
"""

            msg = MIMEMultipart("alternative")
            msg["Subject"] = _sanitize_header_value(subject)
            msg["From"] = _sanitize_header_value(self.from_email)
            msg["To"] = _sanitize_header_value(to_email)

            msg.attach(MIMEText(html_body, "html"))

            await self._send_message(msg, [to_email])

            logger.info("payment_recovered_email_sent", to_email=to_email)
            return True

        except Exception as e:
            logger.error("payment_recovered_email_failed", error=str(e))
            return False

    async def send_account_downgraded_notification(self, to_email: str) -> bool:
        """Send account downgraded notice."""
        try:
            subject = "🔻 Valdrix: Account Downgraded to Free Tier"
            
            html_body = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background: #f59e0b; color: white; padding: 20px; border-radius: 8px 8px 0 0; }
        .content { background: #f8fafc; padding: 20px; border-radius: 0 0 8px 8px; }
        .cta { background: #2563eb; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; display: inline-block; margin: 15px 0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔻 Account Downgraded</h1>
        </div>
        <div class="content">
            <p>We were unable to process your payment after multiple attempts.</p>
            
            <p>Your account has been downgraded to the <strong>Free Tier</strong>.</p>
            
            <p>You can resubscribe at any time to regain full access to premium features:</p>
            
            <a href="https://app.valdrix.io/settings/billing" class="cta">Resubscribe Now</a>
            
            <p>Your data is safe and will remain accessible on the Free Tier.</p>
            
            <p style="color: #64748b; font-size: 12px;">
                Sent by Valdrix Billing
            </p>
        </div>
    </div>
</body>
</html>
"""

            msg = MIMEMultipart("alternative")
            msg["Subject"] = _sanitize_header_value(subject)
            msg["From"] = _sanitize_header_value(self.from_email)
            msg["To"] = _sanitize_header_value(to_email)

            msg.attach(MIMEText(html_body, "html"))

            await self._send_message(msg, [to_email])

            logger.info("account_downgraded_email_sent", to_email=to_email)
            return True

        except Exception as e:
            logger.error("account_downgraded_email_failed", error=str(e))
            return False
