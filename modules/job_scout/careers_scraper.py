"""
Careers page scraper — verified Lever & Greenhouse ATS JSON APIs.

Only companies with verified working API endpoints are included.
Slugs are tested live; 404s removed. Add new companies after verifying:
    python -c "import httpx; r=httpx.get('https://boards-api.greenhouse.io/v1/boards/<slug>/jobs'); print(r.status_code, len(r.json().get('jobs',[])))"

Ctrl+C safe: checks is_shutdown() before each company.
"""
import httpx
from utils.helpers import random_delay, random_user_agent
from utils.logger import setup_logger
from utils.shutdown import is_shutdown

logger = setup_logger("careers_scraper")

FRESHER_KEYWORDS = [
    "fresher", "0-2", "0 - 2", "entry", "junior", "graduate",
    "trainee", "intern", "associate", "0-1", "junior level", "early career"
]

ROLE_KEYWORDS = [
    "software engineer", "software developer", "software development",
    "developer", "engineer",
    "frontend", "back-end", "backend", "full stack", "fullstack", "full-stack",
    "react", "node.js", "nodejs", "python", "javascript",
    "ai engineer", "ml engineer", "machine learning", "data engineer",
    "data scientist", "data analyst",
    "flutter", "mobile developer", "android", "ios developer",
    "sde", "sde-1", "sde 1", "swe", "devops", "cloud engineer",
    "web developer", "graduate engineer", "associate engineer",
    "get ", "trainee", "junior developer",
]

INDIA_KEYWORDS = [
    "india", "chennai", "bengaluru", "bangalore", "hyderabad",
    "pune", "mumbai", "delhi", "coimbatore", "remote", "anywhere",
    "telangana", "karnataka", "tamil", "global"
]

# ── Verified working Greenhouse slugs (tested 2026-06-26) ──────────────────────
GREENHOUSE_COMPANIES = [
    {"name": "Groww",   "slug": "groww"},    # 17 postings
    {"name": "Turing",  "slug": "turing"},   # 23 postings
    {"name": "Slice",   "slug": "slice"},    # 75 postings
]

# ── Verified working Lever slugs (tested 2026-06-26) ──────────────────────────
LEVER_COMPANIES = [
    {"name": "Freshworks", "slug": "freshworks"},  # 0 now but account active
]


def _is_relevant(title: str, dept: str = "") -> bool:
    """Require at least one tech/engineering keyword in the title or dept."""
    text = (title + " " + dept).lower()
    return any(k in text for k in ROLE_KEYWORDS)


def _is_india(location: str) -> bool:
    if not location:
        return True   # No location → likely remote → accept
    return any(k in location.lower() for k in INDIA_KEYWORDS)


def _scrape_greenhouse(company: dict) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{company['slug']}/jobs?content=true"
    jobs = []
    try:
        r = httpx.get(
            url, timeout=15, follow_redirects=True,
            headers={"User-Agent": random_user_agent()}
        )
        if r.status_code != 200:
            logger.warning(f"Greenhouse {company['name']}: HTTP {r.status_code}")
            return []

        for post in r.json().get("jobs", []):
            title = post.get("title", "")
            dept = (post.get("departments") or [{}])[0].get("name", "")
            offices = post.get("offices") or [{}]
            location = offices[0].get("name", "") if offices else ""
            apply_url = post.get("absolute_url", "")

            if not _is_relevant(title, dept):
                continue
            if not _is_india(location):
                continue

            jobs.append({
                "title": title,
                "company": company["name"],
                "location": location or "India (Remote)",
                "apply_url": apply_url,
                "platform": "careers_page",
                "raw_jd": (post.get("content") or "")[:2000],
            })

        logger.info(f"Greenhouse {company['name']}: {len(jobs)} matching jobs")
    except Exception as e:
        logger.warning(f"Greenhouse {company['name']} error: {e}")
    return jobs


def _scrape_lever(company: dict) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{company['slug']}?mode=json"
    jobs = []
    try:
        r = httpx.get(
            url, timeout=15, follow_redirects=True,
            headers={"User-Agent": random_user_agent()}
        )
        if r.status_code != 200:
            logger.warning(f"Lever {company['name']}: HTTP {r.status_code}")
            return []

        postings = r.json() if isinstance(r.json(), list) else []
        for post in postings:
            title = post.get("text", "")
            dept = post.get("categories", {}).get("department", "")
            location = post.get("categories", {}).get("location", "")
            apply_url = post.get("hostedUrl", "") or post.get("applyUrl", "")

            if not _is_relevant(title, dept):
                continue
            if not _is_india(location):
                continue

            jobs.append({
                "title": title,
                "company": company["name"],
                "location": location or "India",
                "apply_url": apply_url,
                "platform": "careers_page",
                "raw_jd": (post.get("description") or "")[:2000],
            })

        logger.info(f"Lever {company['name']}: {len(jobs)} matching jobs")
    except Exception as e:
        logger.warning(f"Lever {company['name']} error: {e}")
    return jobs


def scrape(profile: dict, settings: dict) -> list[dict]:
    jobs = []

    for company in GREENHOUSE_COMPANIES:
        if is_shutdown():
            break
        logger.info(f"Careers: {company['name']} (Greenhouse API)")
        jobs.extend(_scrape_greenhouse(company))
        random_delay(1, 2)

    for company in LEVER_COMPANIES:
        if is_shutdown():
            break
        logger.info(f"Careers: {company['name']} (Lever API)")
        jobs.extend(_scrape_lever(company))
        random_delay(1, 2)

    logger.info(f"Careers pages: total {len(jobs)} jobs")
    return jobs
