"""
job_hunter_agent/biz_scraper.py
=================================
Searches for real businesses using a REAL Chrome browser (Selenium).
No API keys. Works like a human browsing.

Sources:
  1. Google Search  — "hospitals in Amsterdam", "restaurants in Dubai", etc.
  2. Google Maps    — scrolls map listings for businesses with websites
  3. JustDial       — Indian business directory (bonus)
  4. Yelp           — Western businesses

Requires:
  pip install selenium undetected-chromedriver webdriver-manager

Chrome must be installed on your system.
"""

import time
import random
import logging
import re
from typing import List, Dict

logger = logging.getLogger(__name__)

# ── Try to import Selenium ────────────────────────────────────
try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        TimeoutException, NoSuchElementException, WebDriverException
    )
    SELENIUM_OK = True
except ImportError:
    SELENIUM_OK = False
    logger.warning("⚠️  undetected-chromedriver not installed. Run: pip install undetected-chromedriver selenium")


# ─────────────────────────────────────────────────────────────
#  TARGET BUSINESS CATEGORIES × CITIES
#  Shubham's best client niches
# ─────────────────────────────────────────────────────────────
SEARCH_TARGETS = [
    # (category_label, search_keyword, city)
    # ── Hospitals / Clinics ──────────────────────────────────
    ("hospital",    "private hospital",           "Amsterdam"),
    ("hospital",    "private hospital",           "Dubai"),
    ("hospital",    "private hospital",           "London"),
    ("hospital",    "multispecialty hospital",    "Noida"),
    ("hospital",    "multispecialty hospital",    "Delhi"),
    ("hospital",    "private hospital",           "Toronto"),
    ("hospital",    "private hospital",           "Singapore"),
    ("hospital",    "private hospital",           "Sydney"),
    ("hospital",    "private hospital",           "Frankfurt"),
    ("hospital",    "private hospital",           "Paris"),
    ("hospital",    "private hospital",           "New York"),
    ("hospital",    "private hospital",           "Chicago"),
    ("hospital",    "private hospital",           "Mumbai"),
    ("hospital",    "private hospital",           "Bangalore"),
    ("hospital",    "private hospital",           "Hyderabad"),
    ("clinic",      "private clinic",             "Berlin"),
    ("clinic",      "dental clinic",              "Toronto"),
    ("clinic",      "dental clinic",              "London"),
    ("clinic",      "dental clinic",              "Dubai"),
    ("clinic",      "medical clinic",             "Amsterdam"),
    ("clinic",      "eye clinic",                 "Singapore"),
    ("clinic",      "skin clinic",                "Mumbai"),
    ("clinic",      "physiotherapy clinic",       "London"),
    # ── Hotels ──────────────────────────────────────────────
    ("hotel",       "boutique hotel",             "Amsterdam"),
    ("hotel",       "business hotel",             "Dubai"),
    ("hotel",       "boutique hotel",             "London"),
    ("hotel",       "boutique hotel",             "Paris"),
    ("hotel",       "boutique hotel",             "Berlin"),
    ("hotel",       "luxury hotel",               "Singapore"),
    ("hotel",       "boutique hotel",             "Toronto"),
    ("hotel",       "resort hotel",               "Bali"),
    ("hotel",       "budget hotel",               "Delhi"),
    ("hotel",       "boutique hotel",             "Barcelona"),
    ("hotel",       "boutique hotel",             "Prague"),
    ("hotel",       "boutique hotel",             "Vienna"),
    # ── Restaurants ─────────────────────────────────────────
    ("restaurant",  "restaurant chain",           "London"),
    ("restaurant",  "fine dining restaurant",     "Dubai"),
    ("restaurant",  "restaurant",                 "Amsterdam"),
    ("restaurant",  "restaurant group",           "New York"),
    ("restaurant",  "restaurant chain",           "Toronto"),
    ("restaurant",  "restaurant",                 "Sydney"),
    ("restaurant",  "fine dining restaurant",     "Paris"),
    ("restaurant",  "restaurant",                 "Singapore"),
    # ── Schools / Colleges ───────────────────────────────────
    ("school",      "private school",             "Amsterdam"),
    ("school",      "private school",             "Dubai"),
    ("school",      "international school",       "Singapore"),
    ("school",      "international school",       "London"),
    ("school",      "private school",             "Toronto"),
    ("school",      "private school",             "Noida"),
    ("school",      "private school",             "Delhi"),
    ("college",     "private college",            "Mumbai"),
    ("college",     "engineering college",        "Noida"),
    ("college",     "management college",         "Delhi"),
    ("college",     "private college",            "Bangalore"),
    ("college",     "private college",            "London"),
    ("college",     "business school",            "Dubai"),
    # ── Retail / Shops ──────────────────────────────────────
    ("shop",        "retail chain store",         "Delhi"),
    ("shop",        "supermarket chain",          "UK"),
    ("shop",        "fashion retail store",       "London"),
    ("shop",        "electronics retailer",       "Dubai"),
    ("shop",        "pharmacy chain",             "Amsterdam"),
    ("shop",        "clothing store chain",       "Toronto"),
    ("shop",        "furniture store",            "Berlin"),
    ("shop",        "supermarket",                "Singapore"),
    # ── Real Estate ──────────────────────────────────────────
    ("real_estate", "real estate agency",         "Dubai"),
    ("real_estate", "property management",        "London"),
    ("real_estate", "real estate agency",         "Amsterdam"),
    ("real_estate", "property management",        "Toronto"),
    ("real_estate", "real estate agency",         "Noida"),
    ("real_estate", "real estate agency",         "Mumbai"),
    ("real_estate", "real estate agency",         "Singapore"),
    ("real_estate", "real estate agency",         "Sydney"),
    ("real_estate", "property developer",         "Dubai"),
    ("real_estate", "property developer",         "London"),
    # ── Gyms / Fitness ──────────────────────────────────────
    ("gym",         "gym fitness center",         "Amsterdam"),
    ("gym",         "gym fitness center",         "Dubai"),
    ("gym",         "gym fitness center",         "London"),
    ("gym",         "fitness club",               "Toronto"),
    ("gym",         "fitness center",             "Singapore"),
    ("gym",         "gym",                        "Noida"),
    # ── Manufacturing / Factories ────────────────────────────
    ("factory",     "manufacturing company",      "Germany"),
    ("factory",     "manufacturing company",      "UK"),
    ("factory",     "manufacturing company",      "Noida"),
    ("factory",     "industrial company",         "Delhi"),
    ("factory",     "manufacturing company",      "Singapore"),
    # ── Extra niches ────────────────────────────────────────
    ("hospital",    "diagnostic center",          "Delhi"),
    ("clinic",      "veterinary clinic",          "London"),
    ("clinic",      "aesthetic clinic",           "Dubai"),
    ("hotel",       "service apartment",          "Singapore"),
    ("real_estate", "commercial property",        "Dubai"),
    ("school",      "coaching institute",         "Noida"),
    ("college",     "law college",                "Mumbai"),
    ("gym",         "yoga studio",                "Amsterdam"),
    ("restaurant",  "cafe chain",                 "London"),
    ("shop",        "jewelry store",              "Dubai"),
]

