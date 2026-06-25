"""Indeed India scraper using Playwright."""
from utils.browser import new_browser
from utils.helpers import random_delay
from utils.logger import setup_logger

logger = setup_logger("indeed_scraper")


def scrape(profile: dict, settings: dict) -> list[dict]:
    roles = profile["target"]["roles"][:2]
    cities = profile["target"]["preferred_cities"][:2]
    max_jobs = settings["scraping"]["max_jobs_per_source"]
    max_pages = settings["scraping"]["max_pages_per_source"]
    headless = settings["scraping"]["headless"]
    jobs = []

    for role in roles:
        for city in cities:
            encoded_role = role.replace(" ", "+")
            encoded_city = city.replace(" ", "+")
            base_url = f"https://in.indeed.com/jobs?q={encoded_role}+fresher&l={encoded_city}"
            logger.info(f"Indeed: scraping {role} in {city}")

            pw, browser, context = new_browser(headless=headless)
            page = context.new_page()
            try:
                for page_num in range(max_pages):
                    url = base_url if page_num == 0 else f"{base_url}&start={page_num * 10}"
                    page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    random_delay(3, 5)

                    cards = page.query_selector_all("div.job_seen_beacon")
                    logger.info(f"Indeed: {len(cards)} cards on page {page_num + 1}")

                    for card in cards:
                        try:
                            title_el = card.query_selector("h2.jobTitle span")
                            company_el = card.query_selector("span[data-testid='company-name']")
                            loc_el = card.query_selector("div[data-testid='text-location']")
                            link_el = card.query_selector("a[id^='job_']")

                            href = link_el.get_attribute("href") if link_el else ""
                            apply_url = ("https://in.indeed.com" + href) if href.startswith("/") else href or base_url

                            jobs.append({
                                "title": title_el.inner_text().strip() if title_el else role,
                                "company": company_el.inner_text().strip() if company_el else "Unknown",
                                "location": loc_el.inner_text().strip() if loc_el else city,
                                "apply_url": apply_url,
                                "platform": "indeed",
                                "raw_jd": "",
                            })
                        except Exception as e:
                            logger.warning(f"Indeed card error: {e}")
                            continue

                    random_delay(3, 5)
                    if len(jobs) >= max_jobs:
                        break

            except Exception as e:
                logger.error(f"Indeed error for {role}/{city}: {e}")
            finally:
                page.close()
                context.close()
                browser.close()
                pw.stop()

    logger.info(f"Indeed: total {len(jobs)} jobs")
    return jobs
