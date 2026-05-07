"""
job_hunter_agent/contact_finder.py
=====================================
Visits a business website and extracts:
  - Email addresses (from contact/about/home pages)
  - Phone numbers
  - Contact person name (best guess)

Uses requests + BeautifulSoup — no browser needed for this step.
Called by biz_scraper.py and client_hunter.py.
"""

import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from typing import Optional, Tuple
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Pages most likely to have contact info
CONTACT_PATHS = [
    "/contact",
    "/contact-us",
    "/contact_us",
    "/contactus",
    "/about",
    "/about-us",
    "/about_us",
    "/reach-us",
    "/get-in-touch",
    "/team",
    "/support",
    "/info",
    "/help",
]

EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,7}"
)
PHONE_REGEX = re.compile(
    r"(?:\+?\d[\d\s\-\(\)]{7,15}\d)"
)

# Skip these generic/useless emails
SKIP_EMAILS = {
    "example@example.com",
    "test@test.com",
    "noreply@",
    "no-reply@",
    "donotreply@",
    "support@sentry.io",
    "webmaster@",
    "w3schools.com",
    "schema.org",
    "example.org",
}


def _is_valid_email(email: str) -> bool:
    e = email.lower()
    for skip in SKIP_EMAILS:
        if skip in e:
            return False
    # reject image/font filenames accidentally matched
    if any(e.endswith(ext) for ext in [".png", ".jpg", ".gif", ".svg", ".woff"]):
        return False
    return True


def _extract_emails_from_text(text: str) -> list:
    found = EMAIL_REGEX.findall(text)
    return [e for e in found if _is_valid_email(e)]


def _extract_phone_from_text(text: str) -> Optional[str]:
    matches = PHONE_REGEX.findall(text)
    for m in matches:
        cleaned = re.sub(r"[\s\-\(\)]", "", m)
        if 7 <= len(cleaned) <= 15:
            return m.strip()
    return None


def _fetch_page(url: str, timeout: int = 10) -> Optional[str]:
    """Fetch page HTML, return None on failure."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code == 200:
            return r.text
    except Exception as e:
        logger.debug(f"Fetch failed {url}: {e}")
    return None


def _build_contact_urls(base_url: str) -> list:
    """Build list of URLs to check for contact info."""
    parsed = urlparse(base_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    urls = [base_url]  # home page first
    for path in CONTACT_PATHS:
        urls.append(base + path)
    return urls


def _guess_contact_name(soup: BeautifulSoup) -> Optional[str]:
    """Try to find a real person's name on the page."""
    # Look for common patterns like "Contact John Smith" or "Dr. Sharma"
    patterns = [
        r"\b(?:Dr\.?|Mr\.?|Mrs\.?|Ms\.?|Prof\.?)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?",
        r"(?:Director|Manager|Owner|CEO|Founder|Head)\s*[:\-]?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
    ]
    text = soup.get_text(" ")
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(0).strip()
            if 3 < len(name) < 50:
                return name
    return None


# ─────────────────────────────────────────────────────────────
#  MAIN FUNCTION
# ─────────────────────────────────────────────────────────────
def find_contact_info(website_url: str) -> dict:
    """
    Visit a website and extract contact details.

    Returns:
        {
          "email": str or None,
          "all_emails": [str, ...],
          "phone": str or None,
          "contact_name": str or None,
          "source_url": str,
        }
    """
    if not website_url:
        return _empty_result()

    # Normalize URL
    if not website_url.startswith("http"):
        website_url = "https://" + website_url

    all_emails = []
    phone = None
    contact_name = None
    source_url = website_url

    urls_to_check = _build_contact_urls(website_url)

    for url in urls_to_check:
        html = _fetch_page(url)
        if not html:
            time.sleep(0.3)
            continue

        soup = BeautifulSoup(html, "html.parser")

        # Extract emails from full page text
        page_text = soup.get_text(" ")
        emails = _extract_emails_from_text(page_text)

        # Also scan href="mailto:..." links — most reliable
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("mailto:"):
                email = href.replace("mailto:", "").split("?")[0].strip()
                if email and _is_valid_email(email):
                    emails.insert(0, email)  # mailto links are most reliable

        for e in emails:
            if e not in all_emails:
                all_emails.append(e)

        # Extract phone
        if not phone:
            phone = _extract_phone_from_text(page_text)

        # Try to find a real name
        if not contact_name:
            contact_name = _guess_contact_name(soup)

        if all_emails:
            source_url = url
            # Prefer non-generic emails (info@, contact@ are ok but personal better)
            personal = [e for e in all_emails if not any(
                e.lower().startswith(g) for g in ["info@", "contact@", "admin@", "hello@", "mail@"]
            )]
            best_email = personal[0] if personal else all_emails[0]

            logger.info(f"📧 Found email at {url}: {best_email}")
            return {
                "email": best_email,
                "all_emails": all_emails,
                "phone": phone,
                "contact_name": contact_name,
                "source_url": source_url,
            }

        time.sleep(0.5)  # be polite

    logger.debug(f"No email found for {website_url}")
    return {
        "email": None,
        "all_emails": [],
        "phone": phone,
        "contact_name": contact_name,
        "source_url": source_url,
    }


def _empty_result() -> dict:
    return {
        "email": None,
        "all_emails": [],
        "phone": None,
        "contact_name": None,
        "source_url": "",
    }


# ─────────────────────────────────────────────────────────────
#  QUICK TEST
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_sites = [
        "https://example.com",
    ]
    for site in test_sites:
        print(f"\nChecking: {site}")
        result = find_contact_info(site)
        print(f"  Email:   {result['email']}")
        print(f"  Phone:   {result['phone']}")
        print(f"  Name:    {result['contact_name']}")
        print(f"  Source:  {result['source_url']}")
