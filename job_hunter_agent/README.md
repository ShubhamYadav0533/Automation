# 🤖 AI Job & Client Hunter Agent

A fully automated agent that searches the entire web for jobs and clients that match **your exact profile**, sends personalized outreach emails, auto-replies to responses, and only notifies you when a lead is **confirmed hot and ready to close**.

---

## 🧠 How It Works

```
YOUR PROFILE (skills, rate, availability)
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│  SEARCH ENGINE — scans worldwide every 24 hours         │
│  ✦ Upwork   ✦ LinkedIn   ✦ Remotive   ✦ We Work Remotely│
│  ✦ Freelancer.com   ✦ Wellfound   ✦ Google Maps         │
└───────────────────────┬─────────────────────────────────┘
                        │ 100+ leads found
                        ▼
┌─────────────────────────────────────────────────────────┐
│  CLAUDE AI BRAIN — scores every lead 0-100              │
│  ✦ Skill match analysis                                 │
│  ✦ Budget/rate compatibility                            │
│  ✦ Lead quality check                                   │
└───────────────────────┬─────────────────────────────────┘
                        │ Top leads (score ≥ 65)
                        ▼
┌─────────────────────────────────────────────────────────┐
│  OUTREACH ENGINE — writes & sends personalized emails   │
│  ✦ Every email is unique, NOT a template                │
│  ✦ References specific details from the job post        │
│  ✦ Sent via your Gmail account                          │
└───────────────────────┬─────────────────────────────────┘
                        │ Emails sent
                        ▼
┌─────────────────────────────────────────────────────────┐
│  REPLY MONITOR — checks inbox every 2 hours             │
│  ✦ Reads client replies                                 │
│  ✦ AI classifies: Interested / Questions / Scheduling   │
│  ✦ Auto-replies intelligently                           │
└───────────────────────┬─────────────────────────────────┘
                        │ Lead confirmed HOT
                        ▼
┌─────────────────────────────────────────────────────────┐
│  📱 YOU GET A TELEGRAM NOTIFICATION                     │
│  "🔥 HOT LEAD CONFIRMED — TechBuild GmbH wants to talk! │
│   They asked about your rate and availability.          │
│   AI already replied. Check Gmail for the thread."      │
└─────────────────────────────────────────────────────────┘
```

---

## ⚡ Quick Setup (30 minutes)

### Step 1 — Clone & Install

```bash
cd job_hunter_agent
pip install -r requirements.txt
```

### Step 2 — Edit Your Profile

Open `profile.json` and fill in your real details:
- Your name, email, skills
- Hourly rate
- Portfolio URL
- Target locations

### Step 3 — Get API Keys (all have free tiers)

#### A) Claude API (AI Brain) — Required
1. Go to https://console.anthropic.com
2. Create account → API Keys → Create Key
3. Free credits given on signup

#### B) SerpAPI (Google Search) — Required for job search
1. Go to https://serpapi.com
2. Create free account (100 searches/month free)
3. Copy your API key

#### C) Gmail API — Required for email
1. Go to https://console.cloud.google.com
2. Create a new project
3. Enable **Gmail API**
4. Go to **Credentials** → Create Credentials → **OAuth 2.0 Client ID**
5. Application type: **Desktop app**
6. Download the JSON file
7. Save it as `credentials/gmail_credentials.json`

#### D) Telegram Bot — Required for notifications
1. Open Telegram, search for **@BotFather**
2. Send `/newbot` and follow instructions
3. Copy the **bot token**
4. Start a chat with your new bot
5. Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
6. Send any message to your bot, then refresh that URL
7. Find `"chat":{"id":XXXXXXX}` — that number is your Chat ID

#### E) Hunter.io (Find contact emails) — Optional
1. Go to https://hunter.io
2. Free account gives 25 searches/month
3. Copy API key

### Step 4 — Configure .env

```bash
cp .env.example .env
```

Edit `.env` and fill in all your API keys.

### Step 5 — Run the Agent!

**One-time run (test):**
```bash
python agent.py
```

**Auto-scheduler (runs every 24h, checks replies every 2h):**
```bash
python scheduler.py
```

**Run in background (Linux/Mac):**
```bash
nohup python scheduler.py > data/output.log 2>&1 &
echo "Agent running in background! PID: $!"
```

---

## 📁 File Structure

