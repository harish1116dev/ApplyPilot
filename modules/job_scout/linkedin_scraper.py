"""
LinkedIn job scraper — public jobs-guest JSON API with text-based location.

Text location (e.g. "Chennai, India") is more reliable than geoId
since geoIds change and are hard to verify without a browser session.
Ctrl+C safe: checks is_shutdown() throughout.
"""
import httpx
from bs4 import BeautifulSoup
from utils.logger import setup_logger
from utils.helpers import random_delay, random_user_agent
from utils.shutdown import is_shutdown

logger = setup_logger("linkedin_scraper")

# Map profile city names → LinkedIn location text (verified to return India results)
CITY_LOCATION_MAP = {
    "chennai":    "Chennai, Tamil Nadu, India",
    "bengaluru":  "Bengaluru, Karnataka, India",
    "hyderabad":  "Hyderabad, Telangana, India",
    "coimbatore": "Coimbatore, Tamil Nadu, India",
    "pune":       "Pune, Maharashtra, India",
    "mumbai":     "Mumbai, Maharashtra, India",
    "delhi":      "Delhi, India",
    "remote":     "India",
}

# India state/city keywords for result validation
INDIA_KEYWORDS = [
    "india", "chennai", "bengaluru", "bangalore", "hyderabad",
    "pune", "mumbai", "delhi", "coimbatore", "telangana", "karnataka",
    "tamil nadu", "maharashtra", "remote", "anywhere",
]


def _city_to_location(city: str) -> str:
    return CITY_LOCATION_MAP.get(city.lower().strip(), f"{city}, India")


def _is_india_location(location_text: str) -> bool:
    """Return True if result location is in India or Remote."""
    if not location_text:
        return True  # No location = probably remote, accept it
    loc = location_text.lower()
    return any(k in loc for k in INDIA_KEYWORDS)


def _fetch_jobs(role: str, city: str, max_jobs: int) -> list[dict]:
    """Fetch jobs using LinkedIn's public jobs-guest API with text location."""
    location_str = _city_to_location(city)
    encoded_role = role.replace(" ", "%20")
    encoded_loc = location_str.replace(" ", "%20").replace(",", "%2C")
    jobs = []
    start = 0

    while len(jobs) < max_jobs:
        if is_shutdown():
            break

        url = (
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
            f"?keywords={encoded_role}"
            f"&location={encoded_loc}"
            f"&f_JT=F"          # Full-time only
            f"&f_TPR=r5184000"  # Posted in last 60 days
            f"&start={start}"
        )

        try:
            with httpx.Client(
                headers={
                    "User-Agent": random_user_agent(),
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-IN,en;q=0.9",
                    "Referer": "https://www.linkedin.com/jobs/search/",
                },
                follow_redirects=True,
                timeout=20,
            ) as client:
                resp = client.get(url)

                if resp.status_code == 429:
                    logger.warning("LinkedIn rate limited — stopping")
                    break
                if resp.status_code != 200:
                    logger.debug(f"LinkedIn {resp.status_code} for '{role}'/'{city}'")
                    break

                soup = BeautifulSoup(resp.text, "lxml")
                cards = soup.select("li")

                if not cards:
                    break

                batch_count = 0
                for card in cards:
                    try:
                        title_el = card.select_one(
                            "h3.base-search-card__title, "
                            "h3[class*='title']"
                        )
                        company_el = card.select_one(
                            "h4.base-search-card__subtitle, "
                            "h4[class*='subtitle']"
                        )
                        loc_el = card.select_one(
                            "span.job-search-card__location, "
                            "span[class*='location']"
                        )
                        link_el = card.select_one(
                            "a.base-card__full-link, "
                            "a[href*='linkedin.com/jobs/view']"
                        )

                        title_text = title_el.get_text(strip=True) if title_el else ""
                        if not title_text or len(title_text) < 3:
                            continue

                        location_text = loc_el.get_text(strip=True) if loc_el else ""

                        # Skip results outside India
                        if not _is_india_location(location_text):
                            logger.debug(f"LinkedIn: skipping non-India result: {location_text}")
                            continue

                        href = link_el["href"].split("?")[0] if link_el else ""

                        jobs.append({
                            "title": title_text,
                            "company": company_el.get_text(strip=True) if company_el else "Unknown",
                            "location": location_text or city,
                            "apply_url": href or url,
                            "platform": "linkedin",
                            "raw_jd": "",
                        })
                        batch_count += 1

                    except Exception:
                        continue

                if batch_count == 0:
                    break  # Empty page — stop paginating

                start += 25
                if start >= 75:
                    break  # Max 3 pages

                random_delay(2, 3)

        except Exception as e:
            logger.warning(f"LinkedIn error for '{role}'/'{city}': {e}")
            break

    return jobs[:max_jobs]


def scrape(profile: dict, settings: dict) -> list[dict]:
    roles = profile["target"]["roles"]  # all roles — no cap
    cities = profile["target"]["preferred_cities"][:4]  # up to 4 cities
    max_jobs = settings["scraping"]["max_jobs_per_source"]
    jobs = []
    seen_urls: set[str] = set()
    seen_title_company: set[str] = set()

    for role in roles:
        if is_shutdown():
            break
        for city in cities:
            if is_shutdown():
                break

            logger.info(f"LinkedIn: scraping '{role}' in {city}")
            batch = _fetch_jobs(role, city, max_jobs)

            # URL-level + title+company deduplication
            for j in batch:
                url_key = j.get("apply_url", "")
                tc_key = f"{j.get('title','').lower().strip()}|{j.get('company','').lower().strip()}"
                if url_key and url_key not in seen_urls and tc_key not in seen_title_company:
                    seen_urls.add(url_key)
                    seen_title_company.add(tc_key)
                    jobs.append(j)

            logger.info(
                f"LinkedIn: {len(batch)} jobs for '{role}' in {city} "
                f"(unique total: {len(jobs)})"
            )
            random_delay(3, 5)

            if len(jobs) >= max_jobs:
                break

    logger.info(f"LinkedIn: total {len(jobs)} jobs found")
    return jobs
