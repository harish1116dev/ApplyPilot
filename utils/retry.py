"""
utils/retry.py — Retry decorator for plugin calls and any fallible operation.

Usage:
    @retry(attempts=3, delay=5, backoff=2, fallback="human_needed")
    def apply(...): ...

    # Or call directly:
    result = with_retry(fn, args, kwargs, attempts=3)
"""
import time
import functools
import traceback
from utils.logger import setup_logger

logger = setup_logger("retry")


def retry(attempts: int = 3, delay: float = 5.0, backoff: float = 2.0, fallback=None):
    """
    Decorator: retries `attempts` times with exponential backoff.
    If all attempts fail, returns `fallback` (if set) or re-raises.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            wait = delay
            last_exc = None
            for attempt in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    tb = traceback.format_exc()
                    logger.warning(
                        f"[retry] {fn.__name__} attempt {attempt}/{attempts} failed: {e}\n"
                        f"Waiting {wait:.0f}s before retry..."
                    )
                    if attempt < attempts:
                        time.sleep(wait)
                        wait *= backoff
            # All attempts exhausted
            logger.error(f"[retry] {fn.__name__} failed after {attempts} attempts. Last: {last_exc}")
            if fallback is not None:
                return fallback
            raise last_exc
        return wrapper
    return decorator


def with_retry(fn, args=(), kwargs=None, attempts=3, delay=5.0, backoff=2.0, fallback=None):
    """Imperative version — wrap any callable without decorating it."""
    if kwargs is None:
        kwargs = {}
    decorated = retry(attempts=attempts, delay=delay, backoff=backoff, fallback=fallback)(fn)
    return decorated(*args, **kwargs)


def plugin_retry(fn):
    """
    Convenience decorator for plugins:
    3 attempts, 5s → 10s → 20s, returns 'human_needed' on total failure.
    """
    return retry(attempts=3, delay=5, backoff=2, fallback="human_needed")(fn)
