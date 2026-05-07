"""
job_hunter_agent/agent.py
==========================
THE MAIN ORCHESTRATOR
This is the master runner that connects all modules:
  1. Load your profile
  2. Search for leads worldwide
  3. AI scores and ranks every lead
  4. Send personalized outreach emails
  5. Check for replies and auto-respond
  6. Notify you on Telegram when a hot lead is confirmed

Run this file directly, or use scheduler.py to auto-run every 24h.
"""

import os
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv

# Our modules
from searcher import run_full_search
from ai_brain import rank_all_leads, write_outreach_email, analyze_client_reply, generate_hot_lead_summary
from emailer import send_outreach_email, get_new_replies, send_reply, find_contact_email
from notifier import (
    notify_agent_started,
    notify_agent_completed,
    notify_hot_lead,
    notify_reply_received,
    notify_error,
    send_telegram,
)
from tracker import (
    save_lead,
    update_lead_status,
    is_already_contacted,
    record_email_sent,
    add_reply_to_thread,
    get_all_sent_emails,
    record_hot_lead,
    get_email_thread,
    get_stats,
)

load_dotenv()

# ─────────────────────────────────────────────
#  LOGGING SETUP
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/agent.log", mode="a"),
    ],
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
AUTO_SEND = os.getenv("AUTO_SEND_EMAILS", "false").lower() == "true"
AUTO_REPLY = os.getenv("AUTO_REPLY_ENABLED", "true").lower() == "true"
MIN_SCORE = int(os.getenv("MIN_MATCH_SCORE", "65"))
MAX_LEADS = int(os.getenv("MAX_LEADS_PER_RUN", "20"))

PROFILE_FILE = Path(__file__).parent / "profile.json"


def load_profile() -> Dict:
    """Load the user's profile from profile.json."""
    with open(PROFILE_FILE) as f:
        return json.load(f)


