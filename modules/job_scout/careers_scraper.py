"""Careers page scraper for target companies."""
import httpx
from bs4 import BeautifulSoup
from utils.helpers import random_delay, random_user_agent
from utils.logger import setup_logger

logger = setup_logger("careers_scraper")

TARGET_COMPANIES = [
    {"name": "Zoho", "url": "https://careers.zohocorp.com/", "selector": "a[href*='job']"},
    {"name": "Freshworks", "url": "https://www.freshworks.com/company/careers/", "selector": "a[href*='job']"},
    {"name": "Razorpay", "url": "https://razorpay.com/jobs/", "selector": "a[href*='job']"},
    {"name": "Chargebee", "url": "https://www.chargebee.com/careers/", "selector": "a[href*='job']"},
]

FRESHER_KEYWORDS = ["fresher", "fresher", "0-2", "entry", "junior", "graduate", "trainee"]


def scrape(profile: dict, settings: dict) -> list[dict]:
    target_titles = [r.lower() for r in profile["target"]["roles"]]
    jobs = []

    for company in TARGET_COMPANIES:
        logger.info(f"Careers: scraping {company['name']}")
        try:
            with httpx.Client(
                headers={"User-Agent": random_user_agent()},
                follow_redirects=True,
                timeout=20,
            ) as client:
                resp = client.get(company["url"])
                if resp.status_code != 200:
                    logger.warning(f"{company['name']} returned {resp.status_code}")
                    continue

                soup = BeautifulSoup(resp.text, "lxml")
                links = soup.select(company["selector"])

                for link in links:
                    text = link.get_text(strip=True).lower()
                    href = link.get("href", "")
                    if not href:
                        continue

                    # Filter: must match a target role OR fresher keyword
                    role_match = any(r in text for r in target_titles)
                    fresher_match = any(k in text for k in FRESHER_KEYWORDS)

                    if role_match or fresher_match:
                        apply_url = href if href.startswith("http") else company["url"].rstrip("/") + "/" + href.lstrip("/")
                        jobs.append({
                            "title": link.get_text(strip=True)[:100],
                            "company": company["name"],
                            "location": "Chennai / Bengaluru",
                            "apply_url": apply_url,
                            "platform": "careers_page",
                            "raw_jd": "",
                        })

        except Exception as e:
            logger.error(f"Careers scrape error for {company['name']}: {e}")

        random_delay(3, 5)

    logger.info(f"Careers pages: total {len(jobs)} jobs")
    return jobs
