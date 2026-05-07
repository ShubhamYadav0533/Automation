"""
job_hunter_agent/ollama_writer.py
===================================
FREE local AI using Ollama — NO API KEY NEEDED.
Runs llama3 on your own computer to write personalized
cold-outreach emails for each business you find.

Setup (one-time):
  1. Download Ollama: https://ollama.ai
  2. Run: ollama pull llama3
  3. Keep Ollama running in background (it auto-starts)

This module is called by client_hunter.py automatically.
"""

import requests
import logging
import json

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral"  # mistral is faster than llama3; change to "llama3" if preferred

# ── Shubham's profile snapshot used in every prompt ──────────
PROFILE = {
    "name": "Shubham Yadav",
    "title": "Software Engineer & App Developer",
    "experience": "2 years",
    "skills": "custom web apps, mobile apps, CRM systems, ERP systems, booking platforms, management dashboards",
    "portfolio": "https://github.com/ShubhamYadav0533",
    "email": "shubhamyadav0533@gmail.com",
    "projects": [
        "Hospital CRM — crm.anquestplus.com (live, used by real hospital staff)",
        "Real Estate CRM — crm.anquest.in (live, manages properties and client leads)",
    ],
}


def _is_ollama_running() -> bool:
    """Check if Ollama server is reachable."""
    try:
        r = requests.get("http://localhost:11434", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _ask_ollama(prompt: str, max_retries: int = 2) -> str:
    """Send a prompt to local Ollama and return the response text."""
    for attempt in range(max_retries):
        try:
            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "keep_alive": 300,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 280,
                        "num_ctx": 1024,
                    },
                },
                timeout=200,
            )
            response.raise_for_status()
            return response.json().get("response", "").strip()
        except requests.exceptions.ConnectionError:
            logger.error("❌ Ollama is not running. Start it with: ollama serve")
            return ""
        except Exception as e:
            logger.warning(f"Ollama attempt {attempt + 1} failed: {e}")
    return ""


