"""
Wellfound (AngelList) scraper — Playwright with stealth headers.

Wellfound blocks plain httpx requests (Cloudflare 403).
Uses a headed/headless Chromium session with realistic headers.
Ctrl+C safe: checks is_shutdown() before each role iteration.
"""
from utils.browser import new_browser
from utils.helpers import random_delay
from utils.logger import setup_logger
from utils.shutdown import is_shutdown

logger = setup_logger("wellfound_scraper")

# Wellfound role slugs mapped from profile roles
ROLE_SLUGS = {
    "Full Stack Developer":  "full-stack-engineer",
    "Frontend Developer":    "frontend-engineer",
    "Backend Developer":     "backend-engineer",
    "Software Engineer":     "software-engineer",
    "Node.js Developer":     "backend-engineer",
    "React Developer":       "frontend-engineer",
    "AI/ML Engineer":        "machine-learning-engineer",
    "Flutter Developer":     "mobile-developer",
}


def scrape(profile: dict, settings: dict) -> list[dict]:
    roles = profile["target"]["roles"]
    cities = profile["target"]["preferred_cities"][:2]
    max_jobs = settings["scraping"]["max_jobs_per_source"]
    headless = settings["scraping"]["headless"]
    jobs = []

    # Deduplicate slugs (multiple roles → same slug)
    seen_slugs: set[str] = set()

    for role in roles:
        if is_shutdown():
            break
        if len(jobs) >= max_jobs:
            break

        slug = ROLE_SLUGS.get(role, "software-engineer")
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        # Wellfound location mapping
        location_filters = []
        for city in cities:
            c = city.lower()
            if c in ("chennai", "coimbatore"):
                location_filters.append("india")
                break
            elif c == "bengaluru":
                location_filters.append("bangalore")
            elif c == "remote":
                location_filters.append("remote")

        if not location_filters:
            location_filters = ["india"]

        loc_param = location_filters[0]
        url = f"https://wellfound.com/jobs?roles[]={slug}&locations[]={loc_param}"
        logger.info(f"Wellfound: scraping {slug} / {loc_param}")

        pw, browser, context = new_browser(headless=headless)
        page = context.new_page()

        # Extra stealth headers to bypass Cloudflare
        page.set_extra_http_headers({
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
            "Sec-Fetch-Dest": "document",
            "Upgrade-Insecure-Requests": "1",
        })

        try:
            resp = page.goto(url, timeout=20000, wait_until="domcontentloaded")

            if resp and resp.status == 403:
                logger.warning(f"Wellfound 403 blocked for {slug} — skipping (need login/proxy)")
                continue
            if resp and resp.status != 200:
                logger.warning(f"Wellfound returned {resp.status} for {slug}")
                continue

            random_delay(3, 5)
            if is_shutdown():
                break

            # Wellfound 2025 selectors
            cards = page.query_selector_all("div[class*='JobListing']")
            if not cards:
                cards = page.query_selector_all("[data-test='job-listing']")
            if not cards:
                cards = page.query_selector_all("div[class*='styles_jobListing']")

            logger.info(f"Wellfound: {len(cards)} cards for {slug}")

            for card in cards[:max_jobs]:
                if is_shutdown():
                    break
                try:
                    title_el = (
                        card.query_selector("a[class*='jobTitle']")
                        or card.query_selector("h2 a")
                        or card.query_selector("span[class*='title']")
                    )
                    company_el = (
                        card.query_selector("a[class*='companyName']")
                        or card.query_selector("h3 a")
                        or card.query_selector("span[class*='company']")
                    )
                    loc_el = card.query_selector("span[class*='location']")
                    link_el = (
                        card.query_selector("a[href*='/jobs/']")
                        or card.query_selector("a[href*='wellfound.com']")
                    )

                    href = link_el.get_attribute("href") if link_el else ""
                    apply_url = (
                        ("https://wellfound.com" + href) if href and href.startswith("/")
                        else href or url
                    )

                    jobs.append({
                        "title": title_el.inner_text().strip() if title_el else role,
                        "company": company_el.inner_text().strip() if company_el else "Unknown",
                        "location": loc_el.inner_text().strip() if loc_el else loc_param,
                        "apply_url": apply_url,
                        "platform": "wellfound",
                        "raw_jd": "",
                    })
                except Exception as e:
                    logger.debug(f"Wellfound card error: {e}")
                    continue

        except Exception as e:
            if "timeout" in str(e).lower():
                logger.warning(f"Wellfound timeout for {slug}")
            else:
                logger.error(f"Wellfound error for {slug}: {e}")
        finally:
            try:
                page.close()
                context.close()
                browser.close()
                pw.stop()
            except Exception:
                pass

        random_delay(3, 5)

    logger.info(f"Wellfound: total {len(jobs)} jobs")
    return jobs
