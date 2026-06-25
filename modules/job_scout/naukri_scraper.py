"""Naukri.com scraper using Playwright."""
import json
import re
from utils.browser import new_browser
from utils.helpers import random_delay
from utils.logger import setup_logger

logger = setup_logger("naukri_scraper")


def scrape(profile: dict, settings: dict) -> list[dict]:
    cities = profile["target"]["preferred_cities"]
    roles = profile["target"]["roles"][:3]  # top 3 roles
    max_jobs = settings["scraping"]["max_jobs_per_source"]
    headless = settings["scraping"]["headless"]
    jobs = []

    for role in roles:
        role_slug = role.lower().replace(" ", "-").replace("/", "-")
        for city in cities[:3]:
            if city.lower() == "remote":
                url = f"https://www.naukri.com/{role_slug}-jobs?experience=0"
            else:
                url = f"https://www.naukri.com/{role_slug}-jobs-in-{city.lower()}?experience=0"

            logger.info(f"Naukri: scraping {role} in {city}")
            pw, browser, context = new_browser(headless=headless)
            page = context.new_page()
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                random_delay(3, 5)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                random_delay(2, 3)

                job_cards = page.query_selector_all("article.jobTuple")
                logger.info(f"Naukri: {len(job_cards)} cards on page")

                for card in job_cards[:max_jobs]:
                    try:
                        title = card.query_selector(".title")
                        company = card.query_selector(".subTitle")
                        location = card.query_selector(".location")
                        salary = card.query_selector(".salary")
                        experience = card.query_selector(".experience")
                        link = card.query_selector("a.title")

                        apply_url = link.get_attribute("href") if link else url

                        jobs.append({
                            "title": title.inner_text().strip() if title else role,
                            "company": company.inner_text().strip() if company else "Unknown",
                            "location": location.inner_text().strip() if location else city,
                            "salary_text": salary.inner_text().strip() if salary else "",
                            "experience_text": experience.inner_text().strip() if experience else "",
                            "apply_url": apply_url,
                            "platform": "naukri",
                            "raw_jd": "",
                        })
                    except Exception as e:
                        logger.warning(f"Naukri card parse error: {e}")
                        continue

            except Exception as e:
                logger.error(f"Naukri scrape failed for {role} in {city}: {e}")
            finally:
                page.close()
                context.close()
                browser.close()
                pw.stop()

            random_delay(3, 6)
            if len(jobs) >= max_jobs:
                break

    logger.info(f"Naukri: total {len(jobs)} jobs found")
    return jobs
