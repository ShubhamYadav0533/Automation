"""
job_hunter_agent/ollama_writer.py
===================================
FREE local AI using Ollama — NO API KEY NEEDED.
Writes bilingual cold emails: local language on top, English below.

Supported languages: Japanese, Russian, Korean, Chinese, French,
German, Spanish, Portuguese, Dutch, Turkish, Thai, Arabic, Indonesian.
"""

import requests
import logging
import json

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral"

# ── Shubham's profile ─────────────────────────────────────────
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

# ─────────────────────────────────────────────────────────────
#  CITY → LANGUAGE MAPPING
# ─────────────────────────────────────────────────────────────
CITY_LANGUAGE = {
    # Japanese
    "tokyo": "japanese", "osaka": "japanese", "kyoto": "japanese",
    "japan": "japanese",
    # Russian
    "moscow": "russian", "russia": "russian", "saint petersburg": "russian",
    # Korean
    "seoul": "korean", "south korea": "korean", "busan": "korean",
    # Chinese
    "beijing": "chinese", "shanghai": "chinese", "china": "chinese",
    "shenzhen": "chinese", "hong kong": "chinese",
    # French
    "paris": "french", "france": "french", "lyon": "french",
    # German
    "berlin": "german", "frankfurt": "german", "germany": "german",
    "munich": "german", "hamburg": "german",
    # Spanish
    "barcelona": "spanish", "madrid": "spanish", "spain": "spanish",
    # Portuguese
    "são paulo": "portuguese", "sao paulo": "portuguese",
    "brazil": "portuguese", "lisbon": "portuguese",
    # Dutch
    "amsterdam": "dutch", "rotterdam": "dutch", "netherlands": "dutch",
    # Turkish
    "istanbul": "turkish", "turkey": "turkish", "ankara": "turkish",
    # Thai
    "bangkok": "thai", "thailand": "thai",
    # Arabic
    "dubai": "arabic", "uae": "arabic", "abu dhabi": "arabic",
    "riyadh": "arabic", "doha": "arabic",
    # Indonesian
    "bali": "indonesian", "jakarta": "indonesian", "indonesia": "indonesian",
    # Czech
    "prague": "czech", "czech republic": "czech",
    # Italian
    "rome": "italian", "milan": "italian", "italy": "italian",
    # Polish
    "warsaw": "polish", "poland": "polish",
    # Swedish
    "stockholm": "swedish", "sweden": "swedish",
    # Norwegian
    "oslo": "norwegian", "norway": "norwegian",
    # Finnish
    "helsinki": "finnish", "finland": "finnish",
    # Default English-speaking countries — no translation needed
    "london": "english", "sydney": "english", "melbourne": "english",
    "toronto": "english", "new york": "english", "los angeles": "english",
    "chicago": "english", "singapore": "english", "johannesburg": "english",
    "australia": "english", "canada": "english", "uk": "english",
    "vienna": "english",  # Austrian businesses often prefer English
}


def get_language_for_city(city: str) -> str:
    """Return the local language for a city/country. Default: english."""
    return CITY_LANGUAGE.get(city.lower().strip(), "english")


