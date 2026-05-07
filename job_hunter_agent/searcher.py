"""
job_hunter_agent/searcher.py
============================
Searches for jobs and freelance clients across:
  - Upwork (via Google search)
  - LinkedIn Jobs (via SerpAPI)
  - Remotive.io (remote jobs API - free)
  - We Work Remotely (scrape)
  - Google Maps (local businesses to pitch to)
  - Freelancer.com (via Google search)
  - AngelList / Wellfound (startups)
"""

import os
import json
import time
import logging
import warnings
import requests
from pathlib import Path
from typing import List, Dict
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from serpapi import GoogleSearch
from dotenv import load_dotenv

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)
logger = logging.getLogger(__name__)

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


# ─────────────────────────────────────────────
#  HELPER: Google search via SerpAPI
# ─────────────────────────────────────────────
def _google_search(query: str, num: int = 10) -> List[Dict]:
    """Run a Google search and return organic results."""
    try:
        params = {
            "engine": "google",
            "q": query,
            "num": num,
            "api_key": SERPAPI_KEY,
        }
        results = GoogleSearch(params).get_dict()
        # Surface API-level errors (quota exceeded, invalid key, etc.)
        if "error" in results:
            logger.error(f"SerpAPI error: {results['error']}")
            return []
        organic = results.get("organic_results", [])
        logger.debug(f"Google search '{query[:60]}' → {len(organic)} results")
        return [
            {
                "title": r.get("title", ""),
                "link": r.get("link", ""),
                "snippet": r.get("snippet", ""),
                "source": "google_search",
            }
            for r in organic
        ]
    except Exception as e:
        logger.error(f"Google search error: {e}")
        return []


# ─────────────────────────────────────────────
#  SOURCE 1: Upwork Jobs via Google
# ─────────────────────────────────────────────
def search_upwork(keywords: List[str]) -> List[Dict]:
    """Search Upwork jobs using Google (bypasses bot detection)."""
    leads = []
    # Use broader queries without strict quotes to avoid empty results
    priority_kws = [keywords[0], keywords[2], keywords[5], keywords[9]] if len(keywords) >= 10 else keywords[:4]
    for keyword in priority_kws:
        query = f'site:upwork.com/jobs {keyword} remote'
        results = _google_search(query, num=8)
        for r in results:
            if "upwork.com/jobs" in r.get("link", ""):
                leads.append({
                    "platform": "Upwork",
                    "title": r["title"],
                    "url": r["link"],
                    "description": r["snippet"],
                    "type": "job_post",
                })
        time.sleep(1)
    logger.info(f"Upwork: found {len(leads)} leads")
    return leads


# ─────────────────────────────────────────────
#  SOURCE 2: LinkedIn Jobs via SerpAPI
# ─────────────────────────────────────────────
def search_linkedin(keywords: List[str], locations: List[str]) -> List[Dict]:
    """Search LinkedIn jobs via Google site search (linkedin_jobs engine not on free plan)."""
    leads = []
    priority_kws = keywords[:4]
    for keyword in priority_kws:
        query = f'site:linkedin.com/jobs/view {keyword} remote'
        results = _google_search(query, num=8)
        for r in results:
            link = r.get("link", "")
            if "linkedin.com/jobs" in link:
                leads.append({
                    "platform": "LinkedIn",
                    "title": r["title"],
                    "company": "",
                    "location": "Remote",
                    "url": link,
                    "description": r["snippet"],
                    "type": "job_post",
                })
        time.sleep(1)
    logger.info(f"LinkedIn: found {len(leads)} leads")
    return leads


# ─────────────────────────────────────────────
#  SOURCE 3: Remotive.io (FREE Remote Jobs API)
# ─────────────────────────────────────────────
def search_remotive(keywords: List[str]) -> List[Dict]:
    """Fetch remote jobs from Remotive public API (no key needed)."""
    leads = []
    try:
        url = "https://remotive.com/api/remote-jobs"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        all_jobs = resp.json().get("jobs", [])

        for job in all_jobs:
            tags = job.get("tags", [])
            tags_str = " ".join(tags) if isinstance(tags, list) else str(tags)
            job_text = (
                job.get("title", "") + " " +
                job.get("description", "") + " " +
                tags_str
            )
            job_text_lower = job_text.lower() if isinstance(job_text, str) else ""
            # match any keyword
            for kw in keywords:
                if kw.lower().split()[0] in job_text_lower:
                    leads.append({
                        "platform": "Remotive",
                        "title": job.get("title", ""),
                        "company": job.get("company_name", ""),
                        "url": job.get("url", ""),
                        "salary": job.get("salary", "Not specified"),
                        "description": BeautifulSoup(
                            job.get("description", ""), "html.parser"
                        ).get_text()[:500],
                        "type": "job_post",
                    })
                    break

    except Exception as e:
        logger.error(f"Remotive error: {e}")

    logger.info(f"Remotive: found {len(leads)} leads")
    return leads[:15]


