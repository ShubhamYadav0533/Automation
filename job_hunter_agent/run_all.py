#!/usr/bin/env python3
"""
run_all.py — Single command to run BOTH bots together:
  1. Job Hunter  (agent.py)      — searches LinkedIn/Freelancer/etc, saves proposals
  2. Client Hunter (client_hunter.py) — scrapes businesses, finds emails, sends pitches

Usage:
  python run_all.py               # Run both bots (live mode)
  python run_all.py --dry-run     # Run both but don't send emails
  python run_all.py --jobs-only   # Only run job hunter
  python run_all.py --clients-only # Only run client hunter
  python run_all.py --no-scrape   # Skip browser scraping for clients (use cache)
  python run_all.py --limit 5     # Max 5 client emails per run
"""

import sys
import argparse
import time
from datetime import datetime

# ─────────────────────────────────────────────────────────────
#  BANNER
# ─────────────────────────────────────────────────────────────
def print_banner(dry_run: bool):
    mode = "DRY RUN — no emails will be sent" if dry_run else "LIVE MODE — real emails will be sent"
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           🤖 SHUBHAM'S AUTOMATED INCOME MACHINE 🤖          ║
║                                                              ║
║   Bot 1: Job Hunter   → LinkedIn/Freelancer/Remote jobs      ║
║   Bot 2: Client Hunter → Businesses → Cold email pitches     ║
║                                                              ║
║   Mode: {mode:<52}║
║   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<50}║
╚══════════════════════════════════════════════════════════════╝
""")


# ─────────────────────────────────────────────────────────────
#  BOT 1: Job Hunter
# ─────────────────────────────────────────────────────────────
def run_job_hunter():
    print("\n" + "═"*64)
    print("  🔍 BOT 1 — JOB HUNTER")
    print("  Searching LinkedIn · Freelancer · WeWorkRemotely · Wellfound")
    print("═"*64 + "\n")

    try:
        # Import and run agent's main pipeline
        import importlib.util, os
        spec = importlib.util.spec_from_file_location(
            "agent",
            os.path.join(os.path.dirname(__file__), "agent.py")
        )
        agent_mod = importlib.util.load_from_spec(spec)
        spec.loader.exec_module(agent_mod)

        # agent.py runs its main() on import — check if it has an explicit main()
        if hasattr(agent_mod, "main"):
            agent_mod.main()
        print("\n  ✅ Job Hunter done!\n")
        return True
    except SystemExit:
        print("\n  ✅ Job Hunter finished (SystemExit — normal).\n")
        return True
    except Exception as e:
        print(f"\n  ❌ Job Hunter error: {e}\n")
        return False


# ─────────────────────────────────────────────────────────────
#  BOT 2: Client Hunter (pipeline mode)
# ─────────────────────────────────────────────────────────────
def run_client_hunter(dry_run: bool = False, no_scrape: bool = False, limit: int = 20):
    print("\n" + "═"*64)
    print("  📧 BOT 2 — CLIENT HUNTER")
    print("  Scraping businesses → Finding emails → Sending AI pitches")
    print("═"*64 + "\n")

    try:
        from client_hunter import (
            step1_get_businesses,
            step2_find_and_send_pipeline,
            _is_ollama_running,
            _print_step,
        )
        from ollama_writer import write_client_email
        from client_tracker import get_stats
    except ImportError as e:
        print(f"  ❌ Import error: {e}")
        return False

    # Pre-warm Ollama
    if _is_ollama_running():
        print("  🔥 Pre-warming Ollama mistral model...")
        try:
            import requests as _req
            _req.post(
                "http://localhost:11434/api/generate",
                json={"model": "mistral", "prompt": "hi", "stream": False,
                      "keep_alive": 600, "options": {"num_predict": 1}},
                timeout=210,
            )
            print("  ✅ Ollama warm!\n")
        except Exception:
            print("  ⚠️  Ollama pre-warm timed out — will retry per email\n")
    else:
        print("  ⚠️  Ollama not running — using built-in email templates\n")

    # Step 1 — scrape businesses
    businesses = step1_get_businesses(no_scrape=no_scrape)
    if not businesses:
        print("  ❌ No businesses found. Try without --no-scrape first.")
        return False

    print(f"\n  📋 {len(businesses)} businesses loaded")
    print(f"  🚀 Starting pipeline: find email → send immediately → next\n")

    # Step 2+3 — pipeline
    results = step2_find_and_send_pipeline(
        businesses,
        dry_run=dry_run,
        limit=limit,
    )

    stats = get_stats()

    print(f"""
  ┌─ CLIENT HUNTER RESULTS {'─'*38}
  │  Sent       : {results['sent']}
  │  No email   : {results['no_email']}
  │  Failed     : {results['failed']}
  │  Skipped    : {results['skipped']}
  │  DB total   : {stats.get('total', 0)}  (all-time)
  │  Total sent : {stats.get('email_sent', 0)}  (all-time)
  └{'─'*62}
""")
    return True


# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Run both Job Hunter + Client Hunter bots in one command"
    )
    parser.add_argument("--dry-run",      action="store_true", help="Don't send emails (preview only)")
    parser.add_argument("--jobs-only",    action="store_true", help="Only run Job Hunter bot")
    parser.add_argument("--clients-only", action="store_true", help="Only run Client Hunter bot")
    parser.add_argument("--no-scrape",    action="store_true", help="Client Hunter: use cached data, skip browser")
    parser.add_argument("--limit",        type=int, default=100, help="TARGET emails to send — bot keeps scraping until reached (default: 100)")
    args = parser.parse_args()

    start = datetime.now()
    print_banner(args.dry_run)

    job_ok    = True
    client_ok = True

    # ── BOT 1: Job Hunter ────────────────────────────────────
    if not args.clients_only:
        job_ok = run_job_hunter()
        if not args.jobs_only:
            print("\n  ⏳ Switching to Client Hunter in 3s...")
            time.sleep(3)
    else:
        print("  ⏭️  Skipping Job Hunter (--clients-only)")

    # ── BOT 2: Client Hunter ─────────────────────────────────
    if not args.jobs_only:
        client_ok = run_client_hunter(
            dry_run=args.dry_run,
            no_scrape=args.no_scrape,
            limit=args.limit,
        )
    else:
        print("  ⏭️  Skipping Client Hunter (--jobs-only)")

    # ── Final summary ─────────────────────────────────────────
    duration = int((datetime.now() - start).total_seconds())
    mins, secs = divmod(duration, 60)

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                  ALL BOTS FINISHED                           ║
╠══════════════════════════════════════════════════════════════╣
║  Bot 1 — Job Hunter   : {'✅ Done' if job_ok else '❌ Error':<51}║
║  Bot 2 — Client Hunter: {'✅ Done' if client_ok else '❌ Error':<51}║
║  Total time           : {f'{mins}m {secs}s':<51}║
╠══════════════════════════════════════════════════════════════╣
║  📁 Proposals : job_hunter_agent/data/proposals/             ║
║  📊 Clients   : job_hunter_agent/data/clients.xlsx           ║
║  📋 Leads DB  : job_hunter_agent/data/leads.json             ║
╚══════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