# Google Maps searches — rotated each round for variety
MAPS_SEARCHES_POOL = [
    "hospitals near Amsterdam", "private clinics Dubai", "hotels London",
    "schools Amsterdam", "real estate agencies Dubai", "gyms Amsterdam",
    "restaurants Berlin", "colleges Noida India", "hospitals Noida India",
    "private clinics London", "boutique hotels Paris", "restaurants Dubai",
    "dental clinics Toronto", "fitness centers Singapore", "hospitals Mumbai",
    "real estate agencies London", "private schools Singapore", "hotels Berlin",
    "hospitals Delhi India", "manufacturing companies Noida India",
    "restaurants Amsterdam", "gyms London", "hospitals Toronto",
    "private colleges Bangalore India", "real estate agencies Amsterdam",
    "boutique hotels Barcelona", "restaurants Singapore", "clinics Sydney",
    "hotels Prague", "hospitals Frankfurt Germany",
]

# biz_scraper tracks which offset it is at across rounds
_search_offset: int = 0
_maps_offset: int = 0

MAPS_SEARCHES = MAPS_SEARCHES_POOL[:10]  # backward compat for any direct import


def _get_chrome_major_version() -> int:
    """Detect the installed Chrome major version number."""
    import subprocess
    for cmd in ["google-chrome", "chromium", "chromium-browser"]:
        try:
            out = subprocess.check_output([cmd, "--version"], stderr=subprocess.DEVNULL).decode()
            match = re.search(r"(\d+)\.\d+\.\d+", out)
            if match:
                return int(match.group(1))
        except Exception:
            continue
    return 114  # safe fallback


