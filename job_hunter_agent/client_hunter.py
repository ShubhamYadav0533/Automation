"""
job_hunter_agent/client_hunter.py
====================================
THE MAIN RUNNER — Client Hunter Bot
=====================================
Priority order every run:
  1. Send follow-up to anyone emailed 3+ days ago with no reply yet
  2. Send to leads that already have email but haven't been emailed
  3. Scrape new businesses → find email → send immediately
  Keeps going until daily target (default 100) is reached.

Run:
  python client_hunter.py             # send 100 emails, never stop
  python client_hunter.py --limit 50  # custom target
  python client_hunter.py --dry-run   # preview only, don't send
  python client_hunter.py --no-scrape # use cached data first round
"""

import os
import sys
import time
import logging
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)

# Our modules
from biz_scraper import scrape_businesses
from contact_finder import find_contact_info
from ollama_writer import write_client_email, _is_ollama_running
from client_tracker import (
    save_client_lead,
    is_already_contacted,
    mark_email_sent,
    update_client_status,
    update_client_contact,
    get_stats,
)

# Gmail SMTP send (reuse from existing emailer.py)
from emailer import send_outreach_email

# Telegram notification (optional)
try:
    from notifier import send_telegram
    NOTIFIER_OK = True
except Exception:
    NOTIFIER_OK = False

# ─────────────────────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/client_hunter.log", mode="a"),
    ],
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  CONFIG (from .env)
# ─────────────────────────────────────────────────────────────
GMAIL_SENDER   = os.getenv("GMAIL_SENDER_EMAIL", "")
AUTO_SEND      = os.getenv("CLIENT_AUTO_SEND", "false").lower() == "true"
DELAY_BETWEEN  = int(os.getenv("EMAIL_DELAY_SECONDS", "45"))  # seconds between emails
MAX_PER_RUN    = int(os.getenv("MAX_CLIENTS_PER_RUN", "20"))

DATA_DIR = Path(__file__).parent / "data"


# ─────────────────────────────────────────────────────────────
#  STEP 1: Scrape or load cached businesses
# ─────────────────────────────────────────────────────────────
def step1_get_businesses(no_scrape: bool = False, round_offset: int = 0) -> List[Dict]:
    cache_file = DATA_DIR / "scraped_businesses.json"

    if no_scrape and cache_file.exists():
        logger.info("📂 Loading cached businesses (--no-scrape mode)")
        return json.loads(cache_file.read_text())

    _print_step("🌐 SCRAPING", f"Round offset {round_offset} — rotating keyword slice for fresh results")
    print("  Opening Chrome browser...")
    logger.info(f"🌐 Scraping round {round_offset}...")
    businesses = scrape_businesses(
        max_google_searches=10,
        max_maps_searches=5,
        include_india=True,
        round_offset=round_offset,
    )

    cache_file.write_text(json.dumps(businesses, indent=2, ensure_ascii=False))
    logger.info(f"✅ Found {len(businesses)} businesses. Saved to {cache_file.name}")
    return businesses


