#!/usr/bin/env python3
"""Check Gmail inbox and categorize all replies."""
import imaplib, email as email_lib, os, sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

sender = os.getenv("GMAIL_SENDER_EMAIL")
pwd    = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")

print(f"📬 Connecting to Gmail ({sender})...")
imap = imaplib.IMAP4_SSL("imap.gmail.com")
imap.login(sender, pwd)
imap.select("INBOX")

# Only check last 7 days using IMAP date search
_, nums = imap.search(None, "SINCE", "01-May-2026")
all_msgs = nums[0].split()
# Take last 80 max to avoid slowness
all_msgs = all_msgs[-80:]
print(f"📥 Checking {len(all_msgs)} recent messages...\n")

bounced, auto_reply, real_reply = [], [], []

for num in all_msgs:
    _, data = imap.fetch(num, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
    if not data or not data[0]:
        continue
    raw_headers = data[0][1] if isinstance(data[0], tuple) else b""
    msg  = email_lib.message_from_bytes(raw_headers)
    frm  = msg.get("From", "")
    subj = msg.get("Subject", "")
    dt   = msg.get("Date", "")
    body = ""   # headers-only pass — no body needed for categorisation

    entry = {"from": frm, "subject": subj, "date": dt, "body": body.strip()}

    frm_l  = frm.lower()
    subj_l = subj.lower()

    if "mailer-daemon" in frm_l or "delivery status" in subj_l or "delivery status notification" in subj_l:
        bounced.append(entry)
    elif any(x in subj_l for x in ["automatic reply", "auto-reply", "autoreply",
                                    "out of office", "autoresponse", "auto response",
                                    "welcome email", "crm:", "noreply", "no-reply"]):
        auto_reply.append(entry)
    elif any(x in frm_l for x in ["noreply", "no-reply", "notifications@github",
                                   "mailer", "postmaster", "daemon"]):
        auto_reply.append(entry)
    else:
        real_reply.append(entry)

imap.logout()

# ── REAL REPLIES ─────────────────────────────────────────────
print("=" * 60)
print(f"  💬  REAL REPLIES  ({len(real_reply)})")
print("=" * 60)
if real_reply:
    for i, r in enumerate(real_reply, 1):
        print(f"\n  [{i}] FROM   : {r['from']}")
        print(f"      SUBJECT: {r['subject']}")
        print(f"      DATE   : {r['date']}")
else:
    print("  — No real replies yet")

# ── AUTO-REPLIES ─────────────────────────────────────────────
print(f"\n{'=' * 60}")
print(f"  🤖  AUTO-REPLIES  ({len(auto_reply)})  (out-of-office / welcome emails)")
print("=" * 60)
if auto_reply:
    for i, r in enumerate(auto_reply, 1):
        print(f"\n  [{i}] FROM   : {r['from']}")
        print(f"      SUBJECT: {r['subject']}")
        print(f"      DATE   : {r['date']}")
else:
    print("  — None")

# ── BOUNCED ──────────────────────────────────────────────────
print(f"\n{'=' * 60}")
print(f"  ❌  BOUNCED / DELIVERY FAILURES  ({len(bounced)})")
print("=" * 60)
if bounced:
    for i, r in enumerate(bounced, 1):
        # Extract failed address from body
        failed = ""
        for line in r["body"].splitlines():
            if "Final-Recipient" in line or "failed" in line.lower() or "@" in line:
                failed = line.strip()
                break
        print(f"  [{i}] DATE: {r['date'][:25]}  |  {failed[:80]}")
else:
    print("  — No bounces")

print(f"\n{'=' * 60}")
print(f"  📊  SUMMARY: {len(real_reply)} real  |  {len(auto_reply)} auto  |  {len(bounced)} bounced")
print("=" * 60)