def _make_driver() -> "uc.Chrome":
    """Launch undetected Chrome browser, pinned to the correct driver version."""
    from pathlib import Path
    # Delete stale chromedriver so uc downloads the right one
    uc_driver_path = Path.home() / ".local/share/undetected_chromedriver/undetected_chromedriver"
    if uc_driver_path.exists():
        try:
            uc_driver_path.unlink()
            logger.info(f"🗑️  Removed old chromedriver → will re-download correct version")
        except Exception:
            pass

    chrome_ver = _get_chrome_major_version()
    logger.info(f"🌐 Chrome version detected: {chrome_ver}")

    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1280,900")
    # Uncomment below to run headless (invisible browser):
    # options.add_argument("--headless=new")
    driver = uc.Chrome(options=options, version_main=chrome_ver)
    driver.set_page_load_timeout(30)
    return driver


def _human_pause(min_s: float = 1.0, max_s: float = 3.0):
    """Random pause to mimic human behaviour."""
    time.sleep(random.uniform(min_s, max_s))


def _scroll_page(driver, times: int = 3):
    """Scroll down slowly like a human."""
    for _ in range(times):
        driver.execute_script("window.scrollBy(0, window.innerHeight * 0.7);")
        _human_pause(0.8, 1.5)


# ─────────────────────────────────────────────────────────────
#  SOURCE 1: Google Search (multi-page)
# ─────────────────────────────────────────────────────────────
def _scrape_google_search(driver, keyword: str, city: str, category: str, max_pages: int = 4) -> List[Dict]:
    """Search Google for businesses across multiple pages."""
    query = f"{keyword} {city} official website"
    leads = []
    seen_urls: set = set()

    for page in range(max_pages):
        start = page * 10
        url = f"https://www.google.com/search?q={query.replace(' ', '+')}&num=10&start={start}"
        try:
            driver.get(url)
            _human_pause(2, 4)

            # Accept cookies if prompted (only first page)
            if page == 0:
                try:
                    btn = driver.find_element(By.XPATH, "//button[contains(., 'Accept') or contains(., 'Agree')]")
                    btn.click()
                    _human_pause(1, 2)
                except NoSuchElementException:
                    pass

            _scroll_page(driver, 2)

            # Detect CAPTCHA — stop if Google blocked us
            if "captcha" in driver.current_url.lower() or "sorry/index" in driver.current_url:
                logger.warning(f"⚠️  Google CAPTCHA on page {page+1} — stopping early")
                break

            # Grab organic result cards
            results = driver.find_elements(By.CSS_SELECTOR, "div.g, div[data-sokoban-container]")
            if not results:
                results = driver.find_elements(By.CSS_SELECTOR, "div.tF2Cxc, div.yuRUbf")

            page_count = 0
            for result in results[:10]:
                try:
                    title_el = result.find_element(By.CSS_SELECTOR, "h3")
                    title = title_el.text.strip()
                    if not title:
                        continue

                    link_el = result.find_element(By.CSS_SELECTOR, "a")
                    href = link_el.get_attribute("href") or ""
                    if not href.startswith("http"):
                        continue
                    if "google.com" in href or "youtube.com" in href:
                        continue
                    if href in seen_urls:
                        continue
                    seen_urls.add(href)

                    snippet = ""
                    try:
                        snippet_el = result.find_element(By.CSS_SELECTOR, "div.VwiC3b, span.aCOpRe")
                        snippet = snippet_el.text.strip()
                    except NoSuchElementException:
                        pass

                    leads.append({
                        "name": title,
                        "website": href,
                        "category": category,
                        "city": city,
                        "source": f"google_p{page+1}",
                        "snippet": snippet[:200],
                        "email": None,
                        "phone": None,
                        "contact_name": None,
                        "status": "found",
                    })
                    page_count += 1
                    logger.debug(f"  p{page+1}: {title} → {href[:55]}")

                except Exception:
                    continue

            logger.info(f"🔍 Google p{page+1} '{keyword} {city}' → {page_count} leads")

            # No results on this page — no point going deeper
            if page_count == 0:
                break

            _human_pause(2, 4)  # pause between pages

        except WebDriverException as e:
            logger.error(f"Google search page {page+1} failed: {e}")
            break

    return leads