# ─────────────────────────────────────────────────────────────
#  STEP 2+3 PIPELINE: Find email → Send immediately → Next
# ─────────────────────────────────────────────────────────────
def step2_find_and_send_pipeline(
    businesses: List[Dict],
    dry_run: bool = False,
    limit: int = MAX_PER_RUN,
) -> Dict:
    """
    For each business:
      1. Visit website → find email
      2. If found → Ollama writes email → Gmail sends it  ← IMMEDIATELY
      3. Move to next business
    No waiting for all emails first.
    """
    if not GMAIL_SENDER and not dry_run:
        logger.error("❌ GMAIL_SENDER_EMAIL not set in .env")
        return {"sent": 0, "failed": 0, "skipped": 0, "no_email": 0}

    ollama_ok = _is_ollama_running()
    ai_label = "✅ Ollama mistral" if ollama_ok else "📄 Template"
    if not ollama_ok:
        print("  ⚠️  Ollama not running — using built-in email templates")

    sent = 0
    failed = 0
    skipped = 0
    no_email = 0
    processed = 0

    total = len(businesses)

    for i, biz in enumerate(businesses):
        if processed >= limit:
            break

        name    = biz.get("name", "?")
        website = biz.get("website", "")
        city    = biz.get("city", "")
        category = biz.get("category", "business")

        # ── Save & dedup ─────────────────────────────────────
        save_client_lead(biz)
        if is_already_contacted(name):
            print(f"  ⏭️  [{i+1}/{total}] Already contacted: {name[:50]}")
            skipped += 1
            continue

        print(f"\n{'═'*62}")
        print(f"  🏢 [{i+1}/{total}] {name}")
        print(f"  📍 {category.upper()} | {city}")

        # ── FIND website if missing ───────────────────────────
        if not website:
            print(f"  🔎 No website — searching Google for {name}...")
            website = _find_website_via_google(name, city)
            biz["website"] = website

        if not website:
            print(f"  ❌ No website found — skipping")
            update_client_status(name, "no_email")
            no_email += 1
            continue

        # ── FIND email ────────────────────────────────────────
        print(f"  🌐 Visiting: {website[:62]}")
        print(f"  🔍 Scanning /contact /about pages for email...")
        contact = find_contact_info(website)

        email       = contact["email"]
        phone       = contact["phone"] or biz.get("phone", "")
        contact_name = contact["contact_name"] or ""

        biz.update({"email": email, "phone": phone, "contact_name": contact_name})
        update_client_contact(name, email=email or "", phone=phone, contact_name=contact_name)

        if not email:
            print(f"  ❌ No email found on website")
            update_client_status(name, "no_email")
            no_email += 1
            time.sleep(0.8)
            continue

        print(f"  📧 Email found: {email}")
        processed += 1

        # ── WRITE email with AI ───────────────────────────────
        print(f"  🤖 AI writing personalized email ({ai_label})...")
        email_data = write_client_email(
            business_name=name,
            category=category,
            contact_name=contact_name,
            website=website,
        )
        subject  = email_data["subject"]
        body     = email_data["body"]
        used_ai  = email_data["used_ai"]

        # ── PRINT full email ──────────────────────────────────
        print(f"\n  ┌─ EMAIL {'(DRY RUN)' if dry_run else 'TO SEND'} {'─'*38}")
        print(f"  │  TO      : {email}")
        print(f"  │  SUBJECT : {subject}")
        print(f"  │  AI      : {'✅ Ollama mistral' if used_ai else '📄 Template'}")
        print(f"  ├{'─'*52}")
        for line in body.strip().split("\n"):
            print(f"  │  {line}")
        print(f"  └{'─'*52}")

        if dry_run:
            print(f"\n  🟡 DRY RUN — not sent")
            mark_email_sent(name, subject, used_ai)
            sent += 1
            continue

        # ── SEND ──────────────────────────────────────────────
        print(f"\n  📤 Sending via Gmail ({GMAIL_SENDER})...")
        try:
            success = send_outreach_email(
                to_email=email,
                subject=subject,
                body=body,
                lead_id=name,
            )
            if success:
                mark_email_sent(name, subject, used_ai)
                sent += 1
                print(f"  ✅ SENT → {email}")
                logger.info(f"Sent: {name} → {email} | {subject}")
                if NOTIFIER_OK:
                    try:
                        send_telegram(
                            f"📤 Cold email sent!\n👤 {name}\n📧 {email}\n📝 {subject}"
                        )
                    except Exception:
                        pass
                if processed < limit:
                    print(f"\n  ⏳ Waiting {DELAY_BETWEEN}s (spam filter safety)...")
                    for r in range(DELAY_BETWEEN, 0, -5):
                        print(f"     {r}s ...", end="\r", flush=True)
                        time.sleep(min(5, r))
                    print(" " * 20, end="\r")
            else:
                failed += 1
                print(f"  ❌ Gmail rejected — {email}")
                update_client_status(name, "bounced")
        except Exception as e:
            failed += 1
            print(f"  ❌ Error: {e}")
            logger.error(f"Send error {name}: {e}")

    return {"sent": sent, "failed": failed, "skipped": skipped, "no_email": no_email}


