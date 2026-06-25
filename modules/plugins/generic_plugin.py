"""Generic application plugin — last resort fallback."""
import os
from utils.browser import new_browser
from utils.helpers import random_delay
from utils.logger import setup_logger

logger = setup_logger("generic_plugin")

FIELD_MAP = {
    "name": ["name", "full name", "your name", "applicant name"],
    "email": ["email", "e-mail"],
    "phone": ["phone", "mobile", "contact number"],
    "linkedin": ["linkedin"],
    "github": ["github"],
    "portfolio": ["portfolio", "website", "url"],
}


def apply(job: dict, resume_path: str, cover_letter: str, answers: dict, profile: dict) -> str:
    p = profile["personal"]
    url = job.get("apply_url", "")

    pw, browser, context = new_browser(headless=True)
    page = context.new_page()
    filled_count = 0

    try:
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        random_delay(2, 3)

        # CAPTCHA check
        if page.query_selector("iframe[title*='reCAPTCHA']") or page.query_selector("div.recaptcha-checkbox"):
            return "captcha"

        profile_values = {
            "name": p["name"],
            "email": p["email"],
            "phone": p["phone"],
            "linkedin": p.get("linkedin", ""),
            "github": p.get("github", ""),
            "portfolio": p.get("portfolio", ""),
        }

        inputs = page.query_selector_all("input:not([type='hidden']):not([type='submit']):not([type='checkbox']):not([type='radio']), textarea")

        for inp in inputs:
            try:
                inp_type = inp.get_attribute("type") or "text"
                if inp_type == "file":
                    continue

                aria = (inp.get_attribute("aria-label") or "").lower()
                placeholder = (inp.get_attribute("placeholder") or "").lower()
                name_attr = (inp.get_attribute("name") or "").lower()
                combined = f"{aria} {placeholder} {name_attr}"

                value = None
                for field, keywords in FIELD_MAP.items():
                    if any(kw in combined for kw in keywords):
                        value = profile_values.get(field, "")
                        break

                if value is None:
                    for q, ans in answers.items():
                        if any(word in combined for word in q.lower().split()[:3]):
                            value = ans
                            break

                if value:
                    inp.fill(str(value)[:500])
                    filled_count += 1
                    random_delay(0.3, 0.6)

            except Exception:
                continue

        # Resume upload
        file_inputs = page.query_selector_all("input[type='file']")
        for fi in file_inputs:
            if resume_path and os.path.exists(resume_path):
                fi.set_input_files(resume_path)
                random_delay(1, 2)

        if filled_count == 0:
            logger.warning(f"Generic plugin: no fields filled for {url}")
            return "human_needed"

        # Try to submit
        submit = (
            page.query_selector("button[type='submit']")
            or page.query_selector("input[type='submit']")
        )
        if submit:
            submit.click()
            random_delay(2, 3)
            logger.info(f"Generic plugin submitted ({filled_count} fields) for {job.get('company')}")
            return "success"
        else:
            return "partial"

    except Exception as e:
        logger.error(f"Generic plugin error: {e}")
        return "human_needed"
    finally:
        page.close()
        context.close()
        browser.close()
        pw.stop()
