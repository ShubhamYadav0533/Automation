"""
job_hunter_agent/ai_brain.py
=============================
The AI brain of the agent. Handles:
  1. Scoring & ranking leads against your profile
  2. Writing personalized outreach emails
  3. Reading & replying to client responses
  4. Deciding if a lead is "confirmed hot" to notify you

AI Backend priority:
  1. Google Gemini (free - 1500 req/day)
  2. Anthropic Claude (if credits available)
  3. Keyword fallback (always works, no API needed)
"""

import os
import json
import logging
from typing import Dict, List, Tuple
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)
logger = logging.getLogger(__name__)

# ── Try Gemini (free tier, primary) ──────────────────────────
_gemini_client = None
try:
    import google.generativeai as genai
    _gemini_key = os.getenv("GEMINI_API_KEY", "")
    if _gemini_key:
        genai.configure(api_key=_gemini_key)
        _gemini_client = genai.GenerativeModel("gemini-2.0-flash")
        logger.info("✅ Gemini AI ready (free tier)")
except Exception as e:
    logger.debug(f"Gemini not available: {e}")

# ── Try Claude (paid, fallback) ───────────────────────────────
_claude_client = None
_claude_disabled = False
try:
    import anthropic
    _claude_key = os.getenv("ANTHROPIC_API_KEY", "")
    if _claude_key and not _claude_key.startswith("your_"):
        _claude_client = anthropic.Anthropic(api_key=_claude_key)
except Exception:
    pass

MODEL = "gemini-2.0-flash"


