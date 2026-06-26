"""Playwright browser factory — Windows-thread-safe."""
import asyncio
import os
import sys
from playwright.sync_api import sync_playwright, Browser, BrowserContext
from utils.helpers import random_user_agent


def _fix_windows_event_loop():
    """
    On Windows, asyncio defaults to ProactorEventLoop in the main thread
    but worker threads get no event loop at all.
    Playwright's sync API needs one → create it if missing.
    """
    if sys.platform != "win32":
        return
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        # No event loop in this thread — create a fresh one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    # Ensure ProactorEventLoop (required for subprocess on Windows)
    if not isinstance(loop, asyncio.ProactorEventLoop):
        new_loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(new_loop)


def new_browser(headless: bool = True) -> tuple:
    """Return (playwright, browser, context). Caller must close all three."""
    _fix_windows_event_loop()

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
