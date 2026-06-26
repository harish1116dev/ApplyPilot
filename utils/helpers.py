"""Shared utility helpers."""
import re
import random
from datetime import datetime
from utils.shutdown import interruptible_sleep, is_shutdown


def random_delay(min_s: float = 2.0, max_s: float = 5.0) -> None:
    """Sleep a random amount — wakes immediately on Ctrl+C."""
    interruptible_sleep(random.uniform(min_s, max_s))


def normalize_text(text: str) -> str:
    """Lowercase + strip extra whitespace."""
    return re.sub(r"\s+", " ", text.lower().strip()) if text else ""


def safe_get(d: dict, *keys, default=None):
    """Safe nested dict access."""
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key, default)
        else:
            return default
    return d


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def chunk_list(lst: list, size: int) -> list:
    """Split a list into chunks of given size."""
    return [lst[i : i + size] for i in range(0, len(lst), size)]


RANDOM_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
]


def random_user_agent() -> str:
    return random.choice(RANDOM_USER_AGENTS)
