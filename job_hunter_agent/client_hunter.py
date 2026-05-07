"""
job_hunter_agent/client_hunter.py
====================================
THE MAIN RUNNER — Client Hunter Bot
=====================================
Chains everything together:

  Step 1 → biz_scraper.py    — Chrome scrapes Google + Google Maps + JustDial
  Step 2 → contact_finder.py — Visit each website, extract email
  Step 3 → ollama_writer.py  — Local AI writes personalized pitch email
  Step 4 → emailer.py        — Gmail sends the email
  Step 5 → client_tracker.py — Saves everything to clients.json + clients.xlsx

Run:
  python client_hunter.py

Flags:
  python client_hunter.py --dry-run     # find leads but DON'T send emails
  python client_hunter.py --no-scrape   # skip browser scraping, use existing leads
  python client_hunter.py --limit 10    # only process 10 leads per run
"""

import os
import sys
import time
import logging
import argparse
import json
from datetime import datetime
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
def step1_get_businesses(no_scrape: bool = False) -> List[Dict]:
    cache_file = DATA_DIR / "scraped_businesses.json"

    if no_scrape and cache_file.exists():
        logger.info("📂 Loading cached businesses (--no-scrape mode)")
        return json.loads(cache_file.read_text())

    _print_step("🌐 STEP 1", "Scraping Google Search + Google Maps for businesses")
    print("  Opening Chrome browser...")
    print("  Searching: hospitals, clinics, hotels, schools, real estate in Amsterdam/Dubai/London/Berlin...")
    logger.info("🌐 STEP 1: Scraping Google + Maps for businesses...")
    businesses = scrape_businesses(
        max_google_searches=8,
        max_maps_searches=5,
        include_india=True,
    )

    # Cache results
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
#  MAIN
# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Client Hunter Bot — find businesses and pitch your services")
    parser.add_argument("--dry-run",   action="store_true", help="Find leads but DON'T send emails")
    parser.add_argument("--no-scrape", action="store_true", help="Skip browser, use cached data (first round only)")
    parser.add_argument("--limit",     type=int, default=MAX_PER_RUN, help="TARGET: how many emails to send total (keeps scraping until reached)")
    parser.add_argument("--test-ai",   action="store_true", help="Test Ollama + template writer only")
    args = parser.parse_args()

    # ── Quick AI test mode ────────────────────────────────────
    if args.test_ai:
        print(f"\n🤖 Ollama running: {_is_ollama_running()}\n")
        result = write_client_email("City Hospital Amsterdam", "hospital", "Dr. Van Berg", "https://example.com")
        print(f"Subject: {result['subject']}\n\nBody:\n{result['body']}")
        return

    start_time = datetime.now()
    target = args.limit  # e.g. 100 — keep going until this many sent

    banner = f"""
╔══════════════════════════════════════════════════════╗
║          CLIENT HUNTER BOT — Shubham Yadav           ║
║  Find businesses → Extract emails → Send pitches     ║
║  Mode  : {'DRY RUN (no emails)' if args.dry_run else 'LIVE (sending emails)':^40}  ║
║  Target: {f'Send {target} emails (scrapes new batches until done)':^40}  ║
╚══════════════════════════════════════════════════════╝
"""
    print(banner)

    # ── Pre-warm Ollama once ──────────────────────────────────
    if _is_ollama_running():
        print("🔥 Pre-warming Ollama mistral model (first load ~2 min)...")
        import requests as _req
        try:
            _req.post("http://localhost:11434/api/generate",
                json={"model": "mistral", "prompt": "hi", "stream": False,
                      "keep_alive": 600, "options": {"num_predict": 1}},
                timeout=210)
            print("✅ Ollama model warm and ready!\n")
        except Exception:
            print("⚠️  Ollama pre-warm timed out — will retry per email\n")

    # ── MAIN LOOP — keep scraping until target emails sent ────
    total_sent    = 0
    total_no_email = 0
    total_failed  = 0
    total_scraped = 0
    round_num     = 0
    MAX_ROUNDS    = 20   # safety cap — never infinite
    STALL_LIMIT   = 3    # stop if 3 consecutive rounds find 0 new emails

    stall_count   = 0
    cache_file    = DATA_DIR / "scraped_businesses.json"

    # ── Load already-processed business names for resume ─────
    clients_file = DATA_DIR / "clients.json"
    already_processed: set = set()
    if clients_file.exists():
        try:
            existing = json.loads(clients_file.read_text())
            already_processed = set(existing.keys())
            if already_processed:
                print(f"  📂 Resuming: {len(already_processed)} businesses already processed — will skip them\n")
        except Exception:
            pass

    while total_sent < target and round_num < MAX_ROUNDS:
        round_num += 1
        remaining = target - total_sent

        print(f"\n{'━'*62}")
        print(f"  🔄 ROUND {round_num}  |  Sent so far: {total_sent}/{target}  |  Need {remaining} more")
        print(f"{'━'*62}")

        # Round 1 can use --no-scrape cache; after that always scrape fresh
        use_cache = args.no_scrape and round_num == 1

        businesses = step1_get_businesses(no_scrape=use_cache)
        if not businesses:
            print("  ❌ No businesses found — stopping.")
            break

        total_scraped += len(businesses)

        # ── Filter out already-processed businesses ───────────
        fresh = [b for b in businesses if b.get("name", "") not in already_processed]
        skipped_resume = len(businesses) - len(fresh)
        if skipped_resume:
            print(f"  ⏭️  Skipping {skipped_resume} already-processed businesses from this batch")
        if not fresh:
            stall_count += 1
            print(f"  ⚠️  All businesses in this round already processed ({stall_count}/{STALL_LIMIT})")
            if stall_count >= STALL_LIMIT:
                print("  🛑 Nothing new to process — stopping.")
                break
            if cache_file.exists():
                cache_file.unlink()
            time.sleep(30)
            continue

        _print_step(
            "🚀 PIPELINE",
            f"Round {round_num} | Find email → Send instantly | need {remaining} more"
        )

        results = step2_find_and_send_pipeline(
            fresh,
            dry_run=args.dry_run,
            limit=remaining,  # only send what's still needed
        )

        # Track newly processed names for resume
        already_processed.update(b.get("name", "") for b in fresh)

        total_sent     += results["sent"]
        total_no_email += results["no_email"]
        total_failed   += results["failed"]

        print(f"\n  📊 Round {round_num} result: sent={results['sent']}  no_email={results['no_email']}  failed={results['failed']}")
        print(f"  📈 Progress: {total_sent}/{target} emails sent")

        # Stall detection — if a whole round found nothing to send, count it
        if results["sent"] == 0 and results["no_email"] == len(businesses):
            stall_count += 1
            print(f"  ⚠️  No emails found in this round ({stall_count}/{STALL_LIMIT} stall rounds)")
            if stall_count >= STALL_LIMIT:
                print(f"  🛑 3 rounds with no results — stopping to avoid wasting resources.")
                break
        else:
            stall_count = 0  # reset on any progress

        # Remove cache after round 1 so next round scrapes fresh
        if cache_file.exists() and not args.no_scrape:
            cache_file.unlink()

        if total_sent < target:
            print(f"\n  ⏳ Cooling down 30s before next scrape round...")
            time.sleep(30)

    # ── Final Summary ─────────────────────────────────────────
    duration = (datetime.now() - start_time).seconds
    mins, secs = divmod(duration, 60)
    stats = get_stats()

    reached = total_sent >= target
    status_icon = "✅ TARGET REACHED" if reached else f"⚠️  Stopped at {total_sent}/{target}"

    summary = f"""
╔══════════════════════════════════════════════════════╗
║                    RUN COMPLETE                      ║
╠══════════════════════════════════════════════════════╣
║  Status             : {status_icon:<31}║
║  Rounds run         : {round_num:<31}║
║  Businesses scraped : {total_scraped:<31}║
║  Emails sent        : {total_sent:<31}║
║  No email found     : {total_no_email:<31}║
║  Failed/Bounced     : {total_failed:<31}║
║  Duration           : {f'{mins}m {secs}s':<31}║
╠══════════════════════════════════════════════════════╣
║  ALL-TIME STATS                                      ║
║  Total in DB        : {stats.get('total', 0):<31}║
║  Emails sent (total): {stats.get('email_sent', 0):<31}║
║  Replied            : {stats.get('replied', 0):<31}║
║  Converted          : {stats.get('converted', 0):<31}║
╠══════════════════════════════════════════════════════╣
║  📊 Excel: data/clients.xlsx                         ║
║  📋 JSON:  data/clients.json                         ║
║  📄 Log:   data/client_hunter.log                    ║
╚══════════════════════════════════════════════════════╝
"""
    print(summary)

    if NOTIFIER_OK and total_sent > 0:
        try:
            send_telegram(
                f"🎯 Client Hunter Done!\n"
                f"{'✅ TARGET HIT' if reached else '⚠️ Partial'}: {total_sent}/{target} emails sent\n"
                f"Rounds: {round_num} | Scraped: {total_scraped}\n"
                f"All-time sent: {stats.get('email_sent', 0)}"
            )
        except Exception:
            pass


if __name__ == "__main__":
    main()
