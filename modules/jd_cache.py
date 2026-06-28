"""
modules/jd_cache.py — Disk-based Job Description Cache.

Caches full JD text + Gemini verdicts to disk, keyed by a SHA-256 hash of
the apply URL.  Prevents:
  - Re-downloading the same JD on subsequent runs
  - Re-running Gemini on a JD we've already analyzed
  - Duplicate applications

Cache layout:
    sessions/jd_cache/
        <sha256_of_url>.json
            {
                "url":           "<original url>",
                "url_hash":      "<sha256>",
                "raw_jd":        "<full jd text>",
                "jd_hash":       "<sha256 of raw_jd>",
                "fetched_at":    "<iso8601>",
                "gemini_verdict": { ... } | null,
                "verdict_at":    "<iso8601>" | null,
                "applied":       false,
                "applied_at":    null
            }

All public functions are thread-safe (module-level lock).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional

from utils.logger import setup_logger

logger = setup_logger("jd_cache")

_CACHE_DIR = os.path.join("sessions", "jd_cache")
_DEFAULT_MAX_AGE_DAYS = 7
_lock = threading.Lock()


# ─── Internal Helpers ─────────────────────────────────────────────────────────

def _url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode()).hexdigest()


def _jd_hash(raw_jd: str) -> str:
    return hashlib.sha256(raw_jd.encode()).hexdigest()


def _cache_path(url_hash: str) -> str:
    return os.path.join(_CACHE_DIR, f"{url_hash}.json")


def _ensure_dir() -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)


def _load_entry(url_hash: str) -> Optional[dict]:
    path = _cache_path(url_hash)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[jd_cache] Failed to read cache file {path}: {e}")
        return None


def _save_entry(entry: dict) -> None:
    _ensure_dir()
    path = _cache_path(entry["url_hash"])
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"[jd_cache] Failed to write cache file {path}: {e}")


def _is_stale(entry: dict, max_age_days: int) -> bool:
    fetched_at = entry.get("fetched_at")
    if not fetched_at:
        return True
    try:
        ts = datetime.fromisoformat(fetched_at)
        age = datetime.now(timezone.utc) - ts
        return age > timedelta(days=max_age_days)
    except Exception:
        return True


# ─── Public API ───────────────────────────────────────────────────────────────

def get_cached_jd(url: str, max_age_days: int = _DEFAULT_MAX_AGE_DAYS) -> Optional[dict]:
    """
    Check if we have a cached JD for this URL.

    Returns the full cache entry dict if found AND not stale, else None.
    Entry contains: raw_jd, gemini_verdict (may be None), applied, etc.
    """
    if not url:
        return None
    with _lock:
        h = _url_hash(url)
        entry = _load_entry(h)
        if entry is None:
            logger.debug(f"[jd_cache] MISS: {url[:80]}")
            return None
        if _is_stale(entry, max_age_days):
            logger.debug(f"[jd_cache] STALE (>{max_age_days}d): {url[:80]}")
            return None
        logger.debug(
            f"[jd_cache] HIT: {url[:80]}"
            + (" (has verdict)" if entry.get("gemini_verdict") else " (no verdict yet)")
        )
        return entry


def save_jd(url: str, raw_jd: str) -> None:
    """
    Persist the raw JD text for a URL.  Creates a new entry or updates
    existing raw_jd + jd_hash (preserving any existing verdict).
    """
    if not url or not raw_jd:
        return
    with _lock:
        h = _url_hash(url)
        existing = _load_entry(h) or {}
        existing.update({
            "url": url,
            "url_hash": h,
            "raw_jd": raw_jd,
            "jd_hash": _jd_hash(raw_jd),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
        _save_entry(existing)
        logger.debug(f"[jd_cache] Saved JD ({len(raw_jd)} chars): {url[:80]}")


def save_gemini_verdict(url: str, verdict: dict) -> None:
    """
    Attach the Gemini analysis result to an existing cache entry.
    If no entry exists yet, creates one (without raw_jd).
    """
    if not url or not verdict:
        return
    with _lock:
        h = _url_hash(url)
        existing = _load_entry(h) or {
            "url": url,
            "url_hash": h,
            "raw_jd": "",
            "jd_hash": "",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        existing["gemini_verdict"] = verdict
        existing["verdict_at"] = datetime.now(timezone.utc).isoformat()
        existing.setdefault("applied", False)
        existing.setdefault("applied_at", None)
        _save_entry(existing)
        logger.debug(f"[jd_cache] Saved Gemini verdict: {url[:80]}")


def mark_applied(url: str) -> None:
    """Mark a cached job as applied (prevents duplicate applications)."""
    if not url:
        return
    with _lock:
        h = _url_hash(url)
        existing = _load_entry(h)
        if existing:
            existing["applied"] = True
            existing["applied_at"] = datetime.now(timezone.utc).isoformat()
            _save_entry(existing)
            logger.debug(f"[jd_cache] Marked as applied: {url[:80]}")


def is_applied(url: str) -> bool:
    """Return True if this URL was already applied to (per cache)."""
    if not url:
        return False
    with _lock:
        h = _url_hash(url)
        entry = _load_entry(h)
        return bool(entry and entry.get("applied"))


def get_cache_stats() -> dict:
    """Return a summary of the cache state (file count, applied count, etc.)."""
    _ensure_dir()
    files = [f for f in os.listdir(_CACHE_DIR) if f.endswith(".json")]
    applied = 0
    with_verdict = 0
    for fname in files:
        path = os.path.join(_CACHE_DIR, fname)
        try:
            with open(path, encoding="utf-8") as f:
                e = json.load(f)
            if e.get("applied"):
                applied += 1
            if e.get("gemini_verdict"):
                with_verdict += 1
        except Exception:
            pass
    return {
        "cached_jobs": len(files),
        "with_gemini_verdict": with_verdict,
        "already_applied": applied,
        "cache_dir": _CACHE_DIR,
    }
