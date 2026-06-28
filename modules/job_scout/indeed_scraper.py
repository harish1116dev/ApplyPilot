"""
Indeed India scraper using Playwright.
Ctrl+C safe: checks is_shutdown() before each page/card iteration.

Fix (2026-06): Indeed's 2025 card DOM changed significantly.
  - Cards are now rendered as <li> elements with data-jk attribute
  - Title is in <span data-testid="jobTitle"> or <a[data-jk]>
  - Company is in <span data-testid="company-name">
  - Location is in <div data-testid="text-location">
  - Apply URL extracted from data-jk: https://in.indeed.com/viewjob?jk=<jk>
  - Fallback selectors preserved for resilience
"""
from utils.browser import new_browser
from utils.helpers import random_delay
from utils.logger import setup_logger
from utils.shutdown import is_shutdown

logger = setup_logger("indeed_scraper")


def _extract_job_key(card) -> str:
    """Extract Indeed's job key (jk) from a card element."""
    # Try data-jk on the card itself
    jk = card.get_attribute("data-jk") or ""
    if not jk:
        # Try on child anchor
        link = card.query_selector("a[data-jk]")
        if link:
            jk = link.get_attribute("data-jk") or ""
    if not jk:
        # Try id starting with job_
        link = card.query_selector("a[id^='job_']")
        if link:
            jid = link.get_attribute("id") or ""
            jk = jid.replace("job_", "")
    return jk.strip()


def _extract_title(card) -> str:
    """Extract job title from a card element."""
    # Modern Indeed: <a data-jk="..."><span>Title</span></a>
    for sel in [
        "span[data-testid='jobTitle']",
        "a[data-jk] span",
        "h2[class*='title'] span[title]",
        "h2[class*='title'] span",
        "h2.jobTitle span[title]",
        "h2.jobTitle span",
        "a[id^='job_'] span",
    ]:
        el = card.query_selector(sel)
        if el:
            text = el.get_attribute("title") or el.inner_text().strip()
            if text:
                return text
    return ""


def _extract_company(card) -> str:
    for sel in [
        "span[data-testid='company-name']",
        "[class*='companyName']",
        "[class*='company-name']",
        "span[class*='company']",
    ]:
        el = card.query_selector(sel)
        if el:
            text = el.inner_text().strip()
            if text:
                return text
    return "Unknown"


def _extract_location(card, fallback: str = "") -> str:
    for sel in [
        "div[data-testid='text-location']",
        "div[data-testid='job-location']",
        "[class*='companyLocation']",
        "[class*='location']",
    ]:
        el = card.query_selector(sel)
        if el:
            text = el.inner_text().strip()
            if text:
                return text
    return fallback


def scrape(profile: dict, settings: dict) -> list[dict]:
    roles = profile["target"]["roles"]  # all roles — no cap
    cities = profile["target"]["preferred_cities"][:3]
    max_jobs = settings["scraping"]["max_jobs_per_source"]
    max_pages = settings["scraping"]["max_pages_per_source"]
    headless = settings["scraping"]["headless"]
    timeout_ms = settings["scraping"].get("playwright_timeout_ms", 15000)
    jobs = []
    seen_jks: set[str] = set()  # deduplicate within scraper by job key

    for role in roles:
        if is_shutdown():
            break
        for city in cities:
            if is_shutdown():
                break

            encoded_role = role.replace(" ", "+")
            encoded_city = city.replace(" ", "+")
            # Append "fresher" to bias results toward entry-level
            base_url = (
                f"https://in.indeed.com/jobs?q={encoded_role}+fresher"
                f"&l={encoded_city}&sort=date"
            )
            logger.info(f"Indeed: scraping '{role}' in {city}")

            pw, browser, context = new_browser(headless=headless)
            page = context.new_page()
            try:
                for page_num in range(max_pages):
                    if is_shutdown():
                        break

                    start = page_num * 10
                    url = base_url if page_num == 0 else f"{base_url}&start={start}"
                    try:
                        page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                    except Exception as e:
                        logger.warning(f"Indeed goto timeout for {role}/{city} page {page_num+1}: {e}")
                        break

                    random_delay(2, 4)
                    if is_shutdown():
                        break

                    # ── Card selectors (tried in order, first match wins) ──────
                    # Modern Indeed wraps cards in <li data-jk="...">
                    cards = page.query_selector_all("li[data-jk]")
                    if not cards:
                        # Older layout: div.job_seen_beacon
                        cards = page.query_selector_all("div.job_seen_beacon")
                    if not cards:
                        cards = page.query_selector_all("div[class*='job_seen_beacon']")
                    if not cards:
                        # Generic fallback: any card-like container with a job link
                        cards = page.query_selector_all("div[data-jk]")

                    logger.info(
                        f"Indeed: {len(cards)} cards on page {page_num + 1} "
                        f"for '{role}'/{city}"
                    )

                    if not cards:
                        break  # No more results on this page

                    page_new = 0
                    for card in cards:
                        if is_shutdown():
                            break
                        try:
                            title_text = _extract_title(card)
                            if not title_text:
                                continue

                            company_text = _extract_company(card)
                            location_text = _extract_location(card, fallback=city)

                            # Build apply URL from job key (most reliable)
                            jk = _extract_job_key(card)
                            if jk and jk in seen_jks:
                                continue
                            if jk:
                                seen_jks.add(jk)
                                apply_url = f"https://in.indeed.com/viewjob?jk={jk}"
                            else:
                                # Fallback: try getting href from any anchor in card
                                link_el = (
                                    card.query_selector("a[data-jk]")
                                    or card.query_selector("h2 a")
                                    or card.query_selector("a[id^='job_']")
                                )
                                href = link_el.get_attribute("href") if link_el else ""
                                apply_url = (
                                    ("https://in.indeed.com" + href)
                                    if href and href.startswith("/")
                                    else (href or base_url)
                                )

                            jobs.append({
                                "title": title_text,
                                "company": company_text,
                                "location": location_text,
                                "apply_url": apply_url,
                                "platform": "indeed",
                                "raw_jd": "",
                            })
                            page_new += 1

                        except Exception as e:
                            logger.debug(f"Indeed card parse error: {e}")
                            continue

                    logger.debug(f"Indeed: extracted {page_new} new jobs from page {page_num + 1}")
                    random_delay(2, 4)

                    if len(jobs) >= max_jobs:
                        logger.info(f"Indeed: reached max_jobs={max_jobs}, stopping")
                        break

            except Exception as e:
                logger.error(f"Indeed error for '{role}'/'{city}': {e}")
            finally:
                try:
                    page.close()
                    context.close()
                    browser.close()
                    pw.stop()
                except Exception:
                    pass

    logger.info(f"Indeed: total {len(jobs)} jobs")
    return jobs