# ─────────────────────────────────────────────────────────────
#  SOURCE 2: Google Maps
# ─────────────────────────────────────────────────────────────
def _scrape_google_maps(driver, search_query: str) -> List[Dict]:
    """Search Google Maps and extract business listings."""
    url = f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}"
    leads = []

    try:
        driver.get(url)
        _human_pause(3, 5)

        # Scroll the sidebar to load more results
        for _ in range(4):
            try:
                sidebar = driver.find_element(
                    By.CSS_SELECTOR, "div[role='feed'], div.m6QErb"
                )
                driver.execute_script("arguments[0].scrollTop += 800;", sidebar)
                _human_pause(1.5, 2.5)
            except NoSuchElementException:
                _scroll_page(driver, 2)
                break

        # Grab all business cards
        cards = driver.find_elements(
            By.CSS_SELECTOR,
            "a.hfpxzc, div.Nv2PK, [jsaction*='mouseover:pane']"
        )

        # Deduplicate by iterating the feed links
        feed_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/maps/place/']")

        processed_names = set()
        for link in feed_links[:20]:
            try:
                name = link.get_attribute("aria-label") or ""
                href = link.get_attribute("href") or ""
                if not name or name in processed_names:
                    continue
                processed_names.add(name)

                # Click to open the panel and get website
                driver.execute_script("arguments[0].click();", link)
                _human_pause(1.5, 3)

                website = ""
                phone = ""
                try:
                    # Website link in the sidebar panel
                    web_el = driver.find_element(
                        By.CSS_SELECTOR,
                        "a[data-item-id='authority'], a[aria-label*='website' i], a[href^='http']:not([href*='google'])"
                    )
                    website = web_el.get_attribute("href") or ""
                    if "google.com" in website or "maps.google" in website:
                        website = ""
                except NoSuchElementException:
                    pass

                try:
                    phone_el = driver.find_element(
                        By.CSS_SELECTOR,
                        "[data-item-id*='phone'], [aria-label*='phone' i]"
                    )
                    phone = phone_el.get_attribute("aria-label") or phone_el.text
                    phone = phone.replace("Phone:", "").strip()
                except NoSuchElementException:
                    pass

                # Detect category from search query
                category = "business"
                for cat in ["hospital", "clinic", "hotel", "restaurant", "school",
                            "college", "shop", "real_estate", "gym", "factory"]:
                    if cat in search_query.lower():
                        category = cat
                        break

                # Extract city from search query
                city_match = re.search(r"(?:in|near)\s+(.+)", search_query, re.I)
                city = city_match.group(1).strip() if city_match else search_query

                leads.append({
                    "name": name,
                    "website": website,
                    "category": category,
                    "city": city,
                    "source": "google_maps",
                    "snippet": "",
                    "email": None,
                    "phone": phone,
                    "contact_name": None,
                    "status": "found",
                })
                logger.debug(f"  Maps: {name} | website: {website[:50] if website else 'none'}")

            except Exception as e:
                logger.debug(f"Maps card error: {e}")
                continue

        logger.info(f"🗺️  Google Maps '{search_query}' → {len(leads)} leads")

    except WebDriverException as e:
        logger.error(f"Google Maps scrape failed: {e}")

    return leads


