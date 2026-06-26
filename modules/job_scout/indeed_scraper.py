"""
Indeed India scraper using Playwright.
Ctrl+C safe: checks is_shutdown() before each page/card iteration.
"""
from utils.browser import new_browser
from utils.helpers import random_delay
from utils.logger import setup_logger
from utils.shutdown import is_shutdown

logger = setup_logger("indeed_scraper")


def scrape(profile: dict, settings: dict) -> list[dict]:
    roles = profile["target"]["roles"]  # all roles — no cap
    cities = profile["target"]["preferred_cities"][:3]
    max_jobs = settings["scraping"]["max_jobs_per_source"]
    max_pages = settings["scraping"]["max_pages_per_source"]
    headless = settings["scraping"]["headless"]
    timeout_ms = settings["scraping"].get("playwright_timeout_ms", 15000)
    jobs = []

    for role in roles:
        if is_shutdown():
            break
        for city in cities:
            if is_shutdown():
                break

            encoded_role = role.replace(" ", "+")
            encoded_city = city.replace(" ", "+")
            base_url = f"https://in.indeed.com/jobs?q={encoded_role}+fresher&l={encoded_city}"
            logger.info(f"Indeed: scraping '{role}' in {city}")

            pw, browser, context = new_browser(headless=headless)
            page = context.new_page()
            try:
                for page_num in range(max_pages):
                    if is_shutdown():
                        break

                    url = base_url if page_num == 0 else f"{base_url}&start={page_num * 10}"
                    try:
                        page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                    except Exception as e:
                        logger.warning(f"Indeed goto timeout for {role}/{city} page {page_num}: {e}")
                        break

                    random_delay(2, 4)
                    if is_shutdown():
                        break

                    # Indeed 2025 selectors
                    cards = page.query_selector_all("div.job_seen_beacon")
                    if not cards:
                        cards = page.query_selector_all("div[class*='job_seen_beacon']")
                    if not cards:
                        cards = page.query_selector_all("li[class*='css-'] div[data-testid]")

                    logger.info(f"Indeed: {len(cards)} cards on page {page_num + 1} for '{role}'/{city}")

                    if not cards:
                        break  # No more results

                    for card in cards:
                        if is_shutdown():
                            break
                        try:
                            title_el = (
                                card.query_selector("h2.jobTitle span[title]")
                                or card.query_selector("h2.jobTitle span")
                                or card.query_selector("h2[class*='title'] span")
                            )
                            company_el = (
                                card.query_selector("span[data-testid='company-name']")
                                or card.query_selector("[class*='company-name']")
                            )
                            loc_el = (
                                card.query_selector("div[data-testid='text-location']")
                                or card.query_selector("[class*='companyLocation']")
                            )
                            link_el = (
                                card.query_selector("a[id^='job_']")
                                or card.query_selector("h2.jobTitle a")
                                or card.query_selector("a[data-jk]")
                            )

                            title_text = title_el.inner_text().strip() if title_el else ""
                            if not title_text:
                                title_attr = title_el.get_attribute("title") if title_el else ""
                                title_text = title_attr or role

                            href = link_el.get_attribute("href") if link_el else ""
                            apply_url = (
                                ("https://in.indeed.com" + href) if href and href.startswith("/")
                                else href or base_url
                            )

                            if not title_text or title_text == role:
                                continue

                            jobs.append({
                                "title": title_text,
                                "company": company_el.inner_text().strip() if company_el else "Unknown",
                                "location": loc_el.inner_text().strip() if loc_el else city,
                                "apply_url": apply_url,
                                "platform": "indeed",
                                "raw_jd": "",
                            })
                        except Exception as e:
                            logger.debug(f"Indeed card error: {e}")
                            continue

                    random_delay(2, 4)
                    if len(jobs) >= max_jobs:
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
