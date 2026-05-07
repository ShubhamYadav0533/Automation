-- Migration 001: Create clients table
-- Run in: https://supabase.com/dashboard/project/zlwbnqgjovuhssccsixd/sql/new

CREATE TABLE IF NOT EXISTS public.clients (
  id            BIGSERIAL PRIMARY KEY,
  name          TEXT UNIQUE NOT NULL,
  email         TEXT,
  website       TEXT,
  phone         TEXT,
  contact_name  TEXT,
  city          TEXT,
  category      TEXT,
  source        TEXT,
  status        TEXT DEFAULT 'found',
  date_found    TEXT,
  date_emailed  TEXT,
  email_subject TEXT,
  notes         TEXT,
  used_ai       BOOLEAN DEFAULT FALSE,
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS clients_status_idx ON public.clients(status);
CREATE INDEX IF NOT EXISTS clients_date_emailed_idx ON public.clients(date_emailed);
