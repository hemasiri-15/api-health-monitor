"""
=============================================================================
alerts.py - Alert / Notification Module
=============================================================================
Responsibility:
    - Send notifications when an endpoint goes DOWN or validation FAILS.
    - Supports three channels (configured via config.yaml):
        1. Console  (always active; uses Python logging)
        2. Email    (via SMTP / Gmail App Password)
        3. Slack    (via Incoming Webhook URL)
    - Each alert channel is independently toggled in config.yaml.
=============================================================================
"""

import logging
import smtplib
import urllib.request
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Console alert (always runs — minimal, no external dependencies)
# ---------------------------------------------------------------------------

def send_console_alert(endpoint_name: str, status: str, details: str) -> None:
    """
    Log an alert message to the console (stdout / log file).

    Args:
        endpoint_name: Human-readable name of the failing endpoint.
        status:        Current status string, e.g. 'DOWN'.
        details:       Short description of why the alert was triggered.
    """
    # Using WARNING level so it stands out from regular INFO logs
    logger.warning(
        "🚨 ALERT | Endpoint: %-40s | Status: %-8s | Reason: %s",
        endpoint_name, status, details
    )


# ---------------------------------------------------------------------------
# Email alert via SMTP
# ---------------------------------------------------------------------------

def send_email_alert(
    endpoint_name: str,
    status: str,
    details: str,
    email_config: Dict[str, Any]
) -> None:
    """
    Send an HTML email notification via SMTP (tested with Gmail).

    Prerequisites in config.yaml:
        alerts.email.smtp_server    e.g. "smtp.gmail.com"
        alerts.email.smtp_port      e.g. 587
        alerts.email.sender_email   Your Gmail address
        alerts.email.sender_password  Gmail App Password (not your login password)
        alerts.email.recipient_email  Where to send the alert

    Args:
        endpoint_name: Name of the failing endpoint.
        status:        Status string ('DOWN', 'DEGRADED', etc.).
        details:       Failure description.
        email_config:  Dict from config.yaml['alerts']['email'].
    """
    # Build a simple HTML email body
    subject = f"[API Monitor] {status} — {endpoint_name}"
    html_body = f"""
    <html><body>
    <h2 style="color:{'red' if status=='DOWN' else 'orange'}">
        API Monitor Alert: {status}
    </h2>
    <table border="1" cellpadding="6">
        <tr><td><b>Endpoint</b></td><td>{endpoint_name}</td></tr>
        <tr><td><b>Status</b></td><td>{status}</td></tr>
        <tr><td><b>Details</b></td><td>{details}</td></tr>
    </table>
    <p style="color:grey;font-size:12px;">Sent by API Health Check Monitor</p>
    </body></html>
    """

    # Assemble MIME message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_config.get("sender_email", "")
    msg["To"] = email_config.get("recipient_email", "")
    msg.attach(MIMEText(html_body, "html"))

    try:
        # Connect to SMTP server with STARTTLS for security
        with smtplib.SMTP(
            email_config.get("smtp_server", "smtp.gmail.com"),
            email_config.get("smtp_port", 587)
        ) as server:
            server.ehlo()
            server.starttls()
            server.login(
                email_config.get("sender_email", ""),
                email_config.get("sender_password", "")
            )
            server.sendmail(
                email_config["sender_email"],
                email_config["recipient_email"],
                msg.as_string()
            )
        logger.info("Email alert sent for: %s", endpoint_name)

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "Email auth failed — check sender_email and sender_password in config.yaml"
        )
    except Exception as exc:
        logger.error("Email send failed: %s", exc)


# ---------------------------------------------------------------------------
# Slack alert via Incoming Webhook
# ---------------------------------------------------------------------------

def send_slack_alert(
    endpoint_name: str,
    status: str,
    details: str,
    slack_config: Dict[str, Any]
) -> None:
    """
    Post an alert message to a Slack channel via an Incoming Webhook.

    Prerequisites:
        1. Create an Incoming Webhook in your Slack workspace.
        2. Paste the webhook URL into config.yaml under alerts.slack.webhook_url.

    Args:
        endpoint_name: Name of the failing endpoint.
        status:        Status string.
        details:       Failure description.
        slack_config:  Dict from config.yaml['alerts']['slack'].
    """
    webhook_url = slack_config.get("webhook_url", "")
    if not webhook_url or "YOUR" in webhook_url:
        logger.warning("Slack webhook URL not configured — skipping Slack alert")
        return

    # Build Slack Block Kit message for richer formatting
    emoji = "🔴" if status == "DOWN" else "🟡"
    payload = {
        "text": f"{emoji} *API Alert: {status}* — {endpoint_name}",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} API Monitor Alert"
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Endpoint:*\n{endpoint_name}"},
                    {"type": "mrkdwn", "text": f"*Status:*\n{status}"},
                    {"type": "mrkdwn", "text": f"*Details:*\n{details}"}
                ]
            }
        ]
    }

    # Use standard library urllib (no extra dependencies needed)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                logger.info("Slack alert sent for: %s", endpoint_name)
            else:
                logger.error("Slack webhook returned HTTP %s", resp.status)
    except Exception as exc:
        logger.error("Slack alert failed: %s", exc)


# ---------------------------------------------------------------------------
# Dispatcher — called by monitor.py on every failure
# ---------------------------------------------------------------------------

def dispatch_alert(
    endpoint_name: str,
    status: str,
    details: str,
    alert_config: Dict[str, Any]
) -> None:
    """
    Route an alert to all enabled notification channels.

    This is the ONLY function monitor.py needs to call.
    It reads the 'alerts' section from config.yaml to decide
    which channels are active.

    Args:
        endpoint_name: Name of the failing endpoint.
        status:        'DOWN', 'DEGRADED', or 'VALIDATION_FAILED'.
        details:       Human-readable reason for the alert.
        alert_config:  The full alerts dict from config.yaml.
    """
    # 1. Console is always active
    if alert_config.get("console_enabled", True):
        send_console_alert(endpoint_name, status, details)

    # 2. Email (optional)
    if alert_config.get("email_enabled", False):
        send_email_alert(
            endpoint_name, status, details,
            alert_config.get("email", {})
        )

    # 3. Slack (optional)
    if alert_config.get("slack_enabled", False):
        send_slack_alert(
            endpoint_name, status, details,
            alert_config.get("slack", {})
        )
