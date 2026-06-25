"""Module 3 — Scout: orchestrates all scrapers."""
import json
import os
from utils.logger import setup_logger
from modules.job_scout import (
    naukri_scraper,
    linkedin_scraper,
    wellfound_scraper,
    indeed_scraper,
    careers_scraper,
)

logger = setup_logger("scout")


def load_settings() -> dict:
    with open(os.path.join("config", "settings.json")) as f:
        return json.load(f)


def build_search_query(profile: dict) -> str:
    roles = " OR ".join(f'"{r}"' for r in profile["target"]["roles"][:4])
    cities = " OR ".join(profile["target"]["preferred_cities"][:3])
    return f'("fresher" OR "0-2 years") ({roles}) ({cities})'


def run_all_scrapers(profile: dict, settings: dict = None) -> list[dict]:
    if settings is None:
        settings = load_settings()

    all_jobs = []
    scrapers = [
        ("Wellfound", wellfound_scraper.scrape),
        ("Naukri", naukri_scraper.scrape),
        ("LinkedIn", linkedin_scraper.scrape),
        ("Indeed", indeed_scraper.scrape),
        ("Careers", careers_scraper.scrape),
    ]

    for name, scraper_fn in scrapers:
        try:
            logger.info(f"Running {name} scraper...")
            results = scraper_fn(profile, settings)
            logger.info(f"{name}: returned {len(results)} jobs")
            all_jobs.extend(results)
        except Exception as e:
            logger.error(f"{name} scraper crashed: {e}")
            continue

    logger.info(f"Total raw jobs from all scrapers: {len(all_jobs)}")
    return all_jobs
