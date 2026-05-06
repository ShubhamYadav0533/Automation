"""
job_hunter_agent/tracker.py
============================
JSON-based local database to track:
  - All leads found
  - Emails sent
  - Conversations (thread history)
  - Hot leads confirmed
  - What has already been contacted (avoid duplicates)
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
LEADS_FILE = DATA_DIR / "leads.json"
EMAILS_FILE = DATA_DIR / "emails_sent.json"
HOT_LEADS_FILE = DATA_DIR / "hot_leads.json"
THREADS_FILE = DATA_DIR / "threads.json"


def _load(path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))


# ─────────────────────────────────────────────
#  LEADS
# ─────────────────────────────────────────────
def save_lead(lead: Dict) -> str:
    """Save a lead to the database. Returns lead_id."""
    leads = _load(LEADS_FILE)
    lead_id = lead.get("url", "") or f"lead_{datetime.now().timestamp()}"
    lead["saved_at"] = datetime.now().isoformat()
    lead["status"] = lead.get("status", "found")
    leads[lead_id] = lead
    _save(LEADS_FILE, leads)
    return lead_id


def get_lead(lead_id: str) -> Optional[Dict]:
    leads = _load(LEADS_FILE)
    return leads.get(lead_id)


def update_lead_status(lead_id: str, status: str) -> None:
    """Update lead status: found → emailed → replied → hot → closed"""
    leads = _load(LEADS_FILE)
    if lead_id in leads:
        leads[lead_id]["status"] = status
        leads[lead_id]["updated_at"] = datetime.now().isoformat()
        _save(LEADS_FILE, leads)


def is_already_contacted(lead_url: str) -> bool:
    """Check if we already sent an email for this lead URL."""
    emails = _load(EMAILS_FILE)
    return lead_url in emails


def get_all_leads() -> List[Dict]:
    leads = _load(LEADS_FILE)
    return list(leads.values())


def get_hot_leads() -> List[Dict]:
    hot = _load(HOT_LEADS_FILE)
    return list(hot.values())


# ─────────────────────────────────────────────
#  EMAILS SENT
# ─────────────────────────────────────────────
def record_email_sent(
    lead_id: str,
    to_email: str,
    subject: str,
    body: str,
    message_id: str,
    thread_id: str,
) -> None:
    """Record that an email was sent for a lead."""
    emails = _load(EMAILS_FILE)
    emails[lead_id] = {
        "lead_id": lead_id,
        "to_email": to_email,
        "subject": subject,
        "body": body,
        "message_id": message_id,
        "thread_id": thread_id,
        "sent_at": datetime.now().isoformat(),
        "replies": [],
    }
    _save(EMAILS_FILE, emails)


def add_reply_to_thread(lead_id: str, reply: Dict) -> None:
    """Add a client reply to the email thread record."""
    emails = _load(EMAILS_FILE)
    if lead_id in emails:
        emails[lead_id]["replies"].append({
            **reply,
            "received_at": datetime.now().isoformat(),
        })
        _save(EMAILS_FILE, emails)


def get_email_thread(lead_id: str) -> Optional[Dict]:
    emails = _load(EMAILS_FILE)
    return emails.get(lead_id)


def get_all_sent_emails() -> Dict:
    return _load(EMAILS_FILE)


# ─────────────────────────────────────────────
#  HOT LEADS
# ─────────────────────────────────────────────
def record_hot_lead(lead: Dict, score_data: Dict, conversation_summary: str) -> None:
    """Record a confirmed hot lead."""
    hot = _load(HOT_LEADS_FILE)
    lead_id = lead.get("url", f"hot_{datetime.now().timestamp()}")
    hot[lead_id] = {
        "lead": lead,
        "score_data": score_data,
        "conversation_summary": conversation_summary,
        "confirmed_at": datetime.now().isoformat(),
        "status": "hot",
    }
    _save(HOT_LEADS_FILE, hot)
    logger.info(f"🔥 Hot lead saved: {lead.get('title', '')}")


# ─────────────────────────────────────────────
#  STATS
# ─────────────────────────────────────────────
def get_stats() -> Dict:
    """Return overall agent statistics."""
    leads = _load(LEADS_FILE)
    emails = _load(EMAILS_FILE)
    hot = _load(HOT_LEADS_FILE)

    total_leads = len(leads)
    emails_sent = len(emails)
    total_replies = sum(len(e.get("replies", [])) for e in emails.values())
    hot_leads = len(hot)

    return {
        "total_leads_found": total_leads,
        "emails_sent": emails_sent,
        "replies_received": total_replies,
        "hot_leads_confirmed": hot_leads,
        "conversion_rate": f"{(hot_leads/emails_sent*100):.1f}%" if emails_sent > 0 else "0%",
    }
