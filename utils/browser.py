"""Playwright browser factory."""
import os
from playwright.sync_api import sync_playwright, Browser, BrowserContext
from utils.helpers import random_user_agent


def new_browser(headless: bool = True) -> tuple:
    """Return (playwright, browser, context). Caller must close all three."""
    proxy_url = os.getenv("PROXY_URL")
    proxy = {"server": proxy_url} if proxy_url else None

    pw = sync_playwright().start()
    browser: Browser = pw.chromium.launch(
        headless=headless,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
    )
    context: BrowserContext = browser.new_context(
        user_agent=random_user_agent(),
        viewport={"width": 1280, "height": 800},
        proxy=proxy,
        locale="en-IN",
        timezone_id="Asia/Kolkata",
    )
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return pw, browser, context
