"""LinkedIn job scraper — uses public RSS + httpx fallback."""
import os
import httpx
import xml.etree.ElementTree as ET
from utils.logger import setup_logger
from utils.helpers import random_delay, random_user_agent

logger = setup_logger("linkedin_scraper")


def scrape(profile: dict, settings: dict) -> list[dict]:
    roles = profile["target"]["roles"][:3]
    cities = profile["target"]["preferred_cities"][:3]
    max_jobs = settings["scraping"]["max_jobs_per_source"]
    jobs = []

    for role in roles:
        for city in cities:
            encoded_role = role.replace(" ", "+")
            encoded_city = "" if city.lower() == "remote" else city.replace(" ", "+")
            # LinkedIn public job RSS (no auth needed, less blocking)
            url = (
                f"https://www.linkedin.com/jobs/search/?keywords={encoded_role}"
                f"&location={encoded_city}&f_E=1&f_JT=F&trk=public_jobs_jobs-search-bar_search-submit"
            )
            logger.info(f"LinkedIn: scraping {role} in {city}")
            try:
                with httpx.Client(
                    headers={"User-Agent": random_user_agent()},
                    follow_redirects=True,
                    timeout=20,
                ) as client:
                    resp = client.get(url)
                    if resp.status_code != 200:
                        logger.warning(f"LinkedIn returned {resp.status_code} for {role}/{city}")
                        continue

                    # Try to parse job cards from HTML (basic extraction)
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, "lxml")
                    cards = soup.select("div.base-card")
                    for card in cards[:max_jobs]:
                        try:
                            title_el = card.select_one("h3.base-search-card__title")
                            company_el = card.select_one("h4.base-search-card__subtitle")
                            loc_el = card.select_one("span.job-search-card__location")
                            link_el = card.select_one("a.base-card__full-link")

                            jobs.append({
                                "title": title_el.get_text(strip=True) if title_el else role,
                                "company": company_el.get_text(strip=True) if company_el else "Unknown",
                                "location": loc_el.get_text(strip=True) if loc_el else city,
                                "apply_url": link_el["href"].split("?")[0] if link_el else url,
                                "platform": "linkedin",
                                "raw_jd": "",
                            })
                        except Exception as e:
                            logger.warning(f"LinkedIn card parse error: {e}")
                            continue

            except Exception as e:
                logger.error(f"LinkedIn scrape error for {role}/{city}: {e}")

            random_delay(3, 6)
            if len(jobs) >= max_jobs:
                break

    logger.info(f"LinkedIn: total {len(jobs)} jobs found")
    return jobs