# ─────────────────────────────────────────────
#  PHASE 1: HUNT — Find and Email leads
# ─────────────────────────────────────────────
def run_hunt(profile: Dict) -> int:
    """
    Full hunting cycle:
    - Search all platforms
    - AI score every lead
    - Send emails to top leads
    Returns: number of emails sent
    """
    logger.info("\n" + "="*60)
    logger.info("🚀 PHASE 1: HUNTING FOR LEADS")
    logger.info("="*60)

    # 1. Search all platforms
    all_leads = run_full_search(profile)

    # 2. Filter out already contacted
    new_leads = [
        lead for lead in all_leads
        if not is_already_contacted(lead.get("url", ""))
    ]
    logger.info(f"📋 New (uncontacted) leads: {len(new_leads)}")

    # 3. AI ranks all leads
    top_leads = rank_all_leads(new_leads, profile, min_score=MIN_SCORE)
    top_leads = top_leads[:MAX_LEADS]  # cap per run

    logger.info(f"\n🎯 Top {len(top_leads)} leads to contact:")
    for i, lead in enumerate(top_leads):
        logger.info(f"  {i+1}. [{lead['ai_score']}/100] {lead.get('title','')[:60]} ({lead.get('platform','')})")

    # 4. Send emails
    emails_sent = 0
    for lead in top_leads:
        save_lead(lead)

        # Try to get contact email
        contact_email = find_contact_email(lead)

        # For job platforms (Upwork/LinkedIn), we apply directly on the platform
        # For Google Maps outbound leads, we email them directly
        if not contact_email and lead.get("type") == "outbound_lead":
            logger.warning(f"  ⚠️  No email found for: {lead.get('company', '')} — skipping")
            continue

        # For job posts without a direct email, log for manual application
        if not contact_email:
            logger.info(f"  📌 MANUAL ACTION NEEDED: Apply at {lead.get('url', '')}")
            logger.info(f"     Platform: {lead.get('platform', '')} | Score: {lead.get('ai_score')}/100")

            # Write the email/proposal text anyway (for copy-paste)
            email_data = write_outreach_email(lead, profile, lead.get("ai_score_data", {}))
            lead["drafted_proposal"] = email_data
            save_lead(lead)

            # Save proposal to file for easy access
            proposals_dir = Path("data/proposals")
            proposals_dir.mkdir(parents=True, exist_ok=True)
            safe_title = "".join(c for c in lead.get("title", "lead")[:40] if c.isalnum() or c in " -_")
            proposal_file = proposals_dir / f"{safe_title}.txt"
            proposal_file.write_text(
                f"PLATFORM: {lead.get('platform')}\n"
                f"URL: {lead.get('url')}\n"
                f"SCORE: {lead.get('ai_score')}/100\n"
                f"SUBJECT: {email_data.get('subject')}\n\n"
                f"--- EMAIL/PROPOSAL BODY ---\n\n"
                f"{email_data.get('body')}\n"
            )
            logger.info(f"  📄 Proposal saved to: {proposal_file}")
            continue

        # AUTO SEND or manual approval
        email_data = write_outreach_email(lead, profile, lead.get("ai_score_data", {}))

        if AUTO_SEND:
            result = send_outreach_email(
                to_email=contact_email,
                subject=email_data["subject"],
                body=email_data["body"],
                lead_id=lead.get("url", ""),
            )
            if result:
                record_email_sent(
                    lead_id=lead.get("url", ""),
                    to_email=contact_email,
                    subject=email_data["subject"],
                    body=email_data["body"],
                    message_id=result["message_id"],
                    thread_id=result["thread_id"],
                )
                update_lead_status(lead.get("url", ""), "emailed")
                emails_sent += 1
                logger.info(f"  ✅ Email sent to {contact_email}")
                time.sleep(2)  # Be polite, don't spam
        else:
            # Save draft for manual review
            logger.info(f"\n  📧 DRAFT EMAIL (review before sending):")
            logger.info(f"  TO: {contact_email}")
            logger.info(f"  SUBJECT: {email_data['subject']}")
            logger.info(f"  BODY PREVIEW: {email_data['body'][:150]}...")
            send_telegram(
                f"📧 <b>New Draft Email Ready</b>\n\n"
                f"TO: {contact_email}\n"
                f"JOB: {lead.get('title', '')[:80]}\n"
                f"SCORE: {lead.get('ai_score')}/100\n\n"
                f"SUBJECT: {email_data['subject']}\n\n"
                f"✅ Set AUTO_SEND_EMAILS=true in .env to send automatically"
            )

    return emails_sent


