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
OLLAMA_MODEL = "llama3"  # change to "mistral" or "phi3" if you prefer

# ── Shubham's profile snapshot used in every prompt ──────────
PROFILE = {
    "name": "Shubham Yadav",
    "title": "Full Stack Developer (React / Node.js / React Native)",
    "experience": "2 years",
    "skills": "React.js, Next.js, React Native, Node.js, Express.js, MongoDB, MySQL, CRM, ERP, Web & Mobile Apps",
    "portfolio": "https://github.com/ShubhamYadav0533",
    "email": "shubhamyadav0533@gmail.com",
    "projects": [
        "Hospital CRM — crm.anquestplus.com (React + Node + MongoDB)",
        "Real Estate CRM — crm.anquest.in (MERN stack)",
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
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 400,
                    },
                },
                timeout=120,
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
        "pain": "managing patient records, appointments, and billing with outdated spreadsheets or paper",
        "solution": "a custom Hospital CRM/ERP with patient management, appointment scheduling, staff management, and billing — similar to one I already built at crm.anquestplus.com",
        "cta": "Would you be open to a 15-minute call to see how this could save your team hours every week?",
    },
    "clinic": {
        "pain": "tracking patient appointments and medical records manually",
        "solution": "a clean clinic management web app with patient records, appointment calendar, prescription tracking, and billing dashboard",
        "cta": "I'd love to show you a quick demo of similar work I've done. Would that be useful?",
    },
    "hotel": {
        "pain": "managing bookings, room availability, and guest communication across multiple tools",
        "solution": "a custom Hotel Management System with booking engine, room dashboard, guest CRM, and reporting",
        "cta": "I can show you a prototype in 48 hours. Would you like to see it?",
    },
    "restaurant": {
        "pain": "taking orders and managing tables without a clean digital system",
        "solution": "a mobile-friendly Restaurant App with online ordering, table management, and kitchen dashboard — works on any device",
        "cta": "Could I show you a quick mockup of what this would look like for your restaurant?",
    },
    "school": {
        "pain": "managing student admissions, fee tracking, attendance, and communication with parents manually",
        "solution": "a complete College/School CRM with student management, fee tracking, timetable, attendance, and parent portal",
        "cta": "I've built similar systems for educational institutions. Can I show you a quick demo?",
    },
    "college": {
        "pain": "handling admissions, fee management, exam scheduling, and student records with spreadsheets",
        "solution": "a full College Management ERP — student portal, fee management, exam module, staff management, and admin dashboard",
        "cta": "Would a 20-minute demo call this week work for you?",
    },
    "shop": {
        "pain": "tracking inventory, sales, and customers without a proper system",
        "solution": "a custom Inventory + POS system with barcode scanning, stock alerts, sales reports, and customer management",
        "cta": "I can build a prototype specifically for your shop type. Interested in seeing it?",
    },
    "real_estate": {
        "pain": "tracking leads, properties, and client communications across WhatsApp and spreadsheets",
        "solution": "a Real Estate CRM with lead pipeline, property listings, client communication, and automated follow-ups — like crm.anquest.in which I already built",
        "cta": "I'd love to show you the live demo of a Real Estate CRM I've already built. When's a good time?",
    },
    "factory": {
        "pain": "managing production orders, inventory, and workforce tracking manually",
        "solution": "a lightweight Manufacturing ERP with production tracking, inventory management, and staff dashboard",
        "cta": "Would you like to see what this could look like for your operations?",
    },
    "gym": {
        "pain": "managing memberships, class bookings, and payments without automation",
        "solution": "a Gym Management App with membership tracking, class scheduling, payment management, and mobile check-in",
        "cta": "I can demo a similar app I built — would that be worth 15 minutes of your time?",
    },
    "default": {
        "pain": "managing your business operations without a proper digital system",
        "solution": "a custom web or mobile app tailored to your exact workflow — whether it's a CRM, ERP, booking system, or internal tool",
        "cta": "I'd love to understand your current process and show you what I could build. Would a quick call work?",
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
        prompt = f"""You are Shubham Yadav, a Full Stack Developer with 2 years of experience.
Write a SHORT, professional cold email to a potential client.

YOUR DETAILS:
- Name: {PROFILE["name"]}
- Skills: {PROFILE["skills"]}
- Portfolio: {PROFILE["portfolio"]}
- Past work: {", ".join(PROFILE["projects"])}

BUSINESS INFO:
- Business name: {business_name}
- Industry/type: {category}
- Website: {website or "not known"}

EMAIL RULES:
1. Start with: {greeting}
2. Maximum 120 words — short and punchy
3. Mention ONE specific problem they likely face: {pitch["pain"]}
4. Mention ONE solution you can build: {pitch["solution"]}
5. End with this exact call to action: {pitch["cta"]}
6. Sign off: Best regards, Shubham Yadav | {PROFILE["email"]} | {PROFILE["portfolio"]}
7. NO fluff, NO "I hope this email finds you well", NO buzzwords
8. Sound human and genuine, not salesy

Write only the email body, no subject line."""

        body = _ask_ollama(prompt)

        if body and len(body) > 50:
            # Generate subject line
            subject_prompt = f"""Write a short email subject line (max 8 words) for a cold email to {business_name} (a {category} business) about offering to build them a custom {pitch["solution"].split("—")[0].strip()}.
Only output the subject line, nothing else."""
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
        "hospital": f"Custom Hospital CRM for {business_name}",
        "clinic": f"Clinic Management System for {business_name}",
        "hotel": f"Hotel Management App — {business_name}",
        "restaurant": f"Restaurant App for {business_name}",
        "school": f"School Management System — {business_name}",
        "college": f"College ERP for {business_name}",
        "shop": f"Inventory & POS System for {business_name}",
        "real_estate": f"Real Estate CRM for {business_name}",
        "factory": f"Manufacturing ERP — {business_name}",
        "gym": f"Gym Management App for {business_name}",
        "default": f"Custom Web/App Solution for {business_name}",
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
    """Always-works template email — no AI needed."""
    body = f"""{greeting}

I came across {business_name} and noticed that many {category} businesses struggle with {pitch["pain"]}.

I'm Shubham Yadav, a Full Stack Developer with 2 years of experience building production web and mobile applications. I specialize in {pitch["solution"]}.

Some of my relevant work:
• Hospital CRM → crm.anquestplus.com (React + Node.js + MongoDB)
• Real Estate CRM → crm.anquest.in (full MERN stack)

{pitch["cta"]}

Best regards,
Shubham Yadav
Full Stack Developer | React · Node.js · React Native
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
