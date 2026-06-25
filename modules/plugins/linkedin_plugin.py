"""LinkedIn Easy Apply plugin using Playwright."""
import os
from utils.browser import new_browser
from utils.helpers import random_delay
from utils.logger import setup_logger

logger = setup_logger("linkedin_plugin")


def apply(job: dict, resume_path: str, cover_letter: str, answers: dict, profile: dict) -> str:
    p = profile["personal"]
    url = job.get("apply_url", "")
    email = os.getenv("LINKEDIN_EMAIL")
    password = os.getenv("LINKEDIN_PASSWORD")

    if not email or not password:
        logger.warning("LinkedIn credentials not set — human needed")
        return "human_needed"

    pw, browser, context = new_browser(headless=True)
    page = context.new_page()

    try:
        # Login
        page.goto("https://www.linkedin.com/login", timeout=30000)
        random_delay(2, 3)
        page.fill("#username", email)
        page.fill("#password", password)
        page.click("button[type='submit']")
        random_delay(3, 5)

        # Check if logged in
        if "feed" not in page.url and "checkpoint" in page.url:
            logger.warning("LinkedIn login checkpoint — OTP/captcha required")
            return "captcha"

        # Navigate to job
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        random_delay(2, 3)

        # Click Easy Apply
        easy_apply_btn = page.query_selector("button.jobs-apply-button")
        if not easy_apply_btn:
            logger.warning("No Easy Apply button found")
            return "human_needed"

        easy_apply_btn.click()
        random_delay(2, 3)

        # Handle multi-step form (up to 10 steps)
        for step in range(10):
            # Check for CAPTCHA
            if page.query_selector("iframe[title*='challenge']"):
                return "captcha"

            # Fill phone if empty
            phone_input = page.query_selector("input[id*='phoneNumber']")
            if phone_input and not phone_input.input_value():
                phone_input.fill(p["phone"])
                random_delay(0.5, 1)

            # Upload resume if requested
            resume_input = page.query_selector("input[type='file']")
            if resume_input and resume_path and os.path.exists(resume_path):
                resume_input.set_input_files(resume_path)
                random_delay(1, 2)

            # Fill text areas (cover letter / screening questions)
            textareas = page.query_selector_all("textarea")
            for ta in textareas:
                label = (ta.get_attribute("aria-label") or "").lower()
                if "cover" in label and cover_letter:
                    ta.fill(cover_letter[:2000])
                elif label and answers:
                    for q, ans in answers.items():
                        if any(word in label for word in q.lower().split()[:3]):
                            ta.fill(str(ans)[:500])
                            break
                random_delay(0.3, 0.6)

            # Check for Next / Review / Submit buttons
            submit_btn = page.query_selector("button[aria-label='Submit application']")
            next_btn = page.query_selector("button[aria-label='Continue to next step']")
            review_btn = page.query_selector("button[aria-label='Review your application']")

            if submit_btn:
                submit_btn.click()
                random_delay(2, 3)
                logger.info(f"LinkedIn Easy Apply submitted: {job.get('title')} @ {job.get('company')}")
                return "success"
            elif review_btn:
                review_btn.click()
            elif next_btn:
                next_btn.click()
            else:
                logger.warning(f"LinkedIn: no action button found at step {step}")
                break

            random_delay(1, 2)

        return "human_needed"

    except Exception as e:
        logger.error(f"LinkedIn plugin error: {e}")
        return "human_needed"
    finally:
        page.close()
        context.close()
        browser.close()
        pw.stop()
