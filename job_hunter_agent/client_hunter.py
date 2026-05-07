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
#  STEP 2: Find contact email for each business
# ─────────────────────────────────────────────────────────────
def step2_find_emails(businesses: List[Dict]) -> List[Dict]:
    logger.info(f"📧 STEP 2: Finding contact emails for {len(businesses)} businesses...")
    enriched = []

    for i, biz in enumerate(businesses):
        name = biz.get("name", "?")
        website = biz.get("website", "")

        # Save to tracker first (even without email yet)
        save_client_lead(biz)

        if is_already_contacted(name):
            logger.info(f"  ⏭️  Skipping (already contacted): {name}")
            continue

        if not website:
            logger.debug(f"  ⚠️  No website for: {name} — trying Google")
            # Try to find website via Google search
            website = _find_website_via_google(name, biz.get("city", ""))
            biz["website"] = website

        if website:
            logger.info(f"  [{i+1}/{len(businesses)}] Checking: {name}")
            contact = find_contact_info(website)
            biz.update({
                "email": contact["email"],
                "phone": contact["phone"] or biz.get("phone", ""),
                "contact_name": contact["contact_name"],
            })
            update_client_contact(
                name,
                email=contact["email"] or "",
                phone=contact["phone"] or "",
                contact_name=contact["contact_name"] or "",
            )

        if biz.get("email"):
            enriched.append(biz)
            logger.info(f"  ✅ {name} → {biz['email']}")
        else:
            update_client_status(name, "no_email")
            logger.debug(f"  ❌ No email: {name}")

        time.sleep(1.0)  # polite crawl delay

    logger.info(f"📬 {len(enriched)} businesses have contact emails")
    return enriched


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


# ─────────────────────────────────────────────────────────────
#  STEP 3 + 4: Write email with Ollama → Send with Gmail
# ─────────────────────────────────────────────────────────────
def step3_write_and_send(
    businesses: List[Dict],
    dry_run: bool = False,
    limit: int = MAX_PER_RUN,
) -> Dict:
    if not GMAIL_SENDER and not dry_run:
        logger.error("❌ GMAIL_SENDER_EMAIL not set in .env — cannot send emails")
        logger.error("   Add: GMAIL_SENDER_EMAIL=yourname@gmail.com")
        logger.error("   Add: GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx")
        return {"sent": 0, "failed": 0, "skipped": 0}

    ollama_ok = _is_ollama_running()
    if not ollama_ok:
        logger.warning("⚠️  Ollama not running — emails will use built-in templates")
        logger.warning("   To enable AI: run 'ollama serve' in another terminal")

    sent = 0
    failed = 0
    skipped = 0

    for biz in businesses[:limit]:
        name = biz.get("name", "?")
        to_email = biz.get("email", "")

        if not to_email:
            skipped += 1
            continue

        if is_already_contacted(name):
            skipped += 1
            continue

        logger.info(f"\n📝 Writing email for: {name} ({biz.get('category')}) → {to_email}")

        # ── Write email ──────────────────────────────────────
        email_data = write_client_email(
            business_name=name,
            category=biz.get("category", "business"),
            contact_name=biz.get("contact_name", ""),
            website=biz.get("website", ""),
        )

        subject = email_data["subject"]
        body = email_data["body"]
        used_ai = email_data["used_ai"]

        logger.info(f"  Subject: {subject}")
        logger.info(f"  AI used: {'✅ Ollama' if used_ai else '📄 Template'}")

        if dry_run:
            logger.info(f"  [DRY RUN] Would send to: {to_email}")
            logger.info(f"  Preview:\n{body[:200]}...")
            mark_email_sent(name, subject, used_ai)
            sent += 1
            continue

        # ── Send email ───────────────────────────────────────
        try:
            success = send_outreach_email(
                to_email=to_email,
                subject=subject,
                body=body,
                lead={"title": name, "company": name, "url": biz.get("website", "")},
            )

            if success:
                mark_email_sent(name, subject, used_ai)
                sent += 1
                logger.info(f"  ✅ Email sent to {to_email}")

                # Telegram ping
                if NOTIFIER_OK and sent <= 5:
                    try:
                        send_telegram(
                            f"📤 Email sent!\n"
                            f"Company: {name}\n"
                            f"Email: {to_email}\n"
                            f"Subject: {subject}\n"
                            f"AI: {'Ollama' if used_ai else 'Template'}"
                        )
                    except Exception:
                        pass

                # Polite delay between emails
                if sent < len(businesses):
                    logger.info(f"  ⏳ Waiting {DELAY_BETWEEN}s before next email...")
                    time.sleep(DELAY_BETWEEN)
            else:
                failed += 1
                logger.warning(f"  ❌ Failed to send to {to_email}")
                update_client_status(name, "bounced")

        except Exception as e:
            failed += 1
            logger.error(f"  ❌ Error sending to {name}: {e}")

    return {"sent": sent, "failed": failed, "skipped": skipped}


# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Client Hunter Bot — find businesses and pitch your services")
    parser.add_argument("--dry-run",   action="store_true", help="Find leads but DON'T send emails")
    parser.add_argument("--no-scrape", action="store_true", help="Skip browser scraping, use cached data")
    parser.add_argument("--limit",     type=int, default=MAX_PER_RUN, help="Max emails to send per run")
    parser.add_argument("--test-ai",   action="store_true", help="Test Ollama + template writer only")
    args = parser.parse_args()

    # ── Quick AI test mode ────────────────────────────────────
    if args.test_ai:
        print(f"\n🤖 Ollama running: {_is_ollama_running()}\n")
        result = write_client_email("City Hospital Amsterdam", "hospital", "Dr. Van Berg", "https://example.com")
        print(f"Subject: {result['subject']}\n\nBody:\n{result['body']}")
        return

    start_time = datetime.now()
    banner = f"""
╔══════════════════════════════════════════════════════╗
║          CLIENT HUNTER BOT — Shubham Yadav           ║
║  Find businesses → Extract emails → Send pitches     ║
║  Mode: {'DRY RUN (no emails)' if args.dry_run else 'LIVE (sending emails)':^40}  ║
╚══════════════════════════════════════════════════════╝
"""
    print(banner)

    # ── Pre-warm Ollama model so first email isn't slow ───────
    if _is_ollama_running():
        logger.info("🔥 Pre-warming Ollama model (first load takes ~2 min)...")
        import requests as _req
        try:
            _req.post("http://localhost:11434/api/generate",
                json={"model": "mistral", "prompt": "hi", "stream": False,
                      "keep_alive": 600, "options": {"num_predict": 1}},
                timeout=210)
            logger.info("✅ Ollama model is warm and ready")
        except Exception:
            logger.warning("⚠️  Ollama pre-warm timed out — will retry on first email")

    # ── Step 1: Scrape businesses ─────────────────────────────
    businesses = step1_get_businesses(no_scrape=args.no_scrape)
    if not businesses:
        if args.no_scrape:
            logger.error("❌ No cached businesses found. Run without --no-scrape first to collect leads.")
        else:
            logger.error("❌ No businesses found. Check your Chrome installation and internet connection.")
        sys.exit(1)

    # ── Step 2: Find emails ───────────────────────────────────
    with_emails = step2_find_emails(businesses)
    if not with_emails:
        logger.warning("⚠️  No businesses with email addresses found in this run.")

    # ── Step 3+4: Write + Send ────────────────────────────────
    if with_emails or args.dry_run:
        results = step3_write_and_send(
            with_emails,
            dry_run=args.dry_run,
            limit=args.limit,
        )
    else:
        results = {"sent": 0, "failed": 0, "skipped": 0}

    # ── Summary ───────────────────────────────────────────────
    duration = (datetime.now() - start_time).seconds
    stats = get_stats()

    summary = f"""
╔══════════════════════════════════════════════════════╗
║                    RUN COMPLETE                      ║
╠══════════════════════════════════════════════════════╣
║  Businesses scraped : {len(businesses):<31}║
║  Emails found       : {len(with_emails):<31}║
║  Emails sent        : {results['sent']:<31}║
║  Failed             : {results['failed']:<31}║
║  Skipped            : {results['skipped']:<31}║
║  Duration           : {duration}s{'':<28}║
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

    if NOTIFIER_OK and results["sent"] > 0:
        try:
            send_telegram(
                f"🎯 Client Hunter Run Complete!\n"
                f"Scraped: {len(businesses)}\n"
                f"Emails sent: {results['sent']}\n"
                f"Total in DB: {stats.get('total', 0)}"
            )
        except Exception:
            pass


if __name__ == "__main__":
    main()