# ─────────────────────────────────────────────
#  PHASE 2: REPLY — Check inbox and auto-respond
# ─────────────────────────────────────────────
def run_reply_check(profile: Dict) -> int:
    """
    Check Gmail for new replies and auto-respond.
    Returns: number of hot leads confirmed
    """
    logger.info("\n" + "="*60)
    logger.info("📬 PHASE 2: CHECKING REPLIES")
    logger.info("="*60)

    replies = get_new_replies()
    hot_count = 0
    all_sent = get_all_sent_emails()

    # Build a map: from_email → lead_id
    email_to_lead = {}
    for lead_id, email_data in all_sent.items():
        email_to_lead[email_data.get("to_email", "").lower()] = lead_id

    for reply in replies:
        from_email = reply.get("from_email", "").lower()

        # Extract just the email address from "Name <email>"
        if "<" in from_email:
            from_email = from_email.split("<")[1].replace(">", "").strip()

        # Find which lead this reply is for
        lead_id = email_to_lead.get(from_email)
        if not lead_id:
            logger.info(f"  📩 Reply from unknown sender: {reply['from_email']} — skipping")
            continue

        # Get original email thread
        thread = get_email_thread(lead_id)
        if not thread:
            continue

        lead_data = {"url": lead_id, "title": thread.get("subject", ""), "company": from_email}
        original_email = thread.get("body", "")

        logger.info(f"\n  📨 Reply from: {reply['from_email']}")
        logger.info(f"  Subject: {reply['subject']}")
        logger.info(f"  Preview: {reply['body'][:100]}...")

        # AI analyzes the reply
        analysis = analyze_client_reply(
            original_email=original_email,
            client_reply=reply["body"],
            lead=lead_data,
            profile=profile,
        )

        logger.info(f"  🤖 AI Classification: {analysis.get('reply_classification')}")
        logger.info(f"  🔥 Hot Lead: {analysis.get('is_hot_lead')}")

        # Record the reply
        add_reply_to_thread(lead_id, {
            "from": reply["from_email"],
            "body": reply["body"],
            "analysis": analysis,
        })

        # Notify about the reply
        notify_reply_received(
            from_email=reply["from_email"],
            subject=reply["subject"],
            summary=analysis.get("summary", ""),
            is_hot=analysis.get("is_hot_lead", False),
        )

        # Auto-reply if enabled
        if AUTO_REPLY and analysis.get("action_required") in ["SEND_REPLY", "SCHEDULE_CALL"]:
            send_reply(
                to_email=reply["from_email"],
                subject=reply["subject"],
                body=analysis.get("follow_up_body", ""),
                thread_id=reply.get("thread_id", ""),
                original_message_id=reply.get("message_id", ""),
            )
            logger.info(f"  ↩️  Auto-reply sent to {reply['from_email']}")

        # Handle hot leads
        if analysis.get("is_hot_lead"):
            hot_count += 1
            update_lead_status(lead_id, "hot")

            # Generate summary for user
            conversation = [original_email, reply["body"]]
            summary = generate_hot_lead_summary(lead_data, {}, conversation)

            # Record and notify
            record_hot_lead(lead_data, {}, summary)
            notify_hot_lead(lead_data, summary)

            logger.info(f"  🔥🔥 HOT LEAD CONFIRMED! Notified via Telegram.")

    return hot_count


# ─────────────────────────────────────────────
#  MAIN ENTRY POINT
# ─────────────────────────────────────────────
def main():
    """Run one complete cycle of the Job Hunter Agent."""
    logger.info("\n" + "🤖" * 30)
    logger.info("JOB & CLIENT HUNTER AGENT — STARTED")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("🤖" * 30 + "\n")

    # Load profile
    profile = load_profile()
    logger.info(f"👤 Profile: {profile.get('name')} | {profile.get('title')} | {profile.get('experience_years')}y exp")
    logger.info(f"🛠️  Skills: {', '.join(profile.get('skills', [])[:5])}")
    logger.info(f"💰 Rate: ${profile.get('hourly_rate_usd')}/hr\n")

    # Notify start
    notify_agent_started()

    try:
        # Phase 1: Hunt for new leads
        emails_sent = run_hunt(profile)

        # Phase 2: Check and reply to inbox
        gmail_creds = Path(os.getenv("GMAIL_CREDENTIALS_FILE", "credentials/gmail_credentials.json"))
        if not gmail_creds.exists():
            logger.warning("⚠️  Gmail credentials not found — skipping Phase 2 (reply check). "
                           "Download credentials JSON from Google Cloud Console to enable.")
            hot_count = 0
        else:
            hot_count = run_reply_check(profile)

        # Final stats
        stats = get_stats()
        logger.info("\n" + "="*60)
        logger.info("📊 SESSION STATS")
        logger.info("="*60)
        for k, v in stats.items():
            logger.info(f"  {k}: {v}")

        notify_agent_completed(
            total=stats["total_leads_found"],
            hot=stats["hot_leads_confirmed"],
            emails_sent=stats["emails_sent"],
        )

    except Exception as e:
        logger.exception(f"Agent crashed: {e}")
        notify_error(f"Agent error: {str(e)[:200]}")

    logger.info("\n✅ Agent run complete!\n")


if __name__ == "__main__":
    main()
