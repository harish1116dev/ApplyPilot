"""
Internshala job scraper — httpx + BeautifulSoup.

Internshala is India's largest fresher/entry-level jobs platform.
Unlike Naukri (which blocks all scrapers), Internshala serves
full job data in SSR HTML — no JavaScript execution needed.

Naukri is replaced by this scraper because:
- Naukri Playwright scraper: blocked by Akamai bot protection (403)
- Naukri JSON API: requires reCAPTCHA (406)
- Naukri HTML: pure client-side React, no data in HTML

Ctrl+C safe: checks is_shutdown() before each role/city iteration.
"""
import httpx
import re
from bs4 import BeautifulSoup
from utils.helpers import random_delay, random_user_agent
from utils.logger import setup_logger
from utils.shutdown import is_shutdown

logger = setup_logger("naukri_scraper")   # keep logger name for compatibility

_BASE = "https://internshala.com"

_CITY_MAP = {
    "chennai":    "chennai",
    "bengaluru":  "bangalore",
    "bangalore":  "bangalore",
    "coimbatore": "coimbatore",
    "hyderabad":  "hyderabad",
    "pune":       "pune",
    "mumbai":     "mumbai",
    "remote":     None,
}


def _get_headers() -> dict:
    return {
        "User-Agent": random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
    }


def _role_to_slug(role: str) -> str:
    """Convert role name to Internshala URL slug."""
    slug = role.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = slug.replace(" ", "-")
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def _fetch_jobs(role: str, city: str, max_jobs: int) -> list[dict]:
    """Fetch jobs from Internshala job listing page."""
    role_slug = _role_to_slug(role)
    city_slug = _CITY_MAP.get(city.lower().strip(), city.lower().replace(" ", "-"))

    if city_slug:
        url = f"{_BASE}/jobs/{role_slug}-jobs-in-{city_slug}"
    else:
        url = f"{_BASE}/jobs/{role_slug}-jobs"

    jobs = []
    try:
        resp = httpx.get(url, headers=_get_headers(), timeout=20, follow_redirects=True)

        if resp.status_code == 404:
            # Try without city
            url = f"{_BASE}/jobs/{role_slug}-jobs"
            resp = httpx.get(url, headers=_get_headers(), timeout=15, follow_redirects=True)

        if resp.status_code != 200:
            logger.debug(f"Internshala {resp.status_code} for '{role}' in {city}")
            return []

        html = resp.text
        if len(html) < 3000:
            return []

        soup = BeautifulSoup(html, "lxml")

        # Internshala job cards (verified 2026-06-26 from live HTML)
        # The real parent is: div.container-fluid.individual_internship
        cards = soup.select("div.container-fluid.individual_internship")
        if not cards:
            # Fallback
            cards = soup.select("div[class*='individual_internship'][employment_type='job']")
        if not cards:
            cards = soup.select("div[internshipid]")

        for card in cards[:max_jobs]:
            try:
                # Title: h2.job-internship-name > a.job-title-href
                title_el = (
                    card.select_one("a.job-title-href")
                    or card.select_one(".job-internship-name a")
                    or card.select_one("a[href*='/job/detail']")
                )
                # Company: p.company-name
                company_el = (
                    card.select_one("p.company-name")
                    or card.select_one("[class*='company_name'] p")
                    or card.select_one("[class*='company']")
                )
                # Location: p.locations span a
                loc_el = (
                    card.select_one("p.locations span a")
                    or card.select_one("p.row-1-item.locations span")
                    or card.select_one("[class*='location']")
                )
                # Salary: div.row-1-item span.desktop (the one with ic-16-money)
                sal_el = (
                    card.select_one("div.row-1-item span.desktop")
                    or card.select_one("span[class*='salary']")
                    or card.select_one("[class*='stipend']")
                )
                # Experience: span after ic-16-briefcase icon
                exp_el = card.select_one("i.ic-16-briefcase")
                if exp_el:
                    exp_el = exp_el.find_next_sibling("span") or exp_el.parent.find("span")
                if not exp_el:
                    exp_el = card.select_one("[class*='experience'] span")

                title = title_el.get_text(strip=True) if title_el else ""
                if not title or len(title) < 3:
                    continue

                company = company_el.get_text(strip=True) if company_el else "Unknown"
                location = loc_el.get_text(strip=True) if loc_el else city
                sal_text = sal_el.get_text(strip=True) if sal_el else ""
                exp_text = exp_el.get_text(strip=True) if exp_el else "0-2 years"

                href = title_el.get("href", "") if title_el else ""
                apply_url = f"{_BASE}{href}" if href and href.startswith("/") else href or url

                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "salary_text": sal_text,
                    "experience_text": exp_text,
                    "apply_url": apply_url,
                    "platform": "internshala",
                    "raw_jd": card.select_one(".about_job .text").get_text(strip=True)[:1500]
                             if card.select_one(".about_job .text") else "",
                })
            except Exception as e:
                logger.debug(f"Internshala card parse error: {e}")
                continue

    except Exception as e:
        logger.warning(f"Internshala error for '{role}' in {city}: {e}")

    return jobs


def scrape(profile: dict, settings: dict) -> list[dict]:
    cities = profile["target"]["preferred_cities"][:3]
    roles = profile["target"]["roles"]   # all roles — no cap
    max_jobs = settings["scraping"]["max_jobs_per_source"]
    jobs = []
    seen: set[str] = set()

    for role in roles:
        if is_shutdown():
            break

        for city in cities[:2]:   # max 2 cities per role
            if is_shutdown():
                break

            logger.info(f"Naukri: scraping '{role}' in {city}")
            batch = _fetch_jobs(role, city, max_jobs)

            for j in batch:
                key = f"{j['title'].lower().strip()}|{j['company'].lower().strip()}"
                if key not in seen:
                    seen.add(key)
                    jobs.append(j)

            logger.info(f"Naukri: {len(batch)} jobs for '{role}' in {city} (unique total: {len(jobs)})")
            random_delay(1, 2)

        if len(jobs) >= max_jobs:
            break

    logger.info(f"Naukri: total {len(jobs)} jobs found")
    return jobs