# ─────────────────────────────────────────────────────────────
#  SOURCE 3: JustDial (India)
# ─────────────────────────────────────────────────────────────
def _scrape_justdial(driver, keyword: str, city: str, category: str) -> List[Dict]:
    """Scrape JustDial for Indian businesses."""
    city_slug = city.lower().replace(" ", "-")
    kw_slug = keyword.lower().replace(" ", "-")
    url = f"https://www.justdial.com/{city_slug}/{kw_slug}"
    leads = []

    try:
        driver.get(url)
        _human_pause(3, 5)
        _scroll_page(driver, 3)

        cards = driver.find_elements(By.CSS_SELECTOR, "li.cntanr, div.resultbox_info")
        for card in cards[:10]:
            try:
                name = card.find_element(By.CSS_SELECTOR, "span.lng_no_display, h2.jcn").text.strip()
                if not name:
                    continue
                phone = ""
                try:
                    phone = card.find_element(By.CSS_SELECTOR, "span.mobilesv, p.contact-info").text.strip()
                except NoSuchElementException:
                    pass

                leads.append({
                    "name": name,
                    "website": "",
                    "category": category,
                    "city": city,
                    "source": "justdial",
                    "snippet": "",
                    "email": None,
                    "phone": phone,
                    "contact_name": None,
                    "status": "found",
                })
            except Exception:
                continue

        logger.info(f"📋 JustDial '{keyword} {city}' → {len(leads)} leads")

    except Exception as e:
        logger.warning(f"JustDial scrape skipped: {e}")

    return leads


# ─────────────────────────────────────────────────────────────
#  MAIN: Run all scrapers
# ─────────────────────────────────────────────────────────────
def scrape_businesses(
    max_google_searches: int = 10,
    max_maps_searches: int = 5,
    include_india: bool = True,
    round_offset: int = 0,          # rotate keyword slice each round
) -> List[Dict]:
    """
    Launch Chrome, scrape Google + Google Maps + JustDial.
    round_offset rotates through SEARCH_TARGETS so each round finds new businesses.
    """
    if not SELENIUM_OK:
        logger.error("Selenium not installed. Run: pip install undetected-chromedriver selenium")
        return []

    all_leads: List[Dict] = []
    seen_names: set = set()

    # ── Rotate which slice of targets to use ─────────────────
    n = len(SEARCH_TARGETS)
    start_idx = (round_offset * max_google_searches) % n
    rotated = SEARCH_TARGETS[start_idx:] + SEARCH_TARGETS[:start_idx]
    targets_this_round = rotated[:max_google_searches]

    maps_n = len(MAPS_SEARCHES_POOL)
    maps_start = (round_offset * max_maps_searches) % maps_n
    maps_rotated = MAPS_SEARCHES_POOL[maps_start:] + MAPS_SEARCHES_POOL[:maps_start]
    maps_this_round = maps_rotated[:max_maps_searches]

    driver = None
    try:
        logger.info("🚀 Launching Chrome browser...")
        driver = _make_driver()

        # ── 1. Google Search ──────────────────────────────────
        for category, keyword, city in targets_this_round:
            leads = _scrape_google_search(driver, keyword, city, category, max_pages=4)
            for lead in leads:
                key = lead["name"].lower()
                if key not in seen_names:
                    seen_names.add(key)
                    all_leads.append(lead)
            _human_pause(2, 4)

        # ── 2. Google Maps ────────────────────────────────────
        for maps_query in maps_this_round:
            leads = _scrape_google_maps(driver, maps_query)
            for lead in leads:
                key = lead["name"].lower()
                if key not in seen_names:
                    seen_names.add(key)
                    all_leads.append(lead)
            _human_pause(3, 5)

        # ── 3. JustDial (India) ───────────────────────────────
        if include_india:
            india_targets = [
                ("hospital", "multispecialty hospital", "Noida"),
                ("college",  "engineering college",     "Noida"),
                ("hospital", "private hospital",        "Delhi"),
            ]
            for category, keyword, city in india_targets:
                leads = _scrape_justdial(driver, keyword, city, category)
                for lead in leads:
                    key = lead["name"].lower()
                    if key not in seen_names:
                        seen_names.add(key)
                        all_leads.append(lead)
                _human_pause(2, 4)

    except Exception as e:
        logger.error(f"Scraper crashed: {e}", exc_info=True)
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    logger.info(f"✅ Scraping done. Total businesses found: {len(all_leads)}")
    return all_leads


# ─────────────────────────────────────────────────────────────
#  QUICK TEST
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = scrape_businesses(max_google_searches=2, max_maps_searches=1, include_india=False)
    print(f"\nTotal leads scraped: {len(results)}")
    for r in results[:5]:
        print(f"  • {r['name']} | {r['category']} | {r['city']} | {r['website'][:50] if r['website'] else 'no website'}")
