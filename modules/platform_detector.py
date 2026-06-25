"""Module 11 — Platform Detector: identifies application form type from URL."""
import httpx
from bs4 import BeautifulSoup
from utils.helpers import random_user_agent
from utils.logger import setup_logger

logger = setup_logger("platform_detector")

URL_PATTERNS: dict[str, list[str]] = {
    "linkedin": ["linkedin.com/jobs", "linkedin.com/easy-apply"],
    "lever": ["jobs.lever.co", "lever.co"],
    "greenhouse": ["greenhouse.io", "boards.greenhouse.io"],
    "workday": ["workday.com", "myworkdayjobs.com"],
    "google_form": ["docs.google.com/forms", "forms.google.com"],
    "naukri": ["naukri.com"],
    "indeed": ["indeed.com"],
    "wellfound": ["wellfound.com", "angel.co"],
}

HTML_SIGNATURES: dict[str, list[str]] = {
    "lever": ["lever-apply", "lever-team"],
    "greenhouse": ["greenhouse-job-board", "grnhse_app"],
    "workday": ["workday", "wd3.myworkdayjobs"],
    "google_form": ["google.com/forms", "FormView"],
    "linkedin": ["linkedin", "easy-apply"],
}


def detect_platform(url: str) -> str:
    if not url:
        return "generic"

    url_lower = url.lower()
    for platform, patterns in URL_PATTERNS.items():
        if any(p in url_lower for p in patterns):
            logger.debug(f"Platform detected by URL: {platform}")
            return platform

    # Fallback: fetch page and inspect HTML
    return _inspect_html(url)


def _inspect_html(url: str) -> str:
    try:
        with httpx.Client(
            headers={"User-Agent": random_user_agent()},
            follow_redirects=True,
            timeout=15,
        ) as client:
            resp = client.get(url)
            html = resp.text.lower()

            for platform, sigs in HTML_SIGNATURES.items():
                if any(sig.lower() in html for sig in sigs):
                    logger.debug(f"Platform detected by HTML: {platform}")
                    return platform

    except Exception as e:
        logger.warning(f"Platform HTML inspect failed for {url}: {e}")

    logger.debug(f"Platform: generic (fallback) for {url}")
    return "generic"
