"""
job_hunter_agent/scheduler.py
==============================
Auto-runs the agent on a schedule (every 24 hours by default).
Also checks for replies every 2 hours in between hunts.

Run this with: python scheduler.py
Leave it running in the background — it will work for you 24/7!
"""

import os
import time
import logging
import schedule
from datetime import datetime
from dotenv import load_dotenv

import agent

load_dotenv()
logger = logging.getLogger(__name__)

HUNT_INTERVAL_HOURS = int(os.getenv("AGENT_RUN_INTERVAL_HOURS", "24"))
REPLY_CHECK_INTERVAL_MINUTES = 120  # Check replies every 2 hours


def run_full_cycle():
    """Run the complete hunt + reply check cycle."""
    logger.info(f"\n⏰ Scheduled run at {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    agent.main()


def run_reply_check_only():
    """Check for new replies without running a full hunt."""
    logger.info(f"\n📬 Reply check at {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    profile = agent.load_profile()
    agent.run_reply_check(profile)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("data/scheduler.log", mode="a"),
        ],
    )

    logger.info("=" * 60)
    logger.info("🤖 JOB HUNTER SCHEDULER STARTED")
    logger.info(f"📅 Full hunt: every {HUNT_INTERVAL_HOURS} hours")
    logger.info(f"📬 Reply check: every {REPLY_CHECK_INTERVAL_MINUTES} minutes")
    logger.info("=" * 60)

    # Run immediately on start
    run_full_cycle()

    # Schedule full hunt
    schedule.every(HUNT_INTERVAL_HOURS).hours.do(run_full_cycle)

    # Schedule reply checks in between hunts
    schedule.every(REPLY_CHECK_INTERVAL_MINUTES).minutes.do(run_reply_check_only)

    # Keep running
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute


if __name__ == "__main__":
    main()
