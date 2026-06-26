"""
utils/shutdown.py — Global shutdown coordination.

A single threading.Event shared across all modules.
Any thread can check `is_shutdown()` and bail early.
`request_shutdown()` is called by the signal handler in main.py.

Usage:
    from utils.shutdown import is_shutdown, interruptible_sleep

    interruptible_sleep(60)        # Ctrl+C wakes this immediately
    if is_shutdown(): return       # check at loop boundaries
"""
import threading
import time

_shutdown_event = threading.Event()


def request_shutdown() -> None:
    """Signal all workers to stop. Safe to call from any thread."""
    _shutdown_event.set()


def is_shutdown() -> bool:
    """Return True if a shutdown has been requested."""
    return _shutdown_event.is_set()


def interruptible_sleep(seconds: float, granularity: float = 0.25) -> None:
    """
    Sleep for `seconds` but wake up immediately if shutdown is requested.
    Checks the shutdown event every `granularity` seconds.
    """
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if _shutdown_event.is_set():
            return
        remaining = deadline - time.monotonic()
        time.sleep(min(granularity, remaining))
