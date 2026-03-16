"""
Price Drop Alert System
=======================
Monitors the database for price drops and sends email alerts.

Features:
  • Absolute price target alerts  (notify when price ≤ $X)
  • Percentage drop alerts         (notify when price drops ≥ N%)
  • HTML email templates
  • SMTP / SendGrid / Gmail support
  • Cooldown period to prevent spam

Run manually:   python -m alerts.price_alert
Schedule via cron:  0 9 * * * cd /path/to/project && python -m alerts.price_alert
"""

import logging
import os
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from database.models import Database

logger = logging.getLogger(__name__)


# ─── Configuration ────────────────────────────────────────────────────────────

SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", 587))
SMTP_USER     = os.getenv("SMTP_USER", "your@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL    = os.getenv("FROM_EMAIL", SMTP_USER)
ALERT_COOLDOWN_HOURS = int(os.getenv("ALERT_COOLDOWN_HOURS", 24))


# ─── Email Builder ────────────────────────────────────────────────────────────

def build_alert_email(
    product_name: str,
    current_price: float,
    target_price: float,
    product_url: str,
    old_price: Optional[float] = None,
) -> tuple[str, str]:
    """Return (subject, html_body) for price drop notification."""

    drop_str = ""
    if old_price and old_price > current_price:
        pct = round((1 - current_price / old_price) * 100, 1)
        drop_str = f"<span style='color:#16a34a;font-weight:700'>↓ {pct}% drop</span> from ${old_price:.2f}"

    subject = f"🔔 Price Drop Alert: {product_name[:50]} is now ${current_price:.2f}"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8"/>
      <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background:#f4f4f5; margin:0; padding:20px; }}
        .card {{ background:#fff; border-radius:12px; max-width:540px; margin:0 auto;
                 padding:32px; box-shadow:0 4px 16px rgba(0,0,0,.08); }}
        .badge {{ display:inline-block; background:#dcfce7; color:#15803d;
                  padding:4px 12px; border-radius:99px; font-size:13px; font-weight:600; }}
        .price {{ font-size:42px; font-weight:800; color:#111; margin:16px 0 4px; }}
        .target {{ color:#6b7280; font-size:14px; margin-bottom:20px; }}
        .btn {{ display:inline-block; background:#111; color:#fff; padding:14px 28px;
                border-radius:8px; text-decoration:none; font-weight:700; font-size:15px; }}
        .footer {{ text-align:center; color:#9ca3af; font-size:12px; margin-top:24px; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="badge">Price Alert Triggered</div>
        <h2 style="margin:16px 0 8px;font-size:18px;color:#374151">{product_name}</h2>
        <div class="price">${current_price:.2f}</div>
        <div class="target">
          Your target: <strong>${target_price:.2f}</strong>
          {'&nbsp;&nbsp;•&nbsp;&nbsp;' + drop_str if drop_str else ''}
        </div>
        <a href="{product_url}" class="btn">View Deal →</a>
        <div class="footer">
          E-Commerce Price Tracker &nbsp;•&nbsp; Alert sent {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC
        </div>
      </div>
    </body>
    </html>
    """
    return subject, html


# ─── SMTP Sender ──────────────────────────────────────────────────────────────

def send_email(to: str, subject: str, html_body: str) -> bool:
    """Send an HTML email via SMTP. Returns True on success."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = FROM_EMAIL
    msg["To"]      = to
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(FROM_EMAIL, to, msg.as_string())
        logger.info(f"Alert email sent to {to}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")
        return False


# ─── Alert Checker ────────────────────────────────────────────────────────────

class AlertChecker:
    """
    Runs through all active alerts and sends notifications
    where current price satisfies the alert condition.
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.db = Database()

    def run(self):
        self.db.connect()
        try:
            alerts = self.db.get_pending_alerts()
            logger.info(f"Checking {len(alerts)} active alerts...")
            triggered = 0

            for alert in alerts:
                if self._should_trigger(alert):
                    self._trigger(alert)
                    triggered += 1

            logger.info(f"Done. Triggered {triggered} / {len(alerts)} alerts.")
        finally:
            self.db.close()

    def _should_trigger(self, alert: dict) -> bool:
        current = alert.get("current_price")
        if current is None:
            return False

        # Absolute target check
        if current <= alert["target_price"]:
            return True

        # Percentage drop check (if configured)
        if alert.get("pct_drop"):
            # Fetch yesterday's price for comparison
            history = self.db.get_price_history(alert["product_ref"], days=2)
            if len(history) >= 2:
                prev_price = history[-2]["price"]
                if prev_price and current < prev_price:
                    drop = (1 - current / prev_price) * 100
                    if drop >= alert["pct_drop"]:
                        return True
        return False

    def _trigger(self, alert: dict):
        subject, body = build_alert_email(
            product_name=alert["product_name"],
            current_price=alert["current_price"],
            target_price=alert["target_price"],
            product_url="",   # fetch from DB in production
        )

        if self.dry_run:
            logger.info(f"[DRY RUN] Would send alert to {alert['email']}: {subject}")
            return

        sent = send_email(alert["email"], subject, body)
        if sent:
            # Log and deactivate after first trigger (or keep active for recurring)
            self.db.conn.execute(
                "UPDATE alerts SET triggered_at=? WHERE id=?",
                (datetime.utcnow().isoformat(), alert["id"]),
            )
            self.db.conn.execute(
                """
                INSERT INTO alert_log (alert_ref, triggered_at, new_price, message)
                VALUES (?, ?, ?, ?)
                """,
                (alert["id"], datetime.utcnow().isoformat(),
                 alert["current_price"], subject),
            )
            self.db.conn.commit()


# ─── CLI Entry Point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Price Drop Alert Checker")
    parser.add_argument("--dry-run", action="store_true",
                        help="Check alerts without sending emails")
    args = parser.parse_args()

    checker = AlertChecker(dry_run=args.dry_run)
    checker.run()