# ─────────────────────────────────────────────
#  SOURCE 4: We Work Remotely (scrape)
# ─────────────────────────────────────────────
def search_weworkremotely(keywords: List[str]) -> List[Dict]:
    """Fetch We Work Remotely jobs via RSS feed (more reliable than scraping)."""
    leads = []
    rss_feeds = [
        "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-front-end-programming-jobs.rss",
    ]
    seen = set()
    for feed_url in rss_feeds:
        try:
            resp = requests.get(feed_url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(resp.text, "xml")
            items = soup.find_all("item")
            for item in items[:25]:
                title = item.find("title")
                link = item.find("link")
                desc = item.find("description")
                region = item.find("region")
                if not title:
                    continue
                title_text = title.get_text(strip=True)
                link_text = link.get_text(strip=True) if link else ""
                desc_text = BeautifulSoup(
                    desc.get_text(strip=True) if desc else "", "html.parser"
                ).get_text()[:400]
                if link_text in seen:
                    continue
                seen.add(link_text)
                leads.append({
                    "platform": "WeWorkRemotely",
                    "title": title_text,
                    "company": "",
                    "url": link_text,
                    "description": desc_text,
                    "location": region.get_text(strip=True) if region else "Remote",
                    "type": "job_post",
                })
        except Exception as e:
            logger.error(f"WeWorkRemotely RSS error ({feed_url}): {e}")
    logger.info(f"WeWorkRemotely: found {len(leads)} leads")
    return leads[:15]


# ─────────────────────────────────────────────
#  SOURCE 5: Google Maps — Local Business Leads
# ─────────────────────────────────────────────
def search_google_maps(skills: List[str], locations: List[str]) -> List[Dict]:
    """
    Search Google Maps for local businesses that likely need software.
    These become OUTBOUND PITCHING leads (you approach them).
    """
    leads = []
    pitch_queries = [
        f"software company {loc}" for loc in locations[:3]
    ] + [
        f"startup company {loc}" for loc in locations[:2]
    ] + [
        "company needs CRM software",
        "business needs ERP system",
        "small business software development",
    ]

    for query in pitch_queries[:5]:
        try:
            params = {
                "engine": "google_maps",
                "q": query,
                "api_key": SERPAPI_KEY,
            }
            results = GoogleSearch(params).get_dict()
            places = results.get("local_results", [])
            for place in places[:4]:
                website = place.get("website", "")
                leads.append({
                    "platform": "Google Maps",
                    "title": f"Potential client: {place.get('title', '')}",
                    "company": place.get("title", ""),
                    "location": place.get("address", ""),
                    "website": website,
                    "phone": place.get("phone", ""),
                    "rating": place.get("rating", ""),
                    "description": place.get("description", "Business found on Google Maps"),
                    "type": "outbound_lead",
                    "url": place.get("website", place.get("place_id", "")),
                })
            time.sleep(1)
        except Exception as e:
            logger.error(f"Google Maps error: {e}")

    logger.info(f"Google Maps: found {len(leads)} leads")
    return leads


# ─────────────────────────────────────────────
#  SOURCE 6: Freelancer.com via Google
# ─────────────────────────────────────────────
def search_freelancer(keywords: List[str]) -> List[Dict]:
    """Search Freelancer.com projects via Google."""
    leads = []
    priority_kws = [keywords[0], keywords[2], keywords[6]] if len(keywords) >= 7 else keywords[:3]
    for keyword in priority_kws:
        query = f'site:freelancer.com/projects {keyword}'
        results = _google_search(query, num=8)
        for r in results:
            if "freelancer.com/projects" in r.get("link", ""):
                leads.append({
                    "platform": "Freelancer.com",
                    "title": r["title"],
                    "url": r["link"],
                    "description": r["snippet"],
                    "type": "job_post",
                })
        time.sleep(1)
    logger.info(f"Freelancer.com: found {len(leads)} leads")
    return leads


# ─────────────────────────────────────────────
#  SOURCE 7: Wellfound / AngelList (Startups)
# ─────────────────────────────────────────────
def search_wellfound(keywords: List[str]) -> List[Dict]:
    """Search Wellfound (formerly AngelList) startup jobs via Google."""
    leads = []
    for keyword in keywords[:3]:
        query = f'site:wellfound.com/jobs {keyword} remote'
        results = _google_search(query, num=5)
        for r in results:
            if "wellfound.com" in r.get("link", ""):
                leads.append({
                    "platform": "Wellfound (AngelList)",
                    "title": r["title"],
                    "url": r["link"],
                    "description": r["snippet"],
                    "type": "job_post",
                })
        time.sleep(1)
    logger.info(f"Wellfound: found {len(leads)} leads")
    return leads


# ─────────────────────────────────────────────
#  MASTER SEARCH — runs all sources
# ─────────────────────────────────────────────
def run_full_search(profile: Dict) -> List[Dict]:
    """
    Run all search sources and return a combined list of leads.
    Each lead dict has: platform, title, company, url, description, type
    """
    keywords = profile.get("search_keywords", [])
    skills = profile.get("skills", [])
    locations = profile.get("locations_to_target", ["Worldwide"])

    logger.info("=" * 50)
    logger.info("🔍 Starting worldwide job & client hunt...")
    logger.info("=" * 50)

    all_leads = []

    # --- Run each source ---
    all_leads += search_remotive(keywords)          # Free, no key needed
    all_leads += search_weworkremotely(keywords)    # Free scrape
    all_leads += search_upwork(keywords)            # SerpAPI
    all_leads += search_linkedin(keywords, locations)  # SerpAPI
    all_leads += search_freelancer(keywords)        # SerpAPI
    all_leads += search_wellfound(keywords)         # SerpAPI
    all_leads += search_google_maps(skills, locations)  # SerpAPI (outbound)

    # Deduplicate by URL
    seen_urls = set()
    unique_leads = []
    for lead in all_leads:
        url = lead.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_leads.append(lead)

    logger.info(f"\n✅ Total unique leads found: {len(unique_leads)}")
    return unique_leads
