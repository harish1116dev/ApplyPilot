"""
utils/gemini_client.py — Gemini API client using google-genai (new SDK).

Model:    gemini-3.1-flash-lite  (15 RPM, 250K TPM, 500 RPD) — primary
Fallback: gemini-2.5-flash-lite  (10 RPM, 250K TPM,  20 RPD) — only used if primary fails

Why gemini-3.1-flash-lite as primary?
  With 100-200 jobs per run, we need 100-200 RPD (1 call per job).
  gemini-2.5-flash-lite has only 20 RPD — exhausted after 20 jobs.
  gemini-3.1-flash-lite has 500 RPD — handles a full run comfortably.

Rate limits enforced:
- 12 RPM effective (safety buffer below 15 RPM limit)
- 500 RPD — daily counter auto-resets at midnight UTC
"""
from google import genai
import threading
import time
import json
import os
import re
from datetime import datetime, timezone
from utils.logger import setup_logger
from utils.shutdown import interruptible_sleep, is_shutdown

logger = setup_logger("gemini_client")

_API_KEY = os.getenv("GEMINI_API_KEY")

# Lazy-init: only create client when first needed so import doesn't fail without env vars
_client: genai.Client = None

# Model names — gemini-3.1-flash-lite is primary (500 RPD vs 20 RPD for 2.5-flash-lite)
_PRIMARY_MODEL = "gemini-3.1-flash-lite"
_FALLBACK_MODEL = "gemini-2.5-flash-lite"

# Rate limits (gemini-3.1-flash-lite free tier: 15 RPM, 500 RPD)
_RPM_LIMIT = 12          # 12 effective (safety buffer below 15 RPM limit)
_RPD_LIMIT = 500         # 500 per day
_MIN_INTERVAL = 60.0 / _RPM_LIMIT  # 5.0 seconds between calls

# Thread-safe state
_lock = threading.Lock()
_last_call_time: float = 0.0
_daily_count: int = 0
_daily_reset_date: str = ""


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY not set in environment / .env")
        _client = genai.Client(api_key=api_key)
    return _client


def _check_reset_daily(today: str) -> None:
    """Reset RPD counter if we're on a new day."""
    global _daily_count, _daily_reset_date
    if _daily_reset_date != today:
        _daily_count = 0
        _daily_reset_date = today
        logger.info(f"[gemini] Daily counter reset for {today}")


def call_gemini(prompt: str, retries: int = 4) -> str:
    """
    Call Gemini with full rate-limit enforcement and retry/fallback logic.
    Thread-safe: only one call goes to the API at a time.
    """
    global _last_call_time, _daily_count

    current_model = _PRIMARY_MODEL

    for attempt in range(retries):
        with _lock:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            _check_reset_daily(today)

            if _daily_count >= _RPD_LIMIT:
                logger.error(
                    f"[gemini] Daily limit of {_RPD_LIMIT} RPD reached. "
                    "Calls will resume tomorrow."
                )
                raise RuntimeError(
                    f"Gemini daily limit ({_RPD_LIMIT} RPD) reached. "
                    "Upgrade plan or wait until midnight UTC."
                )

            # Enforce RPM gap
            elapsed = time.time() - _last_call_time
            if elapsed < _MIN_INTERVAL:
                time.sleep(_MIN_INTERVAL - elapsed)

            client = _get_client()
            try:
                response = client.models.generate_content(
                    model=current_model,
                    contents=prompt,
                )
                _last_call_time = time.time()
                _daily_count += 1
                text = response.text or ""
                logger.debug(
                    f"[gemini] {current_model} → {len(text)} chars "
                    f"(today: {_daily_count}/{_RPD_LIMIT})"
                )
                return text

            except Exception as e:
                err_str = str(e)
                _last_call_time = time.time()

                if "429" in err_str or "quota" in err_str.lower() or "resource exhausted" in err_str.lower():
                    # Exponential backoff: 10s, 20s, 40s, cap 120s
                    wait = min((2 ** attempt) * 10, 120)
                    logger.warning(
                        f"[gemini] Rate limited on {current_model}. "
                        f"Backing off {wait}s (attempt {attempt + 1}/{retries})"
                    )
                    # Block other threads during the backoff but wake on Ctrl+C
                    _last_call_time = time.time() + wait
                    interruptible_sleep(wait)
                    if is_shutdown():
                        raise RuntimeError("Shutdown requested — aborting Gemini call")

                elif (
                    "404" in err_str
                    or "not found" in err_str.lower()
                    or "invalid" in err_str.lower()
                    or "unavailable" in err_str.lower()
                ):
                    # Model not available — switch to fallback immediately
                    if current_model != _FALLBACK_MODEL:
                        logger.warning(
                            f"[gemini] {current_model} unavailable ({err_str[:120]}). "
                            f"Switching to {_FALLBACK_MODEL}."
                        )
                        current_model = _FALLBACK_MODEL
                    else:
                        logger.error(f"[gemini] Fallback model also failed: {err_str[:200]}")
                        raise RuntimeError(f"Both Gemini models unavailable: {err_str}") from e

                else:
                    logger.error(f"[gemini] Unexpected error (attempt {attempt + 1}/{retries}): {e}")
                    if attempt == retries - 1:
                        raise
                    interruptible_sleep(5 * (attempt + 1))
                    if is_shutdown():
                        raise RuntimeError("Shutdown requested — aborting Gemini call")

    raise RuntimeError(f"Gemini API failed after {retries} retries")


def call_gemini_json(prompt: str) -> dict:
    """
    Call Gemini and robustly parse a JSON response.
    Handles: raw JSON, ```json ... ```, ``` ... ``` fences, JSON embedded in text.
    """
    raw = call_gemini(prompt)
    clean = raw.strip()

    # Strip ```json ... ``` or ``` ... ``` fences
    fence = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", clean, re.DOTALL)
    if fence:
        clean = fence.group(1).strip()

    # Direct parse
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass

    # Extract first JSON object or array from mixed text
    for pattern in (r"\{.*\}", r"\[.*\]"):
        m = re.search(pattern, clean, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                continue

    logger.error(f"[gemini] JSON parse failed. Raw (first 400 chars): {clean[:400]}")
    raise ValueError(f"Gemini response is not valid JSON: {clean[:200]}")


def get_daily_usage() -> dict:
    """Return current Gemini usage stats (thread-safe snapshot)."""
    with _lock:
        return {
            "daily_calls": _daily_count,
            "daily_limit": _RPD_LIMIT,
            "remaining_today": max(0, _RPD_LIMIT - _daily_count),
            "rpm_limit": _RPM_LIMIT,
            "model": _PRIMARY_MODEL,
            "fallback": _FALLBACK_MODEL,
            "reset_date": _daily_reset_date,
        }
