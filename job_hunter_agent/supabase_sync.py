"""
supabase_sync.py
=================
Syncs all client leads to Supabase (free Postgres cloud database).
Runs automatically after every email sent.

SETUP (one-time, 5 minutes):
  1. Go to https://supabase.com → Sign up free
  2. Create a new project → name it "client-hunter"
  3. Go to Settings → API → copy:
       - Project URL  → SUPABASE_URL in .env
       - anon/public key → SUPABASE_KEY in .env
  4. Go to SQL Editor → run this SQL to create the table:

     CREATE TABLE IF NOT EXISTS clients (
       id           SERIAL PRIMARY KEY,
       name         TEXT UNIQUE NOT NULL,
       category     TEXT,
       city         TEXT,
       website      TEXT,
       email        TEXT,
       phone        TEXT,
       contact_name TEXT,
       status       TEXT DEFAULT 'found',
       date_found   TEXT,
       date_emailed TEXT,
       email_subject TEXT,
       used_ai      BOOLEAN DEFAULT false,
       source       TEXT,
       notes        TEXT,
       updated_at   TIMESTAMPTZ DEFAULT NOW()
     );

  5. Add to .env:
       SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
       SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

  6. Install: pip install supabase --break-system-packages

Then this module runs automatically — no extra steps needed.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
DATA_DIR = Path(__file__).parent / "data"
JSON_FILE = DATA_DIR / "clients.json"

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
        row = {
            "name":          name,
            "category":      data.get("category", ""),
            "city":          data.get("city", ""),
            "website":       data.get("website", ""),
            "email":         data.get("email", ""),
            "phone":         data.get("phone", ""),
            "contact_name":  data.get("contact_name", ""),
            "status":        data.get("status", "found"),
            "date_found":    data.get("date_found", ""),
            "date_emailed":  data.get("date_emailed", ""),
            "email_subject": data.get("email_subject", ""),
            "used_ai":       bool(data.get("used_ai", False)),
            "source":        data.get("source", ""),
            "notes":         data.get("notes", ""),
        }
        client.table("clients").upsert(row, on_conflict="name").execute()
        logger.debug(f"☁️  Supabase: upserted {name}")
        return True
    except Exception as e:
        logger.warning(f"Supabase upsert error for {name}: {e}")
        return False


# ─────────────────────────────────────────────────────────────
#  FULL SYNC — push entire clients.json to Supabase
# ─────────────────────────────────────────────────────────────
def sync_all() -> int:
    """
    Push all records from clients.json to Supabase.
    Returns number of records synced.
    """
    if not is_configured():
        print("⚠️  Supabase not configured — add SUPABASE_URL and SUPABASE_KEY to .env")
        return 0
    if not JSON_FILE.exists():
        return 0

    client = _get_client()
    if not client:
        return 0

    try:
        clients = json.loads(JSON_FILE.read_text())
    except Exception:
        return 0

    synced = 0
    rows = []
    for name, data in clients.items():
        rows.append({
            "name":          name,
            "category":      data.get("category", ""),
            "city":          data.get("city", ""),
            "website":       data.get("website", ""),
            "email":         data.get("email", ""),
            "phone":         data.get("phone", ""),
            "contact_name":  data.get("contact_name", ""),
            "status":        data.get("status", "found"),
            "date_found":    data.get("date_found", ""),
            "date_emailed":  data.get("date_emailed", ""),
            "email_subject": data.get("email_subject", ""),
            "used_ai":       bool(data.get("used_ai", False)),
            "source":        data.get("source", ""),
            "notes":         data.get("notes", ""),
        })

    # Upload in batches of 100
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
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)
    # Reload env vars
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

    logging.basicConfig(level=logging.INFO)

    if not is_configured():
        print("""
❌  Supabase not configured.

Add these to your .env file:
  SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
  SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

Follow the setup instructions at the top of this file.
""")
        sys.exit(1)

    print(f"\n☁️  Connecting to Supabase: {SUPABASE_URL[:40]}...")
    count = sync_all()
    if count:
        stats = get_supabase_stats()
        if stats:
            print("\n📊 Supabase Stats:")
            for status, n in stats.items():
                print(f"   {status:<20} : {n}")