# ─────────────────────────────────────────────────────────────
#  INDUSTRY → SERVICE MAPPING
#  Detects what Shubham can build for each business type
# ─────────────────────────────────────────────────────────────
INDUSTRY_PITCH = {
    "hospital": {
        "pain": "hospitals that still rely on paper files or disconnected software lose 2–3 hours per staff member every day on admin work — and that directly costs revenue and patient satisfaction",
        "profit": "a unified digital system that manages patient records, appointment scheduling, billing, and staff — staff work faster, fewer errors, and management gets real-time reports instead of chasing data",
        "proof": "I built a live system like this for a hospital — you can see it at crm.anquestplus.com",
        "cta": "If this sounds familiar, I'd love a 15-minute call to show you exactly what I built and how it could work for your hospital.",
    },
    "clinic": {
        "pain": "most clinics lose appointments and patients because there is no reminder system, no proper records, and no way to track which patients need follow-up — this means lost income every week",
        "profit": "a digital clinic management system with appointment booking, automated reminders, patient history, and billing can recover that lost income and run the clinic with half the admin effort",
        "proof": "I specialize in building these systems for medical practices — simple to use, works on any device",
        "cta": "Would you be open to a quick 15-minute call to see a demo?",
    },
    "hotel": {
        "pain": "hotels using manual booking logs or generic tools miss direct bookings, double-book rooms, and lose guests to OTAs that charge 15–25% commission per booking",
        "profit": "a custom booking and property management system gives guests a direct booking option, cuts OTA fees, and gives staff a live dashboard — more revenue, less dependence on third-party platforms",
        "proof": "I build these systems specifically for independent and boutique hotels",
        "cta": "I can show you a working prototype in 48 hours. Would that be worth a look?",
    },
    "restaurant": {
        "pain": "restaurants without a proper ordering and table management system lose 20–30% of potential orders during busy hours due to confusion, missed orders, and slow service",
        "profit": "a digital ordering and table management app means faster service, fewer mistakes, and more covers per night — directly increasing revenue without adding staff",
        "proof": "I build mobile-friendly restaurant apps that work on any tablet or phone — no expensive hardware needed",
        "cta": "Could I show you a quick mockup of what this would look like for your restaurant?",
    },
    "school": {
        "pain": "schools handling admissions, fee collection, attendance, and parent communication manually waste enormous staff time and often lose track of fees — which hits cash flow",
        "profit": "a school management platform automates fee reminders, attendance tracking, and parent updates — staff spend less time on paperwork and the school collects fees faster",
        "proof": "I have built management systems for educational institutions — simple enough for any staff member to use from day one",
        "cta": "I'd love to show you a working demo. Would a short call this week work for you?",
    },
    "college": {
        "pain": "colleges managing admissions, exams, and student records with spreadsheets risk data loss, make errors that affect students, and spend weeks on work that should take hours",
        "profit": "a complete management platform covers admissions, fee management, exam scheduling, attendance, and student portals — administration becomes measurably faster and more accurate",
        "proof": "I have built systems like this for educational institutions — I can show you one that is already live",
        "cta": "Would a 20-minute demo call this week be useful?",
    },
    "shop": {
        "pain": "retail businesses without proper inventory tracking regularly lose money through overstocking, stockouts, and untracked shrinkage — and without customer data, repeat business is hard to grow",
        "profit": "a custom inventory and sales management system gives real-time stock visibility, sale reports by product, and customer purchase history — turning data into decisions that grow profit",
        "proof": "I build inventory and point-of-sale systems tailored to each business type",
        "cta": "Interested in seeing what this would look like for your store?",
    },
    "real_estate": {
        "pain": "property agencies that track leads on WhatsApp and spreadsheets lose deals because follow-ups fall through the cracks — a missed follow-up is a missed commission",
        "profit": "a property CRM with automated follow-up reminders, lead pipeline, and client communication history means agents close more deals with the same effort — more commission, less lost leads",
        "proof": "I built a live Real Estate CRM — you can see it right now at crm.anquest.in",
        "cta": "I'd love to show you the live demo and discuss what a version for your agency would look like. When's a good time?",
    },
    "factory": {
        "pain": "manufacturing businesses tracking production orders and inventory manually risk costly errors, production delays, and stock shortages that halt the entire line",
        "profit": "a production and inventory management system gives floor managers and leadership real-time visibility — fewer delays, fewer errors, and clear accountability at every stage",
        "proof": "I build management dashboards specifically for operational businesses where accuracy is critical",
        "cta": "Would you like to see what this could look like for your facility?",
    },
    "gym": {
        "pain": "gyms managing memberships and payments manually lose income through expired memberships that are never renewed and miss opportunities to sell additional classes or services",
        "profit": "a gym management app with automatic renewal reminders, membership tracking, and class bookings increases retention and revenue without the owner having to chase anyone manually",
        "proof": "I build gym and fitness management apps that work on phone, tablet, and desktop",
        "cta": "Worth a 15-minute call to see a demo?",
    },
    "default": {
        "pain": "businesses that rely on manual processes and disconnected tools spend more time managing operations than growing them — and that inefficiency has a direct cost",
        "profit": "a custom digital system built around your exact workflow reduces admin time, improves accuracy, and gives management clear visibility — freeing up time and resources to focus on growth",
        "proof": "I build custom web and mobile applications for businesses — live examples at crm.anquestplus.com and crm.anquest.in",
        "cta": "I'd love to understand how your business currently works and show you what I could build. Would a short call work?",
    },
}


def _detect_industry(business_name: str, category: str) -> str:
    """Map business name/category to our pitch industry key."""
    text = f"{business_name} {category}".lower()
    for key in INDUSTRY_PITCH:
        if key in text:
            return key
    if any(w in text for w in ["medical", "health", "care", "pharma", "dental"]):
        return "clinic"
    if any(w in text for w in ["university", "institute", "academy", "school"]):
        return "college"
    if any(w in text for w in ["store", "retail", "mart", "supermarket"]):
        return "shop"
    if any(w in text for w in ["property", "realty", "estate", "housing"]):
        return "real_estate"
    if any(w in text for w in ["manufacture", "production", "industrial", "plant"]):
        return "factory"
    return "default"