def _find_website_via_google(name: str, city: str) -> str:
    """Quick Google search to find a business website."""
    import requests
    try:
        query = f"{name} {city} official website"
        url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=8)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a[href^='http']"):
            href = a.get("href", "")
            if "google" not in href and "youtube" not in href and href.startswith("http"):
                return href
    except Exception:
        pass
    return ""


def _print_step(icon: str, message: str):
    print(f"\n{'═'*60}")
    print(f"  {icon}  {message}")
    print(f"{'═'*60}")


# ─────────────────────────────────────────────────────────────
#  DAILY STATS DASHBOARD
# ─────────────────────────────────────────────────────────────
def print_daily_stats():
    """Print how many emails sent today vs all-time."""
    clients_file = DATA_DIR / "clients.json"
    today = datetime.now().strftime("%Y-%m-%d")
    sent_today = 0
    pending_reply = 0
    replied = 0
    converted = 0
    total = 0

    if clients_file.exists():
        try:
            clients = json.loads(clients_file.read_text())
            total = len(clients)
            for v in clients.values():
                status = v.get("status", "")
                date_emailed = v.get("date_emailed", "")
                if status == "email_sent":
                    if date_emailed and date_emailed.startswith(today):
                        sent_today += 1
                    pending_reply += 1
                elif status == "replied":
                    replied += 1
                elif status == "converted":
                    converted += 1
        except Exception:
            pass

    print(f"""
  ┌─ TODAY'S STATS ({'─'*44}
  │  📤 Sent today          : {sent_today}
  │  ⏳ Awaiting reply      : {pending_reply}
  │  💬 Replied (all time)  : {replied}
  │  💰 Converted           : {converted}
  │  📋 Total in DB         : {total}
  └{'─'*54}""")
    return sent_today


# ─────────────────────────────────────────────────────────────
#  FOLLOW-UP EMAILS (priority 1)
# ─────────────────────────────────────────────────────────────
def send_followups(dry_run: bool = False, limit: int = 20) -> int:
    """
    Send follow-up emails to leads that:
    - Have status=email_sent
    - Were emailed 3+ days ago
    - Have not replied yet
    Returns number of follow-ups sent.
    """
    clients_file = DATA_DIR / "clients.json"
    if not clients_file.exists():
        return 0

    try:
        clients = json.loads(clients_file.read_text())
    except Exception:
        return 0

    cutoff = datetime.now() - timedelta(days=3)
    candidates = []
    for name, data in clients.items():
        if data.get("status") != "email_sent":
            continue
        date_str = data.get("date_emailed", "")
        if not date_str:
            continue
        try:
            emailed_at = datetime.fromisoformat(date_str.split("T")[0])
            if emailed_at <= cutoff:
                candidates.append((name, data))
        except Exception:
            continue

    if not candidates:
        print("  ✅ No follow-ups needed (no leads older than 3 days without reply)")
        return 0

    print(f"\n  📬 Found {len(candidates)} leads to follow up on (emailed 3+ days ago, no reply)")
    sent = 0

    for name, data in candidates[:limit]:
        if sent >= limit:
            break
        email = data.get("email", "")
        category = data.get("category", "default")
        website = data.get("website", "")
        contact_name = data.get("contact_name", "")

        if not email:
            continue

        print(f"\n  🔁 FOLLOW-UP: {name[:55]}")
        print(f"     📧 {email}  |  Originally emailed: {data.get('date_emailed','?')[:10]}")

        # Short follow-up email
        greeting = f"Hi {contact_name}," if contact_name else f"Hi {name} Team,"
        body = f"""{greeting}

I wanted to follow up on my previous message about building a custom digital system for {name}.

I understand you're busy — I'll keep this brief.

I've already built live systems like this for other businesses. If you have 10 minutes this week, I'd love to show you a quick demo that's directly relevant to your work.

No pressure at all — just thought it might be worth a look.

Best regards,
Shubham Yadav
Software Engineer & App Developer
shubhamyadav0533@gmail.com | https://github.com/ShubhamYadav0533"""

        subject = f"Re: Following up — {name}"

        if dry_run:
            print(f"     🟡 DRY RUN — follow-up not sent")
            sent += 1
            continue

        try:
            result = send_outreach_email(to_email=email, subject=subject, body=body, lead_id=f"followup_{name}")
            if result:
                # Update status to show follow-up sent
                clients[name]["date_emailed"] = datetime.now().isoformat()
                clients[name]["notes"] = "Follow-up sent"
                clients_file.write_text(json.dumps(clients, indent=2, ensure_ascii=False))
                sent += 1
                print(f"     ✅ Follow-up sent → {email}")
                time.sleep(DELAY_BETWEEN)
        except Exception as e:
            print(f"     ❌ Error: {e}")

    return sent


# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Client Hunter Bot — find businesses and pitch your services")
    parser.add_argument("--dry-run",   action="store_true", help="Find leads but DON'T send emails")
    parser.add_argument("--no-scrape", action="store_true", help="Skip browser, use cached data (first round only)")
    parser.add_argument("--limit",     type=int, default=100, help="TARGET: emails to send per run (default 100)")
    parser.add_argument("--test-ai",   action="store_true", help="Test Ollama + template writer only")
    args = parser.parse_args()

    # ── Quick AI test mode ────────────────────────────────────
    if args.test_ai:
        print(f"\n🤖 Ollama running: {_is_ollama_running()}\n")
        result = write_client_email("City Hospital Amsterdam", "hospital", "Dr. Van Berg", "https://example.com")
        print(f"Subject: {result['subject']}\n\nBody:\n{result['body']}")
        return

    start_time = datetime.now()
    target = args.limit

    print(f"""
╔══════════════════════════════════════════════════════════╗
║          CLIENT HUNTER BOT — Shubham Yadav               ║
║  Priority 1 → Follow-ups (no reply after 3 days)         ║
║  Priority 2 → Existing leads with email, not sent yet    ║
║  Priority 3 → Scrape new leads → find email → send       ║
║  Mode   : {'DRY RUN (preview only)' if args.dry_run else 'LIVE — real emails':^44}  ║
║  Target : {f'Send {target} emails today (runs until done)':^44}  ║
╚══════════════════════════════════════════════════════════╝""")

    # ── Daily stats ───────────────────────────────────────────
    sent_so_far_today = print_daily_stats()
    total_sent = sent_so_far_today  # count emails already sent today
    remaining = max(0, target - total_sent)

    if remaining == 0:
        print(f"\n  ✅ Already sent {total_sent} emails today — target reached!")
        return

    print(f"\n  🎯 Need to send {remaining} more emails today to reach target of {target}\n")

    # ── Pre-warm Ollama once ──────────────────────────────────
    if _is_ollama_running():
        print("🔥 Pre-warming Ollama mistral model...")
        import requests as _req
        try:
            _req.post("http://localhost:11434/api/generate",
                json={"model": "mistral", "prompt": "hi", "stream": False,
                      "keep_alive": 600, "options": {"num_predict": 1}},
                timeout=210)
            print("✅ Ollama warm!\n")
        except Exception:
            print("⚠️  Ollama pre-warm timed out\n")

    # ─────────────────────────────────────────────────────────
    #  PRE-RUN: Check Gmail for replies, update DB + Supabase
    # ─────────────────────────────────────────────────────────
    _print_step("📬 PRE-CHECK", "Scanning Gmail for new replies from leads...")
    try:
        from supabase_sync import check_and_update_replies
        new_replies = check_and_update_replies()
        if new_replies:
            print(f"  ✅ {new_replies} new replies detected — status updated to 'replied'")
        else:
            print("  — No new replies found")
    except Exception as _e:
        print(f"  ⚠️  Reply check skipped: {_e}")

    # ─────────────────────────────────────────────────────────
    #  PRIORITY 1: Send follow-ups to old no-reply leads
    # ─────────────────────────────────────────────────────────
    _print_step("🔁 PRIORITY 1", "Follow-ups to leads with no reply after 3 days")
    followup_sent = send_followups(dry_run=args.dry_run, limit=remaining)
    total_sent += followup_sent
    remaining = max(0, target - total_sent)
    print(f"  📊 Follow-ups sent: {followup_sent}  |  Progress: {total_sent}/{target}")

    if remaining == 0:
        _print_final_summary(start_time, total_sent, target, 0, 0)
        return

    # ─────────────────────────────────────────────────────────
    #  PRIORITY 2 + 3: Find email → Send → Scrape new if needed
    # ─────────────────────────────────────────────────────────
    _print_step("🚀 PRIORITY 2+3", f"Email existing leads + scrape new ones — need {remaining} more")

    total_scraped = 0
    total_no_email = 0
    total_failed = 0
    round_num = 0
    cache_file = DATA_DIR / "scraped_businesses.json"

    # Load already-processed names for dedup
    clients_file = DATA_DIR / "clients.json"
    already_processed: set = set()
    if clients_file.exists():
        try:
            already_processed = set(json.loads(clients_file.read_text()).keys())
        except Exception:
            pass

    # Never stop — keep looping with new keyword offsets until target hit
    while total_sent < target:
        round_num += 1
        remaining = target - total_sent

        print(f"\n{'━'*62}")
        print(f"  🔄 ROUND {round_num}  |  Sent: {total_sent}/{target}  |  Need {remaining} more")
        print(f"{'━'*62}")

        use_cache = args.no_scrape and round_num == 1
        businesses = step1_get_businesses(no_scrape=use_cache, round_offset=round_num - 1)

        if not businesses:
            print("  ⚠️  Scraper returned no results — retrying in 60s with next keyword set...")
            time.sleep(60)
            continue

        total_scraped += len(businesses)
        fresh = [b for b in businesses if b.get("name", "") not in already_processed]

        print(f"  📋 {len(businesses)} scraped  |  {len(fresh)} new (not yet processed)")

        if not fresh:
            print("  ⚠️  All businesses in this batch already processed — scraping next keyword set...")
            if cache_file.exists():
                cache_file.unlink()
            time.sleep(20)
            continue

        results = step2_find_and_send_pipeline(fresh, dry_run=args.dry_run, limit=remaining)
        already_processed.update(b.get("name", "") for b in fresh)

        total_sent     += results["sent"]
        total_no_email += results["no_email"]
        total_failed   += results["failed"]

        print(f"\n  📊 Round {round_num}: sent={results['sent']} | no_email={results['no_email']} | failed={results['failed']}")
        print(f"  📈 Progress: {total_sent}/{target} emails sent total today")

        if cache_file.exists():
            cache_file.unlink()

        if total_sent < target:
            print(f"  ⏳ Cooling 20s before next round...")
            time.sleep(20)

    _print_final_summary(start_time, total_sent, target, total_scraped, total_no_email)