```
job_hunter_agent/
│
├── agent.py          ← Main orchestrator (run this)
├── scheduler.py      ← Auto-runs every 24h
├── searcher.py       ← Searches all job platforms
├── ai_brain.py       ← Claude AI (scoring, emails, replies)
├── emailer.py        ← Gmail send/receive
├── notifier.py       ← Telegram notifications
├── tracker.py        ← Local database (JSON)
├── profile.json      ← YOUR PROFILE (edit this first!)
├── requirements.txt  ← Python dependencies
├── .env.example      ← Config template
│
├── credentials/      ← Gmail credentials (auto-created)
│   ├── gmail_credentials.json  ← Download from Google Cloud
│   └── gmail_token.pickle      ← Auto-generated after first login
│
└── data/             ← Auto-created data storage
    ├── leads.json          ← All leads found
    ├── emails_sent.json    ← Email tracking + threads
    ├── hot_leads.json      ← Confirmed hot leads
    ├── proposals/          ← Drafted proposals for manual platforms
    ├── agent.log           ← Full activity log
    └── scheduler.log       ← Scheduler log
```

---

## 🎛️ Settings (in .env)

| Setting | Default | Description |
|---------|---------|-------------|
| `AUTO_SEND_EMAILS` | `false` | `true` = fully automatic. `false` = drafts for your review |
| `AUTO_REPLY_ENABLED` | `true` | Auto-reply to client responses |
| `MIN_MATCH_SCORE` | `65` | Only contact leads scoring 65+ out of 100 |
| `MAX_LEADS_PER_RUN` | `20` | Max emails per 24h cycle |
| `AGENT_RUN_INTERVAL_HOURS` | `24` | How often to hunt |

---

## ⚠️ Important Notes

### Platform Rules
- **Upwork/LinkedIn**: These platforms ban bots. The agent **finds** these jobs via Google search and saves the proposal text — you paste it in manually (takes 2 minutes per job). This is the safest approach.
- **Google Maps outbound leads**: Agent emails businesses directly — fully automated.
- **Email to businesses**: Fully automated via Hunter.io + Gmail.

### Anti-Spam
- Agent respects `MAX_LEADS_PER_RUN` to avoid spamming
- 2-second delay between emails
- Never contacts the same lead twice (tracked in database)

### Privacy
- All data stored locally in `data/` folder
- Nothing sent to any third party except the APIs you configure
- Your Gmail token is stored locally in `credentials/`

---

## 🔥 What You'll See in Telegram

When hunting starts:
```
🤖 Job Hunter Agent Started
🔍 Scanning Upwork, LinkedIn, Remotive, Google Maps...
⏳ Will notify you when hot leads are found.
```

When a hot lead is confirmed:
```
🔥 HOT LEAD CONFIRMED!

🔥 TechBuild GmbH — LinkedIn
💰 Budget: $4,000/month
✅ Perfect match: ERP, CRM, Android — all in their job requirements
📧 They replied: "Thanks for reaching out! We're very interested.
    Can you jump on a call this week?"
👉 AI has already replied proposing Thursday 3pm.
   Check Gmail for the full thread!

🔗 https://linkedin.com/jobs/view/...
```

---

## 💡 Tips for Best Results

1. **Fill profile.json completely** — the more detail, the better the AI matches
2. **Start with `AUTO_SEND_EMAILS=false`** to review the first few emails before going fully automatic
3. **Keep the scheduler running 24/7** — use a cheap VPS (DigitalOcean $4/month) or just leave your PC on
4. **Check `data/proposals/`** folder daily — these are AI-drafted proposals for platforms you need to post on manually (Upwork, LinkedIn)
5. **Adjust `MIN_MATCH_SCORE`** — lower it if you're getting too few leads, raise it for higher quality

---

## 🆘 Troubleshooting

**"Gmail credentials not found"**
→ Download the OAuth JSON from Google Cloud Console and save as `credentials/gmail_credentials.json`

**"SerpAPI quota exceeded"**
→ You've used your 100 free searches. Upgrade or wait until next month. Remotive and WeWorkRemotely still work for free.

**"Telegram not configured"**
→ Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to `.env`

**Agent finds 0 leads**
→ Check your `profile.json` keywords. Make sure `search_keywords` has clear job title keywords like "software engineer", "Android developer"