# ─────────────────────────────────────────────────────────────
#  MAIN: Write a cold email for a business
# ─────────────────────────────────────────────────────────────
def write_client_email(
    business_name: str,
    category: str,
    contact_name: str = "",
    website: str = "",
) -> dict:
    """
    Generate a personalized cold-outreach email for a business.

    Returns:
        {
          "subject": str,
          "body": str,
          "industry": str,
          "used_ai": bool
        }
    """
    industry = _detect_industry(business_name, category)
    pitch = INDUSTRY_PITCH[industry]

    greeting = f"Hi {contact_name}," if contact_name else f"Hi {business_name} Team,"

    # ── Try Ollama first ──────────────────────────────────────
    if _is_ollama_running():
        prompt = f"""You are Shubham Yadav, a Software Engineer and App Developer with 2 years of experience building custom digital systems for businesses.
Write a SHORT, professional cold email to a potential client.

IMPORTANT RULES — READ CAREFULLY:
- DO NOT mention any technology names (no React, Node.js, MongoDB, JavaScript, Python, etc.)
- DO NOT say "Full Stack Developer" — say "Software Engineer" or "App Developer"
- Focus on the CLIENT'S business problem and profit, not on your skills
- Maximum 130 words
- Sound like a genuine human, not a developer CV

YOUR DETAILS:
- Name: {PROFILE["name"]}
- Role: Software Engineer & App Developer
- Portfolio: {PROFILE["portfolio"]}
- Past work: {PROFILE["projects"][0]}, {PROFILE["projects"][1]}

BUSINESS INFO:
- Business name: {business_name}
- Industry: {category}
- Website: {website or "not known"}

EMAIL STRUCTURE (follow exactly):
1. Greeting: {greeting}
2. ONE sentence about a specific business problem they likely have: {pitch["pain"]}
3. ONE sentence about how much this costs them / where they lose profit: {pitch["profit"]}
4. ONE sentence about what you can build to fix it (NO tech names): {pitch["proof"]}
5. Call to action: {pitch["cta"]}
6. Sign off exactly: Best regards, / Shubham Yadav | {PROFILE["email"]} | {PROFILE["portfolio"]}

Write ONLY the email body. No subject line. No extra commentary."""

        body = _ask_ollama(prompt)

        if body and len(body) > 50:
            # Generate subject line
            subject_prompt = f"""Write a short email subject line (max 8 words) for a cold outreach email to {business_name}, a {category} business. The email is about building them a custom digital system that solves their operations problem. Do NOT mention any technology names. Only output the subject line text, nothing else, no quotes."""
            subject = _ask_ollama(subject_prompt)
            if not subject or len(subject) > 100:
                subject = _fallback_subject(business_name, industry)

            # Clean up subject (remove quotes if AI added them)
            subject = subject.strip().strip('"').strip("'")

            logger.info(f"✅ Ollama wrote email for {business_name} ({industry})")
            return {
                "subject": subject,
                "body": body,
                "industry": industry,
                "used_ai": True,
            }
        else:
            logger.warning(f"⚠️  Ollama returned empty/short response — using template")

    else:
        logger.warning("⚠️  Ollama not running — using built-in email template (install Ollama for smarter emails)")

    # ── Fallback: hand-crafted template (always works) ────────
    return _template_email(business_name, category, greeting, industry, pitch, website)


def _fallback_subject(business_name: str, industry: str) -> str:
    subjects = {
        "hospital":    f"A digital system that could save {business_name} hours every week",
        "clinic":      f"How {business_name} could recover lost appointments automatically",
        "hotel":       f"Cut OTA commission fees — direct booking system for {business_name}",
        "restaurant":  f"More covers, fewer missed orders — a quick idea for {business_name}",
        "school":      f"Automate fee collection and admin for {business_name}",
        "college":     f"A management platform built around {business_name}'s workflow",
        "shop":        f"Real-time inventory visibility for {business_name}",
        "real_estate": f"Never lose a lead again — a CRM idea for {business_name}",
        "factory":     f"Production visibility that prevents costly delays — {business_name}",
        "gym":         f"Automatic renewals and more member revenue for {business_name}",
        "default":     f"A digital system built around how {business_name} works",
    }
    return subjects.get(industry, subjects["default"])


def _template_email(
    business_name: str,
    category: str,
    greeting: str,
    industry: str,
    pitch: dict,
    website: str,
) -> dict:
    """Always-works template email — no AI needed, no tech names."""
    body = f"""{greeting}

I came across {business_name} and wanted to share something directly relevant to your business.

{pitch["pain"].capitalize()}.

{pitch["profit"].capitalize()}.

{pitch["proof"].capitalize()}.

{pitch["cta"]}

Best regards,
Shubham Yadav
Software Engineer & App Developer
{PROFILE["email"]} | {PROFILE["portfolio"]}"""

    return {
        "subject": _fallback_subject(business_name, industry),
        "body": body,
        "industry": industry,
        "used_ai": False,
    }


# ─────────────────────────────────────────────────────────────
#  QUICK TEST
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing Ollama writer...\n")

    if _is_ollama_running():
        print("✅ Ollama is running!\n")
    else:
        print("⚠️  Ollama not running — will use templates\n")
        print("   To enable AI: ollama serve  (in another terminal)\n")

    result = write_client_email(
        business_name="City General Hospital",
        category="hospital",
        contact_name="Dr. Sharma",
        website="https://cityhospital.com",
    )
    print(f"SUBJECT: {result['subject']}\n")
    print(f"BODY:\n{result['body']}\n")
    print(f"Industry: {result['industry']} | Used AI: {result['used_ai']}")