# ─────────────────────────────────────────────────────────────
#  TRANSLATED GREETING / SIGN-OFF / CTA PER LANGUAGE
# ─────────────────────────────────────────────────────────────
LANG_PHRASES = {
    "japanese": {
        "greeting_team":  "ご担当者様へ",
        "intro":          "はじめまして。私はShubham Yadavと申します。ソフトウェアエンジニア・アプリ開発者として、貴社のビジネス課題をデジタルシステムで解決するお手伝いをしております。",
        "problem_prefix": "貴社では現在、",
        "solution_prefix":"このような課題に対して、",
        "proof_prefix":   "私はすでに同様のシステムを構築しており、",
        "cta":            "ご興味がございましたら、15分ほどのオンラインミーティングでご説明させていただけますでしょうか？",
        "closing":        "何卒よろしくお願いいたします。\nShubham Yadav\n{email} | {portfolio}",
        "divider":        "─── English version below ───",
    },
    "russian": {
        "greeting_team":  "Здравствуйте,",
        "intro":          "Меня зовут Шубхам Ядав, я разработчик программного обеспечения и мобильных приложений. Я специализируюсь на создании цифровых систем, которые помогают бизнесу работать эффективнее.",
        "problem_prefix": "Многие компании в вашей сфере сталкиваются с тем, что",
        "solution_prefix":"Я могу разработать для вас систему, которая",
        "proof_prefix":   "Среди моих реализованных проектов —",
        "cta":            "Буду рад провести 15-минутную встречу онлайн и показать, как это работает. Удобно ли вам?",
        "closing":        "С уважением,\nShubham Yadav\n{email} | {portfolio}",
        "divider":        "─── English version below ───",
    },
    "korean": {
        "greeting_team":  "안녕하세요,",
        "intro":          "저는 소프트웨어 엔지니어 겸 앱 개발자 Shubham Yadav입니다. 기업의 운영 문제를 맞춤형 디지털 시스템으로 해결해 드리고 있습니다.",
        "problem_prefix": "현재 많은 기업들이 겪고 있는 문제는",
        "solution_prefix":"이 문제를 해결하기 위해",
        "proof_prefix":   "저는 이미 유사한 시스템을 구축한 경험이 있으며,",
        "cta":            "15분 온라인 미팅을 통해 자세히 설명드릴 수 있을까요?",
        "closing":        "감사합니다.\nShubham Yadav\n{email} | {portfolio}",
        "divider":        "─── English version below ───",
    },
    "chinese": {
        "greeting_team":  "您好，",
        "intro":          "我是软件工程师兼应用开发者 Shubham Yadav。我专注于为企业构建定制化数字系统，帮助解决运营效率问题。",
        "problem_prefix": "许多企业面临的问题是",
        "solution_prefix":"为解决这一问题，我可以为您构建",
        "proof_prefix":   "我已有类似项目的成功案例，",
        "cta":            "如果您有兴趣，我们可以安排一个15分钟的在线会议，我来为您详细演示。",
        "closing":        "此致敬礼，\nShubham Yadav\n{email} | {portfolio}",
        "divider":        "─── English version below ───",
    },
    "french": {
        "greeting_team":  "Bonjour,",
        "intro":          "Je m'appelle Shubham Yadav, développeur de logiciels et d'applications. Je conçois des systèmes digitaux sur mesure pour aider les entreprises à gagner en efficacité.",
        "problem_prefix": "De nombreuses entreprises dans votre secteur perdent du temps et de l'argent parce que",
        "solution_prefix":"Je peux concevoir un système qui",
        "proof_prefix":   "J'ai déjà réalisé des projets similaires, notamment",
        "cta":            "Seriez-vous disponible pour un appel de 15 minutes cette semaine ?",
        "closing":        "Cordialement,\nShubham Yadav\n{email} | {portfolio}",
        "divider":        "─── English version below ───",
    },
    "german": {
        "greeting_team":  "Sehr geehrte Damen und Herren,",
        "intro":          "Mein Name ist Shubham Yadav, ich bin Softwareentwickler und App-Entwickler. Ich entwickle maßgeschneiderte digitale Systeme, die Unternehmen effizienter machen.",
        "problem_prefix": "Viele Unternehmen in Ihrer Branche verlieren täglich Zeit und Geld, weil",
        "solution_prefix":"Ich kann ein System entwickeln, das",
        "proof_prefix":   "Ich habe bereits ähnliche Projekte erfolgreich umgesetzt, darunter",
        "cta":            "Wäre ein kurzes 15-minütiges Online-Gespräch diese Woche möglich?",
        "closing":        "Mit freundlichen Grüßen,\nShubham Yadav\n{email} | {portfolio}",
        "divider":        "─── English version below ───",
    },
    "spanish": {
        "greeting_team":  "Estimado equipo,",
        "intro":          "Me llamo Shubham Yadav, soy desarrollador de software y aplicaciones. Me especializo en crear sistemas digitales personalizados que ayudan a las empresas a ser más eficientes.",
        "problem_prefix": "Muchas empresas en su sector pierden tiempo y dinero porque",
        "solution_prefix":"Puedo desarrollar un sistema que",
        "proof_prefix":   "Ya he realizado proyectos similares con éxito, como",
        "cta":            "¿Estaría disponible para una llamada rápida de 15 minutos esta semana?",
        "closing":        "Atentamente,\nShubham Yadav\n{email} | {portfolio}",
        "divider":        "─── English version below ───",
    },
    "portuguese": {
        "greeting_team":  "Prezado(a),",
        "intro":          "Meu nome é Shubham Yadav, sou engenheiro de software e desenvolvedor de aplicativos. Especializo-me em criar sistemas digitais personalizados para empresas.",
        "problem_prefix": "Muitas empresas do seu setor perdem tempo e dinheiro porque",
        "solution_prefix":"Posso desenvolver um sistema que",
        "proof_prefix":   "Já realizei projetos semelhantes com sucesso, como",
        "cta":            "Poderia agendar uma chamada de 15 minutos esta semana?",
        "closing":        "Atenciosamente,\nShubham Yadav\n{email} | {portfolio}",
        "divider":        "─── English version below ───",
    },
    "dutch": {
        "greeting_team":  "Geachte heer/mevrouw,",
        "intro":          "Mijn naam is Shubham Yadav, software-engineer en app-ontwikkelaar. Ik specialiseer mij in op maat gemaakte digitale systemen die bedrijven efficiënter maken.",
        "problem_prefix": "Veel bedrijven in uw sector verliezen tijd en geld doordat",
        "solution_prefix":"Ik kan een systeem bouwen dat",
        "proof_prefix":   "Ik heb soortgelijke projecten al succesvol afgerond, waaronder",
        "cta":            "Zou een kort gesprek van 15 minuten deze week mogelijk zijn?",
        "closing":        "Met vriendelijke groet,\nShubham Yadav\n{email} | {portfolio}",
        "divider":        "─── English version below ───",
    },
    "turkish": {
        "greeting_team":  "Sayın yetkili,",
        "intro":          "Adım Shubham Yadav, yazılım mühendisi ve uygulama geliştiricisiyim. İşletmelerin operasyonel sorunlarını özel dijital sistemlerle çözmeye odaklanıyorum.",
        "problem_prefix": "Sektörünüzdeki birçok işletme şu sorunla karşılaşıyor:",
        "solution_prefix":"Bu sorunu çözmek için",
        "proof_prefix":   "Daha önce benzer projeler geliştirdim,",
        "cta":            "Bu konuyu 15 dakikalık bir çevrimiçi görüşmede anlatabilir miyim?",
        "closing":        "Saygılarımla,\nShubham Yadav\n{email} | {portfolio}",
        "divider":        "─── English version below ───",
    },
    "thai": {
        "greeting_team":  "เรียนท่านผู้เกี่ยวข้อง",
        "intro":          "ผมชื่อ Shubham Yadav เป็นวิศวกรซอฟต์แวร์และนักพัฒนาแอปพลิเคชัน ผมเชี่ยวชาญในการสร้างระบบดิจิทัลแบบกำหนดเองสำหรับธุรกิจ",
        "problem_prefix": "ธุรกิจหลายแห่งในอุตสาหกรรมของคุณสูญเสียเวลาและรายได้เพราะ",
        "solution_prefix":"ผมสามารถพัฒนาระบบที่",
        "proof_prefix":   "ผมเคยสร้างโปรเจกต์ที่คล้ายกันสำเร็จแล้ว เช่น",
        "cta":            "คุณสะดวกนัดประชุมออนไลน์ 15 นาทีสัปดาห์นี้ไหมครับ?",
        "closing":        "ด้วยความนับถือ\nShubham Yadav\n{email} | {portfolio}",
        "divider":        "─── English version below ───",
    },
    "arabic": {
        "greeting_team":  "السيد/السيدة المحترم/ة،",
        "intro":          "اسمي Shubham Yadav، مهندس برمجيات ومطور تطبيقات. أتخصص في بناء أنظمة رقمية مخصصة تساعد الشركات على تحقيق كفاءة أعلى.",
        "problem_prefix": "تعاني كثير من الشركات في قطاعكم من مشكلة أن",
        "solution_prefix":"أستطيع بناء نظام يساعدكم على",
        "proof_prefix":   "لدي مشاريع مشابهة ناجحة، منها",
        "cta":            "هل يمكننا تحديد موعد لمكالمة قصيرة مدتها 15 دقيقة هذا الأسبوع؟",
        "closing":        "مع التقدير،\nShubham Yadav\n{email} | {portfolio}",
        "divider":        "─── English version below ───",
    },
    "indonesian": {
        "greeting_team":  "Kepada Yth.,",
        "intro":          "Nama saya Shubham Yadav, seorang software engineer dan pengembang aplikasi. Saya mengkhususkan diri dalam membangun sistem digital khusus untuk membantu bisnis beroperasi lebih efisien.",
        "problem_prefix": "Banyak bisnis di industri Anda kehilangan waktu dan pendapatan karena",
        "solution_prefix":"Saya dapat membangun sistem yang",
        "proof_prefix":   "Saya telah berhasil menyelesaikan proyek serupa, termasuk",
        "cta":            "Apakah Anda bersedia untuk panggilan online 15 menit minggu ini?",
        "closing":        "Hormat saya,\nShubham Yadav\n{email} | {portfolio}",
        "divider":        "─── English version below ───",
    },
    "czech": {
        "greeting_team":  "Vážená paní / Vážený pane,",
        "intro":          "Jmenuji se Shubham Yadav, jsem softwarový inženýr a vývojář aplikací. Specializuji se na tvorbu digitálních systémů na míru pro firmy.",
        "problem_prefix": "Mnoho firem ve vašem odvětví přichází o čas a peníze, protože",
        "solution_prefix":"Mohu vytvořit systém, který",
        "proof_prefix":   "Úspěšně jsem dokončil podobné projekty, například",
        "cta":            "Bylo by možné domluvit si 15minutový online hovor tento týden?",
        "closing":        "S pozdravem,\nShubham Yadav\n{email} | {portfolio}",
        "divider":        "─── English version below ───",
    },
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
    city: str = "",
) -> dict:
    """
    Generate a bilingual cold-outreach email:
      - Local language section on top
      - English section below
    Returns: { "subject": str, "body": str, "industry": str, "used_ai": bool }
    """
    industry = _detect_industry(business_name, category)
    pitch    = INDUSTRY_PITCH[industry]
    language = get_language_for_city(city)

    greeting_en = f"Hi {contact_name}," if contact_name else f"Hi {business_name} Team,"

    # ── Try Ollama first ──────────────────────────────────────
    if _is_ollama_running():
        english_body = _ollama_english_body(business_name, category, greeting_en, pitch, website)
        if english_body:
            subject = _ollama_subject(business_name, industry)
            if language != "english":
                local_body = _ollama_local_body(business_name, category, language, pitch, city)
                if local_body:
                    full_body = _combine_bilingual(local_body, english_body, language)
                else:
                    full_body = _template_local_section(business_name, language, pitch, contact_name) + "\n\n" + english_body
            else:
                full_body = english_body

            logger.info(f"✅ Ollama wrote {'bilingual ' + language if language != 'english' else 'English'} email for {business_name}")
            return {"subject": subject, "body": full_body, "industry": industry, "used_ai": True}

        logger.warning("⚠️  Ollama returned empty — using template")

    else:
        logger.warning("⚠️  Ollama not running — using built-in template")

    # ── Fallback: template ────────────────────────────────────
    return _template_email(business_name, category, greeting_en, industry, pitch, website, language, contact_name)


