"""
utils/gemini_client.py — Gemini API client with multi-key rotation.

Supports up to 3 API keys loaded from env:
  GEMINI_API_KEY      — key 1 (primary)
  GEMINI_API_KEY_2    — key 2 (fallback when key 1 hits daily limit)
  GEMINI_API_KEY_3    — key 3 (fallback when key 2 hits daily limit)

Key rotation strategy:
  - Each key tracks its own daily call count and per-minute rate.
  - When a key hits its RPD limit (500/day), it is marked exhausted and
    the next key takes over automatically.
  - When all keys are exhausted, raises RuntimeError.
  - 429 / resource-exhausted errors on a specific key also trigger rotation
    to the next key (don't waste backoff time — just switch).
  - Daily counters reset at midnight UTC independently per key.

Model priority per key:
  Primary:  gemini-3.1-flash-lite  (15 RPM, 500 RPD free tier)
  Fallback: gemini-2.5-flash-lite  (10 RPM,  20 RPD free tier)
  The fallback model is tried only when the primary model is unavailable
  (404 / model-not-found), NOT for rate-limit errors (we rotate keys instead).

Rate limits enforced:
  - 12 RPM effective per key (safety buffer below 15 RPM hard limit)
  - 500 RPD per key — counter auto-resets at midnight UTC
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

# ─── Models ───────────────────────────────────────────────────────────────────
_PRIMARY_MODEL = "gemini-3.1-flash-lite"
_FALLBACK_MODEL = "gemini-2.5-flash-lite"

# ─── Rate limit constants ─────────────────────────────────────────────────────
_RPM_LIMIT    = 12       # effective RPM per key (buffer below 15 hard limit)
_RPD_LIMIT    = 500      # requests per day per key (free tier)
_MIN_INTERVAL = 60.0 / _RPM_LIMIT   # seconds between calls on same key


# ─── Per-Key State ────────────────────────────────────────────────────────────

class _KeySlot:
    """Holds state for a single API key."""
    def __init__(self, index: int, api_key: str):
        self.index      = index           # 1-based (for log messages)
        self.api_key    = api_key
        self.client     = None            # lazy-init genai.Client
        self.daily_count: int  = 0
        self.reset_date: str   = ""
        self.last_call: float  = 0.0
        self.exhausted: bool   = False    # True once RPD limit reached

    def get_client(self) -> genai.Client:
        if self.client is None:
            self.client = genai.Client(api_key=self.api_key)
        return self.client

    def check_reset(self, today: str) -> None:
        if self.reset_date != today:
            self.daily_count = 0
            self.reset_date  = today
            self.exhausted   = False
            logger.info(f"[gemini] Key {self.index}: daily counter reset for {today}")

    def is_daily_exhausted(self) -> bool:
        return self.daily_count >= _RPD_LIMIT

    def enforce_rpm(self) -> None:
        """Block until the per-minute gap has elapsed for this key."""
        elapsed = time.time() - self.last_call
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)

    def __repr__(self) -> str:
        return (
            f"<Key {self.index} "
            f"calls={self.daily_count}/{_RPD_LIMIT} "
            f"exhausted={self.exhausted}>"
        )


# ─── Key Pool ─────────────────────────────────────────────────────────────────

def _load_keys() -> list[_KeySlot]:
    """Load all configured API keys from environment variables."""
    raw_keys = []
    for env_var in ("GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"):
        val = os.getenv(env_var, "").strip()
        if val:
            raw_keys.append(val)

    if not raw_keys:
        raise EnvironmentError(
            "No Gemini API keys found. Set GEMINI_API_KEY (and optionally "
            "GEMINI_API_KEY_2, GEMINI_API_KEY_3) in your .env file."
        )

    slots = [_KeySlot(i + 1, key) for i, key in enumerate(raw_keys)]
    logger.info(f"[gemini] Loaded {len(slots)} API key(s)")
    return slots


# Module-level state — initialized lazily on first call
_lock: threading.Lock = threading.Lock()
_keys: list[_KeySlot] = []
_active_key_idx: int = 0    # index into _keys list


def _get_keys() -> list[_KeySlot]:
    global _keys
    if not _keys:
        _keys = _load_keys()
    return _keys


def _active_key() -> _KeySlot:
    return _get_keys()[_active_key_idx]


def _rotate_key() -> _KeySlot | None:
    """
    Try to advance to the next non-exhausted key.
    Returns the new active key, or None if all keys are exhausted.
    """
    global _active_key_idx
    keys = _get_keys()
    for offset in range(1, len(keys)):
        candidate_idx = (_active_key_idx + offset) % len(keys)
        candidate = keys[candidate_idx]
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        candidate.check_reset(today)
        if not candidate.is_daily_exhausted():
            _active_key_idx = candidate_idx
            logger.warning(
                f"[gemini] Rotated to Key {candidate.index} "
                f"(calls={candidate.daily_count}/{_RPD_LIMIT})"
            )
            return candidate
    return None   # all exhausted


# ─── Public API ───────────────────────────────────────────────────────────────

def call_gemini(prompt: str, retries: int = 4) -> str:
    """
    Call Gemini with multi-key rotation + RPM enforcement + retry logic.
    Thread-safe: only one call goes to the API at a time.

    Key rotation triggers:
      - Key hits RPD limit (500/day) → switch to next key immediately
      - 429 / resource-exhausted error → mark key exhausted, switch key

    Model fallback (within a key):
      - 404 / model-unavailable → try _FALLBACK_MODEL on same key
    """
    global _active_key_idx

    current_model = _PRIMARY_MODEL

    for attempt in range(retries):
        with _lock:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            keys  = _get_keys()

            # Reset daily counters if it's a new day
            for slot in keys:
                slot.check_reset(today)

            key = keys[_active_key_idx]

            # If active key is exhausted, rotate immediately before trying
            if key.is_daily_exhausted():
                key.exhausted = True
                logger.warning(
                    f"[gemini] Key {key.index} exhausted "
                    f"({key.daily_count}/{_RPD_LIMIT} RPD). Rotating..."
                )
                key = _rotate_key()
                if key is None:
                    raise RuntimeError(
                        f"All {len(keys)} Gemini API key(s) have hit their "
                        f"{_RPD_LIMIT} RPD daily limit. "
                        "Run will resume tomorrow at midnight UTC."
                    )

            # Enforce per-minute gap for the active key
            key.enforce_rpm()

            client = key.get_client()
            try:
                response = client.models.generate_content(
                    model=current_model,
                    contents=prompt,
                )
                key.last_call    = time.time()
                key.daily_count += 1
                text = response.text or ""
                logger.debug(
                    f"[gemini] Key {key.index} / {current_model} "
                    f"-> {len(text)} chars "
                    f"(today: {key.daily_count}/{_RPD_LIMIT})"
                )
                return text

            except Exception as e:
                err_str = str(e)
                key.last_call = time.time()

                # ── Rate limited / quota exhausted ───────────────────────
                if (
                    "429" in err_str
                    or "quota" in err_str.lower()
                    or "resource exhausted" in err_str.lower()
                ):
                    logger.warning(
                        f"[gemini] Key {key.index} rate-limited / quota hit "
                        f"(attempt {attempt + 1}/{retries}). Rotating key..."
                    )
                    key.exhausted   = True
                    key.daily_count = _RPD_LIMIT  # mark as full so rotation skips it
                    rotated = _rotate_key()
                    if rotated is None:
                        raise RuntimeError(
                            f"All {len(keys)} Gemini API key(s) are rate-limited. "
                            "Wait until midnight UTC or add more keys."
                        )
                    # Don't sleep — just retry immediately with the new key
                    continue

                # ── Model unavailable — try fallback model on same key ───
                elif (
                    "404" in err_str
                    or "not found" in err_str.lower()
                    or "invalid" in err_str.lower()
                    or "unavailable" in err_str.lower()
                ):
                    if current_model != _FALLBACK_MODEL:
                        logger.warning(
                            f"[gemini] Key {key.index}: {current_model} unavailable. "
                            f"Switching to {_FALLBACK_MODEL}."
                        )
                        current_model = _FALLBACK_MODEL
                    else:
                        logger.error(
                            f"[gemini] Key {key.index}: fallback model also failed. "
                            f"Error: {err_str[:200]}"
                        )
                        raise RuntimeError(
                            f"Both Gemini models unavailable on Key {key.index}: {err_str}"
                        ) from e

                # ── Other transient error — exponential backoff ──────────
                else:
                    logger.error(
                        f"[gemini] Key {key.index}: unexpected error "
                        f"(attempt {attempt + 1}/{retries}): {e}"
                    )
                    if attempt == retries - 1:
                        raise
                    wait = 5 * (attempt + 1)
                    interruptible_sleep(wait)
                    if is_shutdown():
                        raise RuntimeError("Shutdown requested — aborting Gemini call")

    raise RuntimeError(f"Gemini API failed after {retries} retries across all keys")


def call_gemini_json(prompt: str) -> dict:
    """
    Call Gemini and robustly parse a JSON response.
    Handles: raw JSON, ```json ... ```, ``` ... ``` fences, JSON embedded in text.
    """
    raw   = call_gemini(prompt)
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
    """Return current Gemini usage stats for all keys (thread-safe snapshot)."""
    with _lock:
        keys = _get_keys()
        key_stats = []
        for slot in keys:
            key_stats.append({
                "key":        slot.index,
                "calls":      slot.daily_count,
                "limit":      _RPD_LIMIT,
                "remaining":  max(0, _RPD_LIMIT - slot.daily_count),
                "exhausted":  slot.exhausted,
            })
        active = keys[_active_key_idx]
        return {
            "active_key":     active.index,
            "total_keys":     len(keys),
            "keys":           key_stats,
            "rpm_limit":      _RPM_LIMIT,
            "model":          _PRIMARY_MODEL,
            "fallback_model": _FALLBACK_MODEL,
        }
