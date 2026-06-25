"""Google Form application plugin using Playwright."""
import os
from utils.browser import new_browser
from utils.helpers import random_delay
from utils.logger import setup_logger

logger = setup_logger("google_form_plugin")

FIELD_KEYWORDS = {
    "name": ["name", "full name", "your name"],
    "email": ["email", "e-mail", "mail"],
    "phone": ["phone", "mobile", "contact", "number"],
    "linkedin": ["linkedin"],
    "github": ["github"],
    "portfolio": ["portfolio", "website"],
    "cover_letter": ["cover letter", "why do you want", "about yourself", "motivation"],
}


def apply(job: dict, resume_path: str, cover_letter: str, answers: dict, profile: dict) -> str:
    p = profile["personal"]
    url = job.get("apply_url", "")
    settings_headless = True  # always headless for forms

    pw, browser, context = new_browser(headless=settings_headless)
    page = context.new_page()

    try:
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        random_delay(2, 3)

        # Check for CAPTCHA
        if page.query_selector("div.recaptcha-checkbox") or page.query_selector("iframe[title*='reCAPTCHA']"):
            logger.warning("CAPTCHA detected on Google Form")
            return "captcha"

        # Get all input-like elements
        inputs = page.query_selector_all("input:not([type='hidden']):not([type='submit']), textarea")
        for inp in inputs:
            try:
                label = ""
                aria = inp.get_attribute("aria-label") or ""
                placeholder = inp.get_attribute("placeholder") or ""
                label_lower = (aria + " " + placeholder).lower()

                value = None
                for field, keywords in FIELD_KEYWORDS.items():
                    if any(kw in label_lower for kw in keywords):
                        if field == "name":
                            value = p["name"]
                        elif field == "email":
                            value = p["email"]
                        elif field == "phone":
                            value = p["phone"]
                        elif field == "linkedin":
                            value = p.get("linkedin", "")
                        elif field == "github":
                            value = p.get("github", "")
                        elif field == "portfolio":
                            value = p.get("portfolio", "")
                        elif field == "cover_letter":
                            value = cover_letter or "I am excited to apply for this role."
                        break

                # Also check answers dict
                if value is None:
                    for question, answer in answers.items():
                        if any(kw in label_lower for kw in question.lower().split()[:3]):
                            value = answer
                            break

                if value:
                    inp.fill(str(value))
                    random_delay(0.3, 0.8)

            except Exception as e:
                logger.warning(f"Form field fill error: {e}")
                continue

        # Handle file upload
        file_inputs = page.query_selector_all("input[type='file']")
        for fi in file_inputs:
            if resume_path and os.path.exists(resume_path):
                fi.set_input_files(resume_path)
                random_delay(1, 2)
                logger.info("Resume uploaded to form")

        random_delay(1, 2)

        # Submit
        submit_btn = (
            page.query_selector("div[role='button'][jsname='M2UYVd']")
            or page.query_selector("button[type='submit']")
            or page.query_selector("input[type='submit']")
        )
        if submit_btn:
            submit_btn.click()
            random_delay(2, 3)
            # Screenshot confirmation
            os.makedirs("logs/screenshots", exist_ok=True)
            page.screenshot(path=f"logs/screenshots/{job.get('company','unknown')}_form.png")
            logger.info(f"Google Form submitted for {job.get('title')} @ {job.get('company')}")
            return "success"
        else:
            logger.warning("No submit button found")
            return "human_needed"

    except Exception as e:
        logger.error(f"Google Form plugin error: {e}")
        return "human_needed"
    finally:
        page.close()
        context.close()
        browser.close()
        pw.stop()