def _ollama_english_body(business_name, category, greeting, pitch, website) -> str:
    prompt = f"""You are Shubham Yadav, a Software Engineer and App Developer.
Write a SHORT professional cold email in English only.

RULES:
- DO NOT mention any technology names (no React, Node.js, Python, etc.)
- DO NOT say "Full Stack Developer"
- Max 120 words
- Sound human, not like a CV

EMAIL STRUCTURE:
1. Greeting: {greeting}
2. One sentence about their likely business problem: {pitch["pain"]}
3. One sentence about what you can build to fix it (no tech names)
4. One sentence proof: {pitch["proof"]}
5. Call to action: {pitch["cta"]}
6. Sign off: Best regards, / Shubham Yadav | {PROFILE["email"]} | {PROFILE["portfolio"]}

Business: {business_name} ({category})
Website: {website or "unknown"}

Write ONLY the email body. No subject line."""
    return _ask_ollama(prompt)


def _ollama_local_body(business_name, category, language, pitch, city) -> str:
    lang_names = {
        "japanese": "Japanese", "russian": "Russian", "korean": "Korean",
        "chinese": "Simplified Chinese", "french": "French", "german": "German",
        "spanish": "Spanish", "portuguese": "Portuguese", "dutch": "Dutch",
        "turkish": "Turkish", "thai": "Thai", "arabic": "Arabic",
        "indonesian": "Indonesian", "czech": "Czech",
    }
    lang_display = lang_names.get(language, language.title())
    prompt = f"""Write a very short, professional cold email introduction in {lang_display} for a business in {city}.

The email is from Shubham Yadav, a Software Engineer and App Developer.
The business is: {business_name} ({category})
Business problem to mention: {pitch["pain"]}
What Shubham can build: custom digital management system (no tech names)
Proof: {pitch["proof"]}
Call to action: offer a 15-minute online meeting

Keep it under 100 words. Write ONLY the email body in {lang_display}. No English. No subject line."""
    return _ask_ollama(prompt)


