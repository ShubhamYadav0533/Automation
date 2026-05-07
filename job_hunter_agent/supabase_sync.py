"""
supabase_sync.py
=================
Syncs ALL local data to Supabase cloud database.
- clients.json  → public.clients  table
- leads.json    → public.clients  table (merged, source=job_lead)
- Checks Gmail INBOX daily for replies → updates status to 'replied'
- Auto follow-up: leads emailed 3+ days ago with no reply get flagged

Runs automatically after every email sent.
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Reload from .env at import time so CLI works correctly
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
DATA_DIR  = Path(__file__).parent / "data"
JSON_FILE = DATA_DIR / "clients.json"
LEADS_FILE = DATA_DIR / "leads.json"

_client = None  # lazy-loaded Supabase client


def _get_client():
    """Lazy-load Supabase client."""
    global _client
    if _client is not None:
        return _client
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
        return _client
    except ImportError:
        logger.warning("supabase not installed — run: pip install supabase --break-system-packages")
        return None
    except Exception as e:
        logger.error(f"Supabase connect error: {e}")
        return None


def is_configured() -> bool:
    """Check if Supabase credentials are set in .env."""
    return bool(SUPABASE_URL and SUPABASE_KEY and
                not SUPABASE_URL.startswith("https://xxxx"))


# ─────────────────────────────────────────────────────────────
#  UPSERT a single lead (called after every email sent)
# ─────────────────────────────────────────────────────────────
def upsert_lead(name: str, data: Dict) -> bool:
    """
    Insert or update a single lead in Supabase.
    Called automatically after every email sent.
    """
    if not is_configured():
        return False
    client = _get_client()
    if not client:
        return False
    try:
        client.table("clients").upsert(_build_row(name, data), on_conflict="name").execute()
        logger.debug(f"☁️  Supabase: upserted {name}")
        return True
    except Exception as e:
        logger.warning(f"Supabase upsert error for {name}: {e}")
        return False


# ─────────────────────────────────────────────────────────────
#  BUILD ROW — shared helper
# ─────────────────────────────────────────────────────────────
def _build_row(name: str, data: Dict) -> Dict:
    return {
        "name":          name,
        "category":      data.get("category", ""),
        "city":          data.get("city", ""),
        "website":       data.get("website", ""),
        "email":         data.get("email", ""),
        "phone":         data.get("phone", ""),
        "contact_name":  data.get("contact_name", ""),
        "status":        data.get("status", "found"),
        "date_found":    str(data.get("date_found", "")),
        "date_emailed":  str(data.get("date_emailed", "")),
        "email_subject": data.get("email_subject", ""),
        "used_ai":       bool(data.get("used_ai", False)),
        "source":        data.get("source", ""),
        "notes":         data.get("notes", ""),
    }


# ─────────────────────────────────────────────────────────────
#  FULL SYNC — push clients.json + leads.json → Supabase
# ─────────────────────────────────────────────────────────────
def sync_all() -> int:
    """
    Push ALL records (clients.json + leads.json) to Supabase.
    Returns total number of records synced.
    """
    if not is_configured():
        print("⚠️  Supabase not configured — add SUPABASE_URL and SUPABASE_KEY to .env")
        return 0

    client = _get_client()
    if not client:
        return 0

    rows: List[Dict] = []

    # ── 1. clients.json ──────────────────────────────────────
    if JSON_FILE.exists():
        try:
            clients = json.loads(JSON_FILE.read_text())
            for name, data in clients.items():
                rows.append(_build_row(name, data))
        except Exception as e:
            logger.error(f"Read clients.json error: {e}")

    # ── 2. leads.json (job leads / freelancer leads) ─────────
    if LEADS_FILE.exists():
        try:
            leads_raw = json.loads(LEADS_FILE.read_text())
            # leads.json can be a list or a dict
            leads_iter = leads_raw.items() if isinstance(leads_raw, dict) else enumerate(leads_raw)
            for key, data in leads_iter:
                if not isinstance(data, dict):
                    continue
                name = data.get("name") or data.get("title") or data.get("company") or str(key)
                # Skip if already covered by clients.json
                if any(r["name"] == name for r in rows):
                    continue
                row = _build_row(name, data)
                if not row.get("source"):
                    row["source"] = "job_lead"
                rows.append(row)
        except Exception as e:
            logger.error(f"Read leads.json error: {e}")

    if not rows:
        print("  ⚠️  No data found to sync")
        return 0

    # ── 3. Upload in batches of 100 ──────────────────────────
    synced = 0
    batch_size = 100
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        try:
            client.table("clients").upsert(batch, on_conflict="name").execute()
            synced += len(batch)
            print(f"  ☁️  Synced {synced}/{len(rows)} records to Supabase...")
        except Exception as e:
            logger.error(f"Supabase batch sync error: {e}")

    print(f"  ✅ Supabase sync complete: {synced} records")
    return synced


# ─────────────────────────────────────────────────────────────
#  CHECK REPLIES — scan Gmail INBOX, update replied status
# ─────────────────────────────────────────────────────────────
def check_and_update_replies() -> int:
    """
    Check Gmail for replies from leads.
    - Matches reply sender email against leads in clients.json
    - Updates status → 'replied' in both local JSON and Supabase
    Returns number of new replies found.
    """
    if not JSON_FILE.exists():
        return 0

    try:
        clients = json.loads(JSON_FILE.read_text())
    except Exception:
        return 0

    # Build a lookup: email_address → client_key
    email_to_key: Dict[str, str] = {}
    for key, data in clients.items():
        em = (data.get("email") or "").lower().strip()
        if em:
            email_to_key[em] = key

    if not email_to_key:
        return 0

    # Fetch replies from Gmail
    try:
        from emailer import get_new_replies
        replies = get_new_replies()
    except Exception as e:
        logger.warning(f"Could not fetch replies: {e}")
        return 0

    new_replied = 0
    sb_client = _get_client() if is_configured() else None

    for reply in replies:
        from_raw = reply.get("from_email", "")
        # Extract bare email from "Name <email@x.com>"
        import re
        match = re.search(r"[\w.\-+]+@[\w.\-]+", from_raw)
        if not match:
            continue
        from_email = match.group(0).lower()

        if from_email not in email_to_key:
            continue

        key = email_to_key[from_email]
        old_status = clients[key].get("status", "")
        if old_status == "replied":
            continue  # already marked

        # Update local JSON
        clients[key]["status"] = "replied"
        clients[key]["notes"] = (
            clients[key].get("notes", "") +
            f" | Reply received {datetime.now().strftime('%Y-%m-%d')}"
        ).strip(" |")
        new_replied += 1
        print(f"  💬 Reply detected from: {key} ({from_email})")

        # Update Supabase immediately
        if sb_client:
            try:
                sb_client.table("clients").update({
                    "status": "replied",
                    "notes":  clients[key]["notes"],
                    "updated_at": datetime.now().isoformat(),
                }).eq("name", key).execute()
            except Exception as e:
                logger.warning(f"Supabase reply update error: {e}")

    # Save updated clients.json
    if new_replied:
        try:
            JSON_FILE.write_text(json.dumps(clients, indent=2, ensure_ascii=False))
            # Rebuild Excel
            try:
                from client_tracker import _rebuild_excel, _load_clients
                _rebuild_excel(_load_clients())
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Save error after reply update: {e}")

    return new_replied


# ─────────────────────────────────────────────────────────────
#  FOLLOW-UP FLAGS — list leads needing follow-up
# ─────────────────────────────────────────────────────────────
def get_followup_candidates(days: int = 3) -> List[Dict]:
    """
    Return leads that:
      - status = 'email_sent'
      - emailed >= `days` days ago
      - no reply yet
    Used by client_hunter.py to send follow-ups.
    """
    if not JSON_FILE.exists():
        return []
    try:
        clients = json.loads(JSON_FILE.read_text())
    except Exception:
        return []

    cutoff = datetime.now() - timedelta(days=days)
    candidates = []
    for key, data in clients.items():
        if data.get("status") != "email_sent":
            continue
        date_str = data.get("date_emailed", "")
        if not date_str:
            continue
        try:
            # Handle both ISO and strftime formats
            emailed_dt = datetime.fromisoformat(date_str[:19])
        except Exception:
            continue
        if emailed_dt <= cutoff:
            candidates.append({"key": key, **data})

    candidates.sort(key=lambda x: x.get("date_emailed", ""))
    return candidates


# ─────────────────────────────────────────────────────────────
#  GET STATS from Supabase (for dashboard)
# ─────────────────────────────────────────────────────────────
def get_supabase_stats() -> Optional[Dict]:
    """Fetch summary stats from Supabase."""
    if not is_configured():
        return None
    client = _get_client()
    if not client:
        return None
    try:
        result = client.table("clients").select("status").execute()
        rows = result.data or []
        stats: Dict = {}
        for row in rows:
            s = row.get("status", "found")
            stats[s] = stats.get(s, 0) + 1
        return stats
    except Exception as e:
        logger.warning(f"Supabase stats error: {e}")
        return None


# ─────────────────────────────────────────────────────────────
#  CLI: python supabase_sync.py
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.WARNING,  # suppress httpx INFO spam in CLI
        format="%(levelname)s: %(message)s"
    )

    if not is_configured():
        print("""
❌  Supabase not configured.

Add these to your .env file:
  SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
  SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
""")
        sys.exit(1)

    print(f"\n☁️  Connecting to Supabase: {SUPABASE_URL[:40]}...")

    # 1. Sync all data
    count = sync_all()

    # 2. Check for new replies
    print("\n📬 Checking Gmail for replies...")
    new_replies = check_and_update_replies()
    if new_replies:
        print(f"  ✅ {new_replies} new replies found and status updated!")
    else:
        print("  — No new replies found")

    # 3. Show follow-up candidates
    candidates = get_followup_candidates(days=3)
    if candidates:
        print(f"\n⏰ Follow-up needed ({len(candidates)} leads, emailed 3+ days ago, no reply):")
        for c in candidates[:10]:
            print(f"   • {c['key']:<35} emailed: {c.get('date_emailed','?')[:10]}")
        if len(candidates) > 10:
            print(f"   ... and {len(candidates)-10} more")
    else:
        print("\n✅ No follow-ups needed right now")

    # 4. Stats
    if count:
        stats = get_supabase_stats()
        if stats:
            print("\n📊 Supabase Cloud Stats:")
            for status, n in sorted(stats.items(), key=lambda x: -x[1]):
                print(f"   {status:<20} : {n}")
