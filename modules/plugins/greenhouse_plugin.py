"""Greenhouse application plugin using Playwright."""
import os
from utils.browser import new_browser
from utils.helpers import random_delay
from utils.logger import setup_logger

logger = setup_logger("greenhouse_plugin")


def apply(job: dict, resume_path: str, cover_letter: str, answers: dict, profile: dict) -> str:
    p = profile["personal"]
    url = job.get("apply_url", "")

    pw, browser, context = new_browser(headless=True)
    page = context.new_page()

    try:
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        random_delay(2, 3)

        def fill_if_exists(selector: str, value: str):
            el = page.query_selector(selector)
            if el and value:
                el.fill(value)
                random_delay(0.3, 0.6)

        # Standard Greenhouse fields
        fill_if_exists("input#first_name", p["name"].split()[0])
        fill_if_exists("input#last_name", " ".join(p["name"].split()[1:]) or p["name"])
        fill_if_exists("input#email", p["email"])
        fill_if_exists("input#phone", p["phone"])
        fill_if_exists("input#job_application_linkedin_url", p.get("linkedin", ""))
        fill_if_exists("input#job_application_website", p.get("portfolio", ""))

        # Resume upload
        resume_input = page.query_selector("input[type='file']#resume")
        if not resume_input:
            resume_input = page.query_selector("input[type='file']")
        if resume_input and resume_path and os.path.exists(resume_path):
            resume_input.set_input_files(resume_path)
            random_delay(2, 3)

        # Cover letter
        cl_input = page.query_selector("input[type='file']#cover_letter")
        if cl_input and cover_letter:
            # Save cover letter as text file and attach
            cl_path = "logs/cover_letter_temp.txt"
            os.makedirs("logs", exist_ok=True)
            with open(cl_path, "w", encoding="utf-8") as f:
                f.write(cover_letter)
            cl_input.set_input_files(cl_path)
            random_delay(1, 2)

        # Custom questions (Greenhouse uses data-source attribute)
        custom_fields = page.query_selector_all("li.custom-field")
        for field in custom_fields:
            label_el = field.query_selector("label")
            label_text = label_el.inner_text().strip().lower() if label_el else ""
            inp = field.query_selector("input, textarea")
            if inp:
                for q, ans in answers.items():
                    if any(word in label_text for word in q.lower().split()[:3]):
                        inp.fill(str(ans)[:500])
                        random_delay(0.3, 0.5)
                        break

        # Submit
        submit_btn = page.query_selector("input[type='submit']#submit_app")
        if not submit_btn:
            submit_btn = page.query_selector("button[type='submit']")
        if submit_btn:
            submit_btn.click()
            random_delay(3, 4)
            logger.info(f"Greenhouse submitted: {job.get('title')} @ {job.get('company')}")
            return "success"
        else:
            return "human_needed"

    except Exception as e:
        logger.error(f"Greenhouse plugin error: {e}")
        return "human_needed"
    finally:
        page.close()
        context.close()
        browser.close()
        pw.stop()
