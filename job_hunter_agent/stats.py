#!/usr/bin/env python3
"""
stats.py — Full dashboard: all counts at a glance
Run: python stats.py
"""
import json
import os
from pathlib import Path
from datetime import date, datetime, timedelta
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

DATA_DIR    = Path(__file__).parent / "data"
JSON_FILE   = DATA_DIR / "clients.json"
LEADS_FILE  = DATA_DIR / "leads.json"

# ── Load data ────────────────────────────────────────────────
clients = json.loads(JSON_FILE.read_text()) if JSON_FILE.exists() else {}
leads   = json.loads(LEADS_FILE.read_text()) if LEADS_FILE.exists() else {}

today     = date.today().isoformat()
yesterday = (date.today() - timedelta(days=1)).isoformat()

# ── Compute stats ────────────────────────────────────────────
total           = len(clients)
has_email       = sum(1 for v in clients.values() if v.get("email"))
no_email        = sum(1 for v in clients.values() if not v.get("email"))

email_sent_all  = sum(1 for v in clients.values() if v.get("status") == "email_sent")
replied_all     = sum(1 for v in clients.values() if v.get("status") == "replied")
converted_all   = sum(1 for v in clients.values() if v.get("status") == "converted")
bounced_all     = sum(1 for v in clients.values() if v.get("status") == "bounced")

found_today     = sum(1 for v in clients.values() if str(v.get("date_found","")).startswith(today))
sent_today      = sum(1 for v in clients.values() if str(v.get("date_emailed","")).startswith(today))
found_yesterday = sum(1 for v in clients.values() if str(v.get("date_found","")).startswith(yesterday))
sent_yesterday  = sum(1 for v in clients.values() if str(v.get("date_emailed","")).startswith(yesterday))

# Follow-up = emailed but no reply, sent 3+ days ago
cutoff = (datetime.now() - timedelta(days=3)).date().isoformat()
followup_needed = sum(
    1 for v in clients.values()
    if v.get("status") == "email_sent"
    and str(v.get("date_emailed",""))[:10] <= cutoff
    and str(v.get("date_emailed",""))[:10] != ""
)
followup_sent = sum(
    1 for v in clients.values()
    if "follow" in str(v.get("notes","")).lower()
)

# Leads from leads.json
job_leads = len(leads) if isinstance(leads, (dict, list)) else 0

# Supabase stats
sb_stats = None
try:
    from supabase_sync import get_supabase_stats, is_configured
    if is_configured():
        sb_stats = get_supabase_stats()
except Exception:
    pass

# ── Print dashboard ──────────────────────────────────────────
W = 54
def line(label, value, icon=""):
    val = str(value)
    pad = W - len(icon) - len(label) - len(val) - 4
    print(f"  {icon} {label}{'.' * max(1,pad)}{val}")

print()
print("╔" + "═"*W + "╗")
print("║" + "  📊  CLIENT HUNTER STATS DASHBOARD  ".center(W) + "║")
print("║" + f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}".ljust(W) + "║")
print("╠" + "═"*W + "╣")

print("║" + "  🗃️  ALL-TIME TOTALS".ljust(W) + "║")
print("║" + "─"*W + "║")
line("Total businesses found",    total,          "🏢")
line("Have email address",         has_email,      "📧")
line("No email found",             no_email,       "❌")
line("Emails sent (all time)",     email_sent_all, "📤")
line("Replies received",           replied_all,    "💬")
line("Converted to clients",       converted_all,  "💰")
line("Bounced / invalid",          bounced_all,    "⚠️ ")
line("Job leads (leads.json)",     job_leads,      "💼")

print("║" + "─"*W + "║")
print("║" + "  📅  TODAY  (" + today + ")".ljust(W - 17) + "║")
print("║" + "─"*W + "║")
line("Businesses found today",     found_today,    "🔍")
line("Emails sent today",          sent_today,     "📨")

print("║" + "─"*W + "║")
print("║" + "  📅  YESTERDAY  (" + yesterday + ")".ljust(W - 20) + "║")
print("║" + "─"*W + "║")
line("Businesses found yesterday", found_yesterday,"🔍")
line("Emails sent yesterday",      sent_yesterday, "📨")

print("║" + "─"*W + "║")
print("║" + "  🔁  FOLLOW-UPS".ljust(W) + "║")
print("║" + "─"*W + "║")
line("Needs follow-up (3+ days)",  followup_needed,"⏰")
line("Follow-up emails sent",      followup_sent,  "📩")

if sb_stats:
    print("║" + "─"*W + "║")
    print("║" + "  ☁️   SUPABASE CLOUD DB".ljust(W) + "║")
    print("║" + "─"*W + "║")
    sb_total = sum(sb_stats.values())
    line("Total in Supabase",          sb_total,     "🗄️ ")
    for status, count in sorted(sb_stats.items(), key=lambda x: -x[1]):
        line(f"  └ {status}", count, "  ")

print("╚" + "═"*W + "╝")

# ── Which leads replied? ─────────────────────────────────────
replied_leads = [(k, v) for k, v in clients.items() if v.get("status") == "replied"]
if replied_leads:
    print(f"\n  💬 REPLIED LEADS ({len(replied_leads)}):")
    for name, data in replied_leads:
        print(f"     • {name[:40]:<40}  {data.get('email','')}")

# ── Who needs follow-up soonest? ─────────────────────────────
if followup_needed:
    print(f"\n  ⏰ TOP FOLLOW-UP CANDIDATES (oldest first):")
    candidates = [
        (k, v) for k, v in clients.items()
        if v.get("status") == "email_sent"
        and str(v.get("date_emailed",""))[:10] <= cutoff
        and str(v.get("date_emailed",""))[:10] != ""
    ]
    candidates.sort(key=lambda x: x[1].get("date_emailed",""))
    for name, data in candidates[:10]:
        print(f"     • {name[:38]:<38}  sent: {str(data.get('date_emailed',''))[:10]}  {data.get('email','')}")
    if len(candidates) > 10:
        print(f"     ... and {len(candidates)-10} more")

print()
print("  💡 Commands:")
print("     python stats.py                    → this dashboard")
print("     python supabase_sync.py            → sync + check replies")
print("     python client_hunter.py --limit 100  → send 100 emails")
print("     python client_hunter.py --dry-run    → test without sending")
print()