def _ask_ai(system_prompt: str, user_message: str, max_tokens: int = 1024) -> str:
    """Send prompt to best available AI: Gemini → Claude → fallback."""
    global _claude_disabled

    # 1. Try Gemini first (free)
    if _gemini_client:
        try:
            full_prompt = f"{system_prompt}\n\n{user_message}"
            response = _gemini_client.generate_content(full_prompt)
            return response.text
        except Exception as e:
            logger.warning(f"Gemini error: {e} — trying Claude...")

    # 2. Try Claude (if credits available)
    if _claude_client and not _claude_disabled:
        try:
            msg = _claude_client.messages.create(
                model="claude-opus-4-5",
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            return msg.content[0].text
        except Exception as e:
            err = str(e)
            if "credit balance" in err or "billing" in err.lower():
                logger.warning("⚠️  Claude credits exhausted — using keyword fallback.")
                _claude_disabled = True
            else:
                logger.error(f"Claude error: {e}")

    return ""


# Keep old name as alias for compatibility
def _ask_claude(system_prompt: str, user_message: str, max_tokens: int = 1024) -> str:
    return _ask_ai(system_prompt, user_message, max_tokens)



# ─────────────────────────────────────────────
#  FALLBACK: keyword-based scorer (no API needed)
# ─────────────────────────────────────────────
_HIGH_VALUE_KEYWORDS = [
    "react", "next.js", "nextjs", "react native", "node.js", "nodejs",
    "mern", "typescript", "javascript", "full stack", "fullstack",
    "crm", "erp", "cms", "redux", "express", "mongodb", "frontend",
    "mobile app", "web app", "college management", "legacy", "modernization",
]
_NEGATIVE_KEYWORDS = [
    "python developer", "django", "ruby", "php", "wordpress",
    "data scientist", "machine learning", "devops", "aws engineer",
    "blockchain", "solidity", "copywriter", "content writer",
    "sales", "marketing", "hr ", "accountant", "designer",
    "video", "animator", "seo ", "data entry",
]

def _fallback_score_lead(lead: Dict, profile: Dict) -> tuple:
    """Rule-based scorer used when Claude API has no credits."""
    title = lead.get("title", "").lower()
    desc = lead.get("description", "").lower()
    company = lead.get("company", "").lower()
    text = title + " " + desc + " " + company

    score = 20  # base
    matched_skills = []

    # Title match scores double (title is the strongest signal)
    for kw in _HIGH_VALUE_KEYWORDS:
        in_title = kw in title
        in_text = kw in text
        if in_title:
            score += 12
            matched_skills.append(kw)
        elif in_text:
            score += 5
            matched_skills.append(kw)

    # Penalise irrelevant roles
    for kw in _NEGATIVE_KEYWORDS:
        if kw in text:
            score -= 20

    # Platform bonus
    platform = lead.get("platform", "").lower()
    if platform in ["remotive", "weworkremotely"]:
        score += 10
    elif platform in ["linkedin", "wellfound (angellist)", "freelancer.com"]:
        score += 7
    elif platform == "google maps":  # outbound lead
        score += 12

    # Remote bonus
    if "remote" in text:
        score += 5

    # Internship/unpaid penalty
    if "intern" in title or "unpaid" in title:
        score -= 15

    score = max(0, min(100, score))
    level = "HOT" if score >= 75 else ("WARM" if score >= 55 else "COLD")
    action = "APPLY" if score >= 50 else "SKIP"
    return score, {
        "score": score,
        "match_level": level,
        "reason": f"Keyword match: {', '.join(matched_skills[:4]) or 'no strong match'}",
        "key_skills_matched": matched_skills[:5],
        "estimated_budget": lead.get("salary", "Not specified"),
        "recommended_action": action,
        "scored_by": "fallback",
    }


def _fallback_write_email(lead: Dict, profile: Dict) -> Dict:
    """Template-based email writer used when Claude has no credits."""
    name = profile.get("name", "Shubham")
    title = profile.get("title", "Full Stack Developer")
    exp = profile.get("experience_years", 2)
    rate = profile.get("hourly_rate_usd", 35)
    skills = ", ".join(profile.get("skills", [])[:5])
    portfolio = profile.get("portfolio_url", "https://github.com/ShubhamYadav0533")
    job_title = lead.get("title", "your opportunity")
    company = lead.get("company", "your team")
    platform = lead.get("platform", "")
    projects = profile.get("notable_projects", [])
    project_line = ""
    if projects:
        p = projects[0]
        project_line = f"Most recently, I built {p['name']} ({p['url']}) — {p['description'][:80]}."

    if lead.get("type") == "outbound_lead":
        subject = f"React/Node.js Developer Available — Let's Build Something Great"
        body = (
            f"Hi {company},\n\n"
            f"I came across your business and wanted to reach out. I'm {name}, a {title} "
            f"with {exp} years of experience building web and mobile applications.\n\n"
            f"{project_line}\n\n"
            f"I specialize in {skills} and help businesses build clean, scalable software. "
            f"My rate is ${rate}/hr and I'm available for remote work immediately.\n\n"
            f"Would you be open to a quick 15-minute call to see if there's a fit?\n\n"
            f"Portfolio: {portfolio}\n\n"
            f"Best regards,\n{name}"
        )
    else:
        subject = f"Application: {job_title} — {exp}yr React/Node.js Developer"
        body = (
            f"Hi,\n\n"
            f"I'm very interested in the {job_title} role. I'm {name}, a {title} "
            f"with {exp} years of hands-on experience in {skills}.\n\n"
            f"{project_line}\n\n"
            f"I'm available immediately for remote work at ${rate}/hr and would love "
            f"to discuss how I can contribute to your team.\n\n"
            f"Portfolio & GitHub: {portfolio}\n\n"
            f"Looking forward to hearing from you!\n\n"
            f"Best regards,\n{name}"
        )
    return {"subject": subject, "body": body.strip(), "tone": "professional", "written_by": "fallback"}


# ─────────────────────────────────────────────
#  STEP 1: Score & rank a lead (0-100)
# ─────────────────────────────────────────────
def score_lead(lead: Dict, profile: Dict) -> Tuple[int, str]:
    """
    Ask Claude to score this lead from 0-100 based on:
    - Skill match
    - Budget/salary match
    - Job type preference
    - Lead quality
    Returns: (score: int, reason: str)
    """
    system = """You are an expert career advisor and freelance business analyst.
Your job is to score job leads and client opportunities for a software engineer.
Always respond with valid JSON only. No extra text."""

    user = f"""
CANDIDATE PROFILE:
{json.dumps(profile, indent=2)}

LEAD TO EVALUATE:
{json.dumps(lead, indent=2)}

Score this lead from 0 to 100 based on:
- Skill match (how well the candidate's skills match)
- Budget/salary match (within their rate expectations)
- Job type match (remote, contract, freelance preferences)
- Lead quality (is it real, specific, not too competitive)
- Overall opportunity quality

Respond with this exact JSON:
{{
  "score": <number 0-100>,
  "match_level": "<HOT|WARM|COLD>",
  "reason": "<2-3 sentences explaining the score>",
  "key_skills_matched": ["skill1", "skill2"],
  "estimated_budget": "<estimated budget/salary if visible>",
  "recommended_action": "<APPLY|PITCH|SKIP>"
}}
"""
    response = _ask_claude(system, user, max_tokens=512)
    if not response:
        logger.debug("Claude unavailable — using fallback keyword scorer")
        return _fallback_score_lead(lead, profile)
    try:
        data = json.loads(response)
        return data.get("score", 0), data
    except json.JSONDecodeError:
        logger.error(f"Could not parse score response: {response}")
        return _fallback_score_lead(lead, profile)


# ─────────────────────────────────────────────
#  STEP 2: Write personalized outreach email
# ─────────────────────────────────────────────
def write_outreach_email(lead: Dict, profile: Dict, score_data: Dict) -> Dict:
    """
    Ask Claude to write a personalized, professional outreach email.
    Returns: { subject, body, tone }
    """
    system = """You are an expert freelance business development writer.
You write compelling, personalized, professional emails that get responses.
You never write generic templates. Every email is specific to the job/client.
Keep emails concise (under 200 words) but powerful.
Respond with valid JSON only."""

    lead_type = lead.get("type", "job_post")
    if lead_type == "outbound_lead":
        email_purpose = "cold outreach pitch (you are approaching them to offer your services)"
    else:
        email_purpose = "job application / proposal"

    user = f"""
Write a {email_purpose} email for this opportunity.

SENDER (the software engineer applying):
- Name: {profile.get('name', 'The Candidate')}
- Title: {profile.get('title', 'Software Engineer')}
- Experience: {profile.get('experience_years', 3)} years
- Key Skills: {', '.join(profile.get('skills', [])[:6])}
- Hourly Rate: ${profile.get('hourly_rate_usd', 35)}/hr
- Portfolio: {profile.get('portfolio_url', '')}
- Bio: {profile.get('bio', '')}

OPPORTUNITY:
{json.dumps(lead, indent=2)}

MATCH ANALYSIS:
{json.dumps(score_data, indent=2)}

Write an email that:
1. Opens with something SPECIFIC to their job/company (not generic)
2. Shows you understand their problem/need
3. Highlights 2-3 most relevant skills/experiences
4. Has a clear, specific call to action
5. Is professional but warm, not robotic

Respond with:
{{
  "subject": "<email subject line>",
  "body": "<full email body with proper line breaks>",
  "tone": "<professional|friendly|direct>"
}}
"""
    response = _ask_claude(system, user, max_tokens=1024)
    if not response:
        logger.debug("Claude unavailable — using fallback email template")
        return _fallback_write_email(lead, profile)
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        logger.error(f"Could not parse email response")
        return _fallback_write_email(lead, profile)


# ─────────────────────────────────────────────
#  STEP 3: Read a client's reply & classify it
# ─────────────────────────────────────────────
def analyze_client_reply(
    original_email: str,
    client_reply: str,
    lead: Dict,
    profile: Dict
) -> Dict:
    """
    Read the client's reply and:
    - Classify: INTERESTED / ASKING_QUESTIONS / DECLINED / SPAM / SCHEDULING
    - Write a smart follow-up reply
    - Tell us if this is a CONFIRMED HOT LEAD (notify the user)
    """
    system = """You are an expert sales and freelance business development assistant.
You read email conversations and craft perfect follow-up replies.
You identify warm leads that are ready to close.
Respond with valid JSON only."""

    user = f"""
ORIGINAL EMAIL SENT:
{original_email}

CLIENT'S REPLY:
{client_reply}

OUR PROFILE:
Name: {profile.get('name')}
Skills: {', '.join(profile.get('skills', [])[:6])}
Rate: ${profile.get('hourly_rate_usd')}/hr

JOB/LEAD INFO:
{json.dumps(lead, indent=2)}

Analyze this conversation and respond with:
{{
  "reply_classification": "<INTERESTED|ASKING_QUESTIONS|SCHEDULING|DECLINED|SPAM|NEGOTIATING>",
  "confidence": <0-100>,
  "is_hot_lead": <true|false>,
  "hot_lead_reason": "<why this is hot, if applicable>",
  "follow_up_subject": "<subject for reply email>",
  "follow_up_body": "<your smart reply to the client>",
  "action_required": "<SEND_REPLY|NOTIFY_USER|SKIP|SCHEDULE_CALL>",
  "urgency": "<HIGH|MEDIUM|LOW>",
  "summary": "<one sentence summary of the situation>"
}}

Mark is_hot_lead as TRUE if the client:
- Expressed clear interest
- Asked about rates/timeline/availability
- Wants to schedule a call
- Made an offer
"""
    response = _ask_claude(system, user, max_tokens=1024)
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        logger.error(f"Could not parse reply analysis")
        return {
            "reply_classification": "UNKNOWN",
            "is_hot_lead": False,
            "action_required": "NOTIFY_USER",
            "follow_up_body": "Thank you for your reply! I'd love to discuss this further. When would be a good time to connect?",
            "summary": "Client replied - needs manual review",
        }


# ─────────────────────────────────────────────
#  STEP 4: Generate hot lead summary for user
# ─────────────────────────────────────────────
def generate_hot_lead_summary(lead: Dict, score_data: Dict, conversation: List[str]) -> str:
    """
    Generate a clear summary message to send to the user via Telegram/email
    when a lead becomes confirmed HOT.
    """
    system = """You are a concise business assistant. 
Write short, clear summaries that a busy professional can read in 10 seconds.
Use emojis to make it scannable."""

    user = f"""
Create a hot lead notification for the user. Make it exciting and clear.

LEAD:
{json.dumps(lead, indent=2)}

MATCH SCORE:
{json.dumps(score_data, indent=2)}

CONVERSATION SUMMARY:
{chr(10).join(conversation[-3:])}

Write a notification message (max 15 lines) with:
- 🔥 Lead title and platform
- 💰 Budget/salary if known
- ✅ Why it's a great match (2-3 points)
- 📧 What the client said
- 👉 Recommended next action

Keep it punchy and clear. This is a TELEGRAM message so use line breaks and emojis.
"""
    return _ask_claude(system, user, max_tokens=512)


# ─────────────────────────────────────────────
#  STEP 5: Filter & rank all leads
# ─────────────────────────────────────────────
def rank_all_leads(leads: List[Dict], profile: Dict, min_score: int = 65) -> List[Dict]:
    """
    Score all leads and return sorted list, filtering below min_score.
    Adds 'ai_score', 'ai_score_data' to each lead dict.
    """
    logger.info(f"\n🤖 AI is scoring {len(leads)} leads...")
    scored = []

    for i, lead in enumerate(leads):
        logger.info(f"  Scoring lead {i+1}/{len(leads)}: {lead.get('title', '')[:50]}...")
        score, score_data = score_lead(lead, profile)
        lead["ai_score"] = score
        lead["ai_score_data"] = score_data

        if score >= min_score:
            scored.append(lead)
            logger.info(f"  ✅ Score: {score} ({score_data.get('match_level', '')}) — {score_data.get('recommended_action', '')}")
        else:
            logger.info(f"  ❌ Score: {score} — skipped (below threshold {min_score})")

    # Sort by score descending
    scored.sort(key=lambda x: x.get("ai_score", 0), reverse=True)
    logger.info(f"\n🎯 {len(scored)} leads passed the quality threshold")
    return scored
