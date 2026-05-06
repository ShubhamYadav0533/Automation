"""
job_hunter_agent/notifier.py
=============================
Sends real-time notifications to you via:
  - Telegram Bot (primary — instant phone notification)
  - Email to yourself (backup)
"""

import os
import logging
import requests
from typing import Dict
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ─────────────────────────────────────────────
#  TELEGRAM notifications
# ─────────────────────────────────────────────
def send_telegram(message: str) -> bool:
    """Send a message to your Telegram account via bot."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured. Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env")
        return False

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info("📱 Telegram notification sent")
            return True
        else:
            logger.error(f"Telegram error: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False


def notify_hot_lead(lead: Dict, summary: str) -> None:
    """Notify user about a confirmed hot lead."""
    message = f"""
🔥 <b>HOT LEAD CONFIRMED!</b>

{summary}

🔗 <b>URL:</b> {lead.get('url', 'N/A')}
🏢 <b>Company:</b> {lead.get('company', 'Unknown')}
📊 <b>Match Score:</b> {lead.get('ai_score', '?')}/100

⚡ The AI has already sent your intro email.
💬 If they replied, AI has responded back.
👉 This lead is HOT — check your Gmail for the thread!
"""
    send_telegram(message.strip())


def notify_agent_started() -> None:
    """Notify that the agent has started a new hunt."""
    send_telegram(
        "🤖 <b>Job Hunter Agent Started</b>\n\n"
        "🔍 Scanning Upwork, LinkedIn, Remotive, Google Maps...\n"
        "⏳ Will notify you when hot leads are found."
    )


def notify_agent_completed(total: int, hot: int, emails_sent: int) -> None:
    """Notify hunt completion summary."""
    send_telegram(
        f"✅ <b>Hunt Complete!</b>\n\n"
        f"📊 Total leads scanned: {total}\n"
        f"🔥 Hot leads found: {hot}\n"
        f"📧 Emails sent: {emails_sent}\n\n"
        f"The AI will monitor replies and notify you of confirmations!"
    )


def notify_reply_received(from_email: str, subject: str, summary: str, is_hot: bool) -> None:
    """Notify that a client replied to our outreach."""
    emoji = "🔥" if is_hot else "📩"
    label = "HOT REPLY — Client is interested!" if is_hot else "New Reply Received"

    send_telegram(
        f"{emoji} <b>{label}</b>\n\n"
        f"📧 From: {from_email}\n"
        f"📝 Subject: {subject}\n\n"
        f"💬 {summary}\n\n"
        f"✅ AI has auto-replied. Check Gmail for thread."
    )


def notify_error(error_msg: str) -> None:
    """Notify about a critical error."""
    send_telegram(f"❌ <b>Agent Error</b>\n\n{error_msg}")