def _print_final_summary(start_time, total_sent, target, scraped, no_email):
    duration = int((datetime.now() - start_time).total_seconds())
    mins, secs = divmod(duration, 60)
    stats = get_stats()
    reached = total_sent >= target

    print(f"""
╔══════════════════════════════════════════════════════════╗
║                  ✅ RUN COMPLETE                         ║
╠══════════════════════════════════════════════════════════╣
║  Status          : {'✅ TARGET REACHED' if reached else f'⚠️  {total_sent}/{target} sent':<41}║
║  Emails sent     : {total_sent:<41}║
║  No email found  : {no_email:<41}║
║  Businesses found: {scraped:<41}║
║  Duration        : {f'{mins}m {secs}s':<41}║
╠══════════════════════════════════════════════════════════╣
║  ALL-TIME                                                ║
║  Total in DB     : {stats.get('total', 0):<41}║
║  Ever sent       : {stats.get('email_sent', 0):<41}║
║  Replied         : {stats.get('replied', 0):<41}║
║  Converted       : {stats.get('converted', 0):<41}║
╠══════════════════════════════════════════════════════════╣
║  📊 data/clients.xlsx  📋 data/clients.json              ║
╚══════════════════════════════════════════════════════════╝
""")

    if NOTIFIER_OK and total_sent > 0:
        try:
            send_telegram(
                f"{'✅' if reached else '⚠️'} Client Hunter Done!\n"
                f"Sent today: {total_sent}/{target}\n"
                f"All-time: {stats.get('email_sent', 0)} sent | "
                f"{stats.get('replied', 0)} replied | "
                f"{stats.get('converted', 0)} converted"
            )
        except Exception:
            pass


if __name__ == "__main__":
    main()