def _ollama_subject(business_name: str, industry: str) -> str:
    prompt = f"""Write a short email subject line (max 8 words) for a cold outreach email to {business_name}, a {industry} business. About building a custom digital system that solves their operations problem. DO NOT mention any technology names. Output ONLY the subject line text."""
    subject = _ask_ollama(prompt)
    if not subject or len(subject) > 100:
        return _fallback_subject(business_name, industry)
    return subject.strip().strip('"').strip("'")


def _combine_bilingual(local_body: str, english_body: str, language: str) -> str:
    phrases = LANG_PHRASES.get(language, {})
    divider = phrases.get("divider", "─── English version below ───")
    return f"{local_body.strip()}\n\n{divider}\n\n{english_body.strip()}"


def _template_local_section(business_name: str, language: str, pitch: dict, contact_name: str = "") -> str:
    """Build the local-language section from pre-written phrases."""
    p = LANG_PHRASES.get(language)
    if not p:
        return ""
    greeting = p["greeting_team"]
    if contact_name:
        greeting = greeting.rstrip(",") + f" {contact_name},"
    closing = p["closing"].format(email=PROFILE["email"], portfolio=PROFILE["portfolio"])

    # Shorten pitch to 1–2 sentence fragments
    pain_short    = pitch["pain"][:120].rstrip(",.")
    profit_short  = pitch["profit"][:120].rstrip(",.")
    proof_short   = pitch["proof"][:100].rstrip(",.")

    return (
        f"{greeting}\n\n"
        f"{p['intro']}\n\n"
        f"{p['problem_prefix']} {pain_short}.\n"
        f"{p['solution_prefix']} {profit_short}.\n"
        f"{p['proof_prefix']} {proof_short}.\n\n"
        f"{p['cta']}\n\n"
        f"{closing}"
    )


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
    language: str = "english",
    contact_name: str = "",
) -> dict:
    """Always-works template email — bilingual if language != english."""
    english_body = f"""{greeting}

I came across {business_name} and wanted to share something directly relevant to your business.

{pitch["pain"].capitalize()}.

{pitch["profit"].capitalize()}.

{pitch["proof"].capitalize()}.

{pitch["cta"]}

Best regards,
Shubham Yadav
Software Engineer & App Developer
{PROFILE["email"]} | {PROFILE["portfolio"]}"""

    if language != "english" and language in LANG_PHRASES:
        local_section = _template_local_section(business_name, language, pitch, contact_name)
        phrases = LANG_PHRASES[language]
        divider = phrases.get("divider", "─── English version below ───")
        full_body = f"{local_section}\n\n{divider}\n\n{english_body}"
    else:
        full_body = english_body

    return {
        "subject": _fallback_subject(business_name, industry),
        "body": full_body,
        "industry": industry,
        "used_ai": False,
    }


# ─────────────────────────────────────────────────────────────
#  QUICK TEST
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing bilingual Ollama writer...\n")

    if _is_ollama_running():
        print("✅ Ollama is running!\n")
    else:
        print("⚠️  Ollama not running — will use templates\n")

    test_cases = [
        ("Tokyo General Hospital",  "hospital",    "Tokyo"),
        ("Berliner Klinik GmbH",    "clinic",      "Berlin"),
        ("Paris Boutique Hotel",    "hotel",       "Paris"),
        ("Moscow Real Estate",      "real_estate", "Moscow"),
        ("Seoul Fitness Club",      "gym",         "Seoul"),
        ("Amsterdam Dental Care",   "clinic",      "Amsterdam"),
        ("Dubai Grand Hotel",       "hotel",       "Dubai"),
        ("City Hospital London",    "hospital",    "London"),
    ]

    for name, cat, city in test_cases:
        lang = get_language_for_city(city)
        result = write_client_email(name, cat, city=city)
        print(f"{'='*60}")
        print(f"Business : {name}  [{city} → {lang}]")
        print(f"SUBJECT  : {result['subject']}")
        print(f"BODY:\n{result['body']}")
        print()
