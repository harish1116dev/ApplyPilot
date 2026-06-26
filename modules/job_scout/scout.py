"""Module 3 — Scout: orchestrates all scrapers.

Scraper order is deliberate:
  1. LinkedIn  — httpx, no browser, fast, most results
  2. Careers   — httpx + ATS JSON APIs, no browser, fast
  3. Naukri    — Playwright (browser), runs 3rd so Ctrl+C after fast scrapers works
  4. Indeed    — Playwright (browser), last
  5. Wellfound — Playwright (browser), last (usually 403 anyway)

This way if the user hits Ctrl+C after the first two fast scrapers complete,
the pipeline already has 30-60 jobs to work with and no browser is running.
"""
import json
import os
from utils.logger import setup_logger
from utils.shutdown import is_shutdown
from modules.job_scout import (
    linkedin_scraper,
    careers_scraper,
    naukri_scraper,
    indeed_scraper,
    wellfound_scraper,
)

logger = setup_logger("scout")


def load_settings() -> dict:
    with open(os.path.join("config", "settings.json"), encoding="utf-8") as f:
        return json.load(f)


def run_all_scrapers(profile: dict, settings: dict = None) -> list[dict]:
    if settings is None:
        settings = load_settings()

    all_jobs = []

    # Fast (no browser) scrapers first — browser scrapers last
    scrapers = [
        ("LinkedIn",  linkedin_scraper.scrape),   # httpx JSON API
        ("Careers",   careers_scraper.scrape),    # httpx ATS APIs (Greenhouse/Lever)
        ("Naukri",    naukri_scraper.scrape),      # Playwright
        ("Indeed",    indeed_scraper.scrape),      # Playwright
        ("Wellfound", wellfound_scraper.scrape),   # Playwright (usually 403)
    ]

    for name, scraper_fn in scrapers:
        if is_shutdown():
            logger.warning(f"[scout] Shutdown — skipping remaining scrapers (have {len(all_jobs)} jobs so far)")
            break

        try:
            logger.info(f"Running {name} scraper...")
            results = scraper_fn(profile, settings)
            count = len(results)
            logger.info(f"{name}: returned {count} jobs")
            all_jobs.extend(results)
        except Exception as e:
            logger.error(f"{name} scraper crashed: {e}")
            continue

    logger.info(f"Total raw jobs from all scrapers: {len(all_jobs)}")
    return all_jobs
