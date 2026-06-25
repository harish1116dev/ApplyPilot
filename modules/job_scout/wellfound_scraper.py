"""Wellfound (AngelList) scraper — httpx + BeautifulSoup."""
import httpx
from bs4 import BeautifulSoup
from utils.helpers import random_delay, random_user_agent
from utils.logger import setup_logger

logger = setup_logger("wellfound_scraper")

WELLFOUND_ROLES = {
    "Full Stack Developer": "full-stack-engineer",
    "Frontend Developer": "frontend-engineer",
    "Backend Developer": "backend-engineer",
    "Software Engineer": "software-engineer",
    "AI/ML Engineer": "machine-learning-engineer",
    "Flutter Developer": "mobile-developer",
}


def scrape(profile: dict, settings: dict) -> list[dict]:
    roles = profile["target"]["roles"]
    max_jobs = settings["scraping"]["max_jobs_per_source"]
    jobs = []

    for role in roles:
        slug = WELLFOUND_ROLES.get(role, "software-engineer")
        url = f"https://wellfound.com/jobs?roles[]={slug}&locations[]=chennai"
        logger.info(f"Wellfound: scraping {role}")

        try:
            with httpx.Client(
                headers={"User-Agent": random_user_agent()},
                follow_redirects=True,
                timeout=20,
            ) as client:
                resp = client.get(url)
                if resp.status_code != 200:
                    logger.warning(f"Wellfound returned {resp.status_code}")
                    continue

                soup = BeautifulSoup(resp.text, "lxml")
                cards = soup.select("div[class*='JobListing']")

                for card in cards[:max_jobs]:
                    try:
                        title_el = card.select_one("a[class*='jobTitle'], h2")
                        company_el = card.select_one("a[class*='companyName'], h3")
                        loc_el = card.select_one("span[class*='location']")
                        link_el = card.select_one("a[href*='/jobs/']")

                        jobs.append({
                            "title": title_el.get_text(strip=True) if title_el else role,
                            "company": company_el.get_text(strip=True) if company_el else "Unknown",
                            "location": loc_el.get_text(strip=True) if loc_el else "Chennai",
                            "apply_url": "https://wellfound.com" + link_el["href"] if link_el else url,
                            "platform": "wellfound",
                            "raw_jd": "",
                        })
                    except Exception as e:
                        logger.warning(f"Wellfound card error: {e}")
                        continue

        except Exception as e:
            logger.error(f"Wellfound error for {role}: {e}")

        random_delay(3, 5)
        if len(jobs) >= max_jobs:
            break

    logger.info(f"Wellfound: total {len(jobs)} jobs")
    return jobs
