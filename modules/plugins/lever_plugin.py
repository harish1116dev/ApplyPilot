"""Lever application plugin using Playwright."""
import os
from utils.browser import new_browser
from utils.helpers import random_delay
from utils.logger import setup_logger

logger = setup_logger("lever_plugin")


def apply(job: dict, resume_path: str, cover_letter: str, answers: dict, profile: dict) -> str:
    p = profile["personal"]
    url = job.get("apply_url", "")

    pw, browser, context = new_browser(headless=True)
    page = context.new_page()

    try:
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        random_delay(2, 3)

        # Standard Lever fields
        def fill_if_exists(selector: str, value: str):
            el = page.query_selector(selector)
            if el:
                el.fill(value)
                random_delay(0.3, 0.6)

        fill_if_exists("input[name='name']", p["name"])
        fill_if_exists("input[name='email']", p["email"])
        fill_if_exists("input[name='phone']", p["phone"])
        fill_if_exists("input[name='urls[LinkedIn]']", p.get("linkedin", ""))
        fill_if_exists("input[name='urls[GitHub]']", p.get("github", ""))
        fill_if_exists("input[name='urls[Portfolio]']", p.get("portfolio", ""))

        # Cover letter
        cl_area = page.query_selector("textarea[name='comments']")
        if cl_area and cover_letter:
            cl_area.fill(cover_letter[:3000])
            random_delay(0.5, 1)

        # Resume upload
        resume_input = page.query_selector("input[type='file']")
        if resume_input and resume_path and os.path.exists(resume_path):
            resume_input.set_input_files(resume_path)
            random_delay(2, 3)

        # Custom questions
        custom_inputs = page.query_selector_all("input[name^='cards[']")
        for inp in custom_inputs:
            label_el = page.query_selector(f"label[for='{inp.get_attribute('id')}']")
            label_text = label_el.inner_text().strip().lower() if label_el else ""
            for q, ans in answers.items():
                if any(word in label_text for word in q.lower().split()[:3]):
                    inp.fill(str(ans)[:500])
                    random_delay(0.3, 0.6)
                    break

        # Submit
        submit_btn = page.query_selector("button[type='submit']")
        if submit_btn:
            submit_btn.click()
            random_delay(3, 4)
            logger.info(f"Lever submitted: {job.get('title')} @ {job.get('company')}")
            return "success"
        else:
            return "human_needed"

    except Exception as e:
        logger.error(f"Lever plugin error: {e}")
        return "human_needed"
    finally:
        page.close()
        context.close()
        browser.close()
        pw.stop()
