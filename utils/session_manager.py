"""
utils/session_manager.py — Browser session persistence.

Saves Playwright browser storage state (cookies + localStorage) to disk.
Re-uses sessions on subsequent runs → fewer logins → less CAPTCHA.
"""
import os
import json
import time
from pathlib import Path
from utils.browser import new_browser
from utils.helpers import random_delay
from utils.logger import setup_logger

logger = setup_logger("session_manager")

SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)

# Session valid for 12 hours
SESSION_TTL_SECONDS = 12 * 3600


def _session_path(platform: str) -> Path:
    return SESSIONS_DIR / f"{platform}_session.json"


def _meta_path(platform: str) -> Path:
    return SESSIONS_DIR / f"{platform}_meta.json"


def session_is_valid(platform: str) -> bool:
    """Check if a saved session exists and is still fresh."""
    meta = _meta_path(platform)
    if not meta.exists():
        return False
    try:
        with open(meta) as f:
            data = json.load(f)
        age = time.time() - data.get("saved_at", 0)
        return age < SESSION_TTL_SECONDS
    except Exception:
        return False


def load_session(platform: str):
    """Return the path to the saved session file (for Playwright's load_storage_state)."""
    path = _session_path(platform)
    if path.exists():
        logger.info(f"[session] Loading saved {platform} session")
        return str(path)
    return None


def save_session(platform: str, context) -> None:
    """Save Playwright browser context state to disk."""
    try:
        path = str(_session_path(platform))
        context.storage_state(path=path)
        with open(_meta_path(platform), "w") as f:
            json.dump({"saved_at": time.time(), "platform": platform}, f)
        logger.info(f"[session] Saved {platform} session to {path}")
    except Exception as e:
        logger.warning(f"[session] Failed to save {platform} session: {e}")


def invalidate_session(platform: str) -> None:
    """Delete a session (call this when login fails / session expired)."""
    for path in [_session_path(platform), _meta_path(platform)]:
        if path.exists():
            path.unlink()
    logger.info(f"[session] Invalidated {platform} session")


def new_browser_with_session(platform: str, headless: bool = True):
    """
    Returns (pw, browser, context) with session loaded if available.
    Caller must still call save_session(platform, context) after login.
    """
    from utils.browser import new_browser as _new_browser
    session_file = load_session(platform) if session_is_valid(platform) else None

    pw, browser, context = _new_browser(headless=headless)

    if session_file:
        # Can't load storage state into existing context — recreate with state
        context.close()
        browser.close()
        try:
            browser2 = pw.chromium.launch(
                headless=headless,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            )
            context2 = browser2.new_context(
                storage_state=session_file,
                viewport={"width": 1280, "height": 800},
                locale="en-IN",
                timezone_id="Asia/Kolkata",
            )
            context2.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            logger.info(f"[session] Loaded {platform} session from disk")
            return pw, browser2, context2
        except Exception as e:
            logger.warning(f"[session] Failed to load {platform} state: {e} — using fresh session")
            invalidate_session(platform)
            browser2.close()
            # Fall through to fresh browser
            browser3 = pw.chromium.launch(
                headless=headless,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            )
            context3 = browser3.new_context(viewport={"width": 1280, "height": 800})
            return pw, browser3, context3

    return pw, browser, context
