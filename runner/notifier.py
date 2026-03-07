"""
runner/notifier.py
─────────────────────────────────────────────────────────────────────────────
Notification helpers for the daily strategy runner.

Supports two channels (configurable, both optional):
  1. Email   — SMTP (Gmail, SendGrid, etc.)
  2. Webhook — HTTP POST (Discord, Slack, Teams, or any endpoint)

All send methods are fail-safe: a notification failure NEVER crashes the
runner. Errors are logged at WARNING level and execution continues.

Usage:
    notifier = Notifier(config.notifications, logger)
    notifier.send_daily_summary(summary, actions, date)
    notifier.send_error("Something went wrong")
"""

import json
import logging
import smtplib
import urllib.request
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from .runner_config import NotificationSettings


class Notifier:
    """
    Sends daily summaries and error alerts via email and/or webhook.

    Channels are enabled/disabled independently in the config.
    Both channels are attempted; failure in one does not block the other.

    Args:
        settings: NotificationSettings from RunnerConfig
        logger:   optional logger; defaults to module logger
    """

    def __init__(
        self,
        settings: NotificationSettings,
        logger: Optional[logging.Logger] = None,
    ):
        self._cfg = settings
        self._log = logger or logging.getLogger(__name__)

    # ── PUBLIC API ────────────────────────────────────────────────────────────

    def send_daily_summary(
        self,
        summary: dict,
        actions: List[dict],
        trading_date: date,
    ) -> None:
        """
        Send the end-of-session performance summary.

        Args:
            summary:       dict from OMS.summary()
            actions:       list of order action dicts from the runner
            trading_date:  the trading date (for the subject line)
        """
        subject = (
            f"[Trading Runner] Daily Summary {trading_date} "
            f"| Equity: ${summary.get('equity', 0):,.0f} "
            f"| PnL: ${summary.get('total_pnl', 0):+,.0f}"
        )
        body = _format_summary(summary, actions, trading_date)
        self._dispatch(subject, body)

    def send_error(self, message: str) -> None:
        """
        Send an error/alert notification.

        Args:
            message: human-readable error description
        """
        subject = f"[Trading Runner] ⚠️ ERROR: {message[:80]}"
        body = f"The daily strategy runner encountered an error:\n\n{message}"
        self._dispatch(subject, body)

    def send_market_closed(self, date_str: str) -> None:
        """Notify that the runner exited early because the market is closed today."""
        subject = f"[Trading Runner] Market closed on {date_str} — runner skipped"
        body = f"No trading activity on {date_str} (market holiday or weekend)."
        self._dispatch(subject, body)

    # ── PRIVATE ───────────────────────────────────────────────────────────────

    def _dispatch(self, subject: str, body: str) -> None:
        """Send to all enabled channels."""
        if self._cfg.email.enabled:
            self._send_email(subject, body)
        if self._cfg.webhook.enabled:
            self._send_webhook(subject, body)

    def _send_email(self, subject: str, body: str) -> None:
        """Send via SMTP. Fails silently with a warning log."""
        cfg = self._cfg.email
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = cfg.from_addr
            msg["To"]      = cfg.to_addr
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=15) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(cfg.username, cfg.password)
                smtp.sendmail(cfg.from_addr, [cfg.to_addr], msg.as_string())

            self._log.info(f"Email sent → {cfg.to_addr}")
        except Exception as exc:
            self._log.warning(f"Email notification failed: {exc}")

    def _send_webhook(self, subject: str, body: str) -> None:
        """
        POST a JSON payload to the configured webhook URL.

        Payload format is compatible with Discord, Slack, and Microsoft Teams.
        Falls back to a plain 'content' field if the channel-specific format fails.
        """
        cfg = self._cfg.webhook
        if not cfg.url:
            self._log.warning("Webhook enabled but no URL configured — skipping")
            return

        # Build payload — try Discord/Slack format first
        payload = _build_webhook_payload(subject, body, cfg.url)

        try:
            data    = json.dumps(payload).encode("utf-8")
            req     = urllib.request.Request(
                cfg.url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.getcode()
                if status not in (200, 204):
                    self._log.warning(f"Webhook returned status {status}")
                else:
                    self._log.info(f"Webhook notification sent (HTTP {status})")
        except Exception as exc:
            self._log.warning(f"Webhook notification failed: {exc}")


# ─── PRIVATE HELPERS ─────────────────────────────────────────────────────────

def _format_summary(summary: dict, actions: List[dict], trading_date: date) -> str:
    """Format a human-readable plain-text daily summary."""
    lines = [
        f"=== Trading Runner | {trading_date} ===",
        "",
        "ACCOUNT",
        f"  Equity:            ${summary.get('equity', 0):>14,.2f}",
        f"  Realised P&L:      ${summary.get('realised_pnl', 0):>+14,.2f}",
        f"  Unrealised P&L:    ${summary.get('unrealised_pnl', 0):>+14,.2f}",
        f"  Total P&L:         ${summary.get('total_pnl', 0):>+14,.2f}",
        f"  Drawdown:          {summary.get('current_drawdown', 0):>14.2%}",
        f"  Open Positions:    {summary.get('open_positions', 0):>14}",
        f"  Total Trades:      {summary.get('total_trades', 0):>14}",
        f"  Win Rate:          {summary.get('win_rate', 0):>14.1%}",
        "",
    ]

    if actions:
        lines.append("ORDERS PLACED TODAY")
        for a in actions:
            sym    = a.get("symbol", "?")
            action = a.get("action", "?")
            price  = a.get("price", 0.0)
            qty    = a.get("qty", 0)

            if action == "CLOSED":
                lines.append(f"  {sym:<6}  CLOSED              @ ${price:.2f}")
            elif action in ("OPENED_LONG", "OPENED_SHORT"):
                tp = a.get("tp", 0.0)
                sl = a.get("sl", 0.0)
                oid = a.get("order_id", "?")
                dir_str = "LONG " if action == "OPENED_LONG" else "SHORT"
                lines.append(
                    f"  {sym:<6}  {dir_str}  {qty:>4} shares  "
                    f"entry=${price:.2f}  TP=${tp:.2f}  SL=${sl:.2f}  ID={oid}"
                )
        lines.append("")
    else:
        lines.append("No orders placed today (all signals unchanged).")
        lines.append("")

    return "\n".join(lines)


def _build_webhook_payload(subject: str, body: str, url: str) -> dict:
    """
    Build a webhook JSON payload.

    - Discord webhooks expect {"content": "...", "embeds": [...]}
    - Slack webhooks expect {"text": "..."}
    - Teams webhooks expect {"@type": "MessageCard", "text": "..."}
    - Generic: {"content": "...", "text": "..."}

    We use a simple combined format that works across all of them.
    """
    text = f"**{subject}**\n\n{body}"

    if "discord.com" in url:
        # Discord: content field (max 2000 chars)
        return {"content": text[:2000]}

    if "hooks.slack.com" in url:
        # Slack: text field with markdown
        return {"text": text}

    if "webhook.office.com" in url or "logic.azure.com" in url:
        # Microsoft Teams (legacy connector format)
        return {
            "@type":    "MessageCard",
            "@context": "https://schema.org/extensions",
            "summary":  subject,
            "text":     body.replace("\n", "\n\n"),
        }

    # Generic fallback — works with most webhook services
    return {"content": text, "text": text}
