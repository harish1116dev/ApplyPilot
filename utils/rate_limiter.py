"""
utils/rate_limiter.py — Human-like application pacing.

Instead of 100 applications in 1 minute (bot behaviour),
enforces randomized gaps: 2–11 minutes between applications per platform.

Ctrl+C safe: all sleeps go through interruptible_sleep().
"""
import random
import threading
from utils.logger import setup_logger
from utils.shutdown import interruptible_sleep, is_shutdown

logger = setup_logger("rate_limiter")

# Platform-specific application limits (per session)
PLATFORM_LIMITS = {
    "linkedin":   {"max_per_hour": 8,  "min_gap_s": 120, "max_gap_s": 660},
    "naukri":     {"max_per_hour": 12, "min_gap_s": 90,  "max_gap_s": 420},
    "indeed":     {"max_per_hour": 10, "min_gap_s": 90,  "max_gap_s": 480},
    "lever":      {"max_per_hour": 15, "min_gap_s": 60,  "max_gap_s": 300},
    "greenhouse": {"max_per_hour": 15, "min_gap_s": 60,  "max_gap_s": 300},
    "email":      {"max_per_hour": 20, "min_gap_s": 30,  "max_gap_s": 180},
    "default":    {"max_per_hour": 10, "min_gap_s": 120, "max_gap_s": 660},
}

import time


class RateLimiter:
    def __init__(self):
        self._lock = threading.Lock()
        self._history: dict[str, list[float]] = {}

    def _get_config(self, platform: str) -> dict:
        return PLATFORM_LIMITS.get(platform, PLATFORM_LIMITS["default"])

    def wait(self, platform: str) -> None:
        """
        Block until it's safe to make another application on this platform.
        Returns early if shutdown is requested (Ctrl+C).
        """
        if is_shutdown():
            return

        cfg = self._get_config(platform)

        with self._lock:
            now = time.time()
            history = self._history.get(platform, [])
            history = [t for t in history if now - t < 3600]
            self._history[platform] = history

            # Enforce per-hour limit
            if len(history) >= cfg["max_per_hour"]:
                oldest = history[0]
                wait_until = oldest + 3600
                wait_s = max(0, wait_until - now)
                if wait_s > 0:
                    logger.warning(
                        f"[rate_limiter] {platform}: hourly limit reached. "
                        f"Waiting {wait_s:.0f}s"
                    )
                    # Release lock before long sleep
                    self._lock.release()
                    try:
                        interruptible_sleep(wait_s)
                    finally:
                        self._lock.acquire()

            if is_shutdown():
                return

            # Enforce minimum gap from last application
            if history:
                now = time.time()
                since_last = now - history[-1]
                min_gap = cfg["min_gap_s"]
                if since_last < min_gap:
                    gap = min_gap - since_last
                    self._lock.release()
                    try:
                        interruptible_sleep(gap)
                    finally:
                        self._lock.acquire()

        if is_shutdown():
            return

        # Human-like random gap (outside the lock so other platforms aren't blocked)
        gap = random.uniform(cfg["min_gap_s"], cfg["max_gap_s"])
        logger.debug(f"[rate_limiter] {platform}: waiting {gap:.0f}s before next application")
        interruptible_sleep(gap)

        with self._lock:
            self._history.setdefault(platform, []).append(time.time())

    def record(self, platform: str) -> None:
        """Record an application without waiting (for post-hoc tracking)."""
        with self._lock:
            self._history.setdefault(platform, []).append(time.time())

    def get_stats(self) -> dict:
        now = time.time()
        return {
            p: len([t for t in ts if now - t < 3600])
            for p, ts in self._history.items()
        }


# Global singleton
_limiter = RateLimiter()


def wait_before_apply(platform: str) -> None:
    _limiter.wait(platform)


def record_application(platform: str) -> None:
    _limiter.record(platform)


def get_rate_stats() -> dict:
    return _limiter.get_stats()
