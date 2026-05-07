#!/usr/bin/env python3
"""
auto_runner.py
===============
Lightweight scheduler — runs client_hunter.py every day at 9:00 AM.
Starts automatically when internet is available.

Usage (run once in background, stays alive):
  python auto_runner.py &

Or add to crontab for auto-start on login:
  crontab -e
  @reboot python3 /home/shubham/automation/job_hunter_agent/auto_runner.py &

This script:
  1. Waits until internet is connected
  2. Checks if today's run is already done
  3. Runs client_hunter.py --limit 100
  4. Repeats daily at 9:00 AM
"""

import os
import sys
import time
import socket
import subprocess
import logging
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            str(Path(__file__).parent / "data" / "autorun.log"),
            mode="a"
        ),
    ],
)
logger = logging.getLogger(__name__)

BOT_DIR     = Path(__file__).parent
LAST_RUN    = BOT_DIR / "data" / "last_autorun.txt"
RUN_HOUR    = 9    # 9:00 AM daily
RUN_MINUTE  = 0
DAILY_TARGET = 100


def is_internet_up() -> bool:
    """Check if internet is reachable."""
    try:
        socket.setdefaulttimeout(5)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        return True
    except Exception:
        return False


def already_ran_today() -> bool:
    """Check if we already completed today's run."""
    if not LAST_RUN.exists():
        return False
    try:
        last = LAST_RUN.read_text().strip()
        return last == datetime.now().strftime("%Y-%m-%d")
    except Exception:
        return False


def mark_ran_today():
    LAST_RUN.parent.mkdir(exist_ok=True)
    LAST_RUN.write_text(datetime.now().strftime("%Y-%m-%d"))


def run_bot():
    """Run client_hunter.py and wait for it to finish."""
    logger.info(f"🤖 Starting Client Hunter Bot — target {DAILY_TARGET} emails...")
    cmd = [sys.executable, str(BOT_DIR / "client_hunter.py"), "--limit", str(DAILY_TARGET)]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(BOT_DIR),
            timeout=8 * 3600,   # max 8 hours per run
        )
        if result.returncode == 0:
            logger.info("✅ Bot finished successfully")
        else:
            logger.warning(f"⚠️  Bot exited with code {result.returncode}")
    except subprocess.TimeoutExpired:
        logger.warning("⚠️  Bot exceeded 8-hour timeout — stopping")
    except Exception as e:
        logger.error(f"❌ Bot run error: {e}")


def seconds_until_next_run() -> float:
    """Seconds until next 9:00 AM."""
    now = datetime.now()
    target = now.replace(hour=RUN_HOUR, minute=RUN_MINUTE, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def main():
    logger.info("🕐 Auto Runner started — will run client_hunter.py daily at 09:00 AM")
    logger.info(f"   Bot directory: {BOT_DIR}")

    first_run_done = False

    while True:
        # ── Wait for internet ────────────────────────────────
        if not is_internet_up():
            logger.info("📡 Waiting for internet connection...")
            while not is_internet_up():
                time.sleep(15)
            logger.info("📡 Internet connected!")

        now = datetime.now()

        # ── First launch: run immediately if not done today ──
        if not first_run_done and not already_ran_today():
            logger.info("🚀 First launch — running bot now (not yet run today)")
            mark_ran_today()
            run_bot()
            first_run_done = True
            continue

        # ── Daily schedule: wait until 9 AM ─────────────────
        wait_sec = seconds_until_next_run()
        next_run = datetime.now() + timedelta(seconds=wait_sec)
        logger.info(f"⏰ Next run scheduled: {next_run.strftime('%Y-%m-%d %H:%M')} "
                    f"(in {int(wait_sec/3600)}h {int((wait_sec%3600)/60)}m)")

        # Sleep in chunks so we can detect internet drops
        slept = 0
        while slept < wait_sec:
            time.sleep(min(60, wait_sec - slept))
            slept += 60
            if not is_internet_up():
                logger.info("📡 Internet dropped — will wait for reconnect before running")
                break

        # Check again after waking
        if not is_internet_up():
            continue

        if already_ran_today():
            logger.info("⏭️  Already ran today — waiting for tomorrow")
            time.sleep(3600)
            continue

        logger.info(f"⏰ Time to run! {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        mark_ran_today()
        run_bot()
        first_run_done = True


if __name__ == "__main__":
    main()
