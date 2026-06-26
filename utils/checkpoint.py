"""
utils/checkpoint.py — Scrape-once, resume-anywhere pipeline checkpoint.

Problem it solves:
  Scraping 150+ jobs takes ~10 minutes. Gemini analysis takes another ~15 min.
  If the process crashes or is Ctrl+C'd mid-analysis, all scraping work is lost
  and you have to start over from scratch.

How it works:
  1. After scraping → save all raw jobs to sessions/checkpoint.json
  2. If checkpoint exists on next run → skip scraping, load from checkpoint
  3. Track which jobs are pending / done in the same file
  4. On successful pipeline completion → delete the checkpoint (clean slate)
  5. Checkpoint expires after 12 hours (jobs go stale)

File location: sessions/checkpoint.json  (gitignored)
"""
import json
import os
import time
from datetime import datetime, timezone
from utils.logger import setup_logger

logger = setup_logger("checkpoint")

_CHECKPOINT_FILE = os.path.join("sessions", "checkpoint.json")
_CHECKPOINT_TTL_HOURS = 12   # discard if older than this


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _checkpoint_exists() -> bool:
    return os.path.isfile(_CHECKPOINT_FILE)


def _load_raw() -> dict | None:
    try:
        with open(_CHECKPOINT_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[checkpoint] Could not read checkpoint: {e}")
        return None


def _save_raw(data: dict) -> None:
    os.makedirs(os.path.dirname(_CHECKPOINT_FILE), exist_ok=True)
    with open(_CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── Public API ───────────────────────────────────────────────────────────────

def load_checkpoint() -> dict | None:
    """
    Load existing checkpoint if valid (not expired, not complete).
    Returns the checkpoint dict or None if no valid checkpoint found.
    """
    if not _checkpoint_exists():
        return None

    data = _load_raw()
    if not data:
        return None

    # Check expiry
    created_at = data.get("created_at", "")
    try:
        created = datetime.fromisoformat(created_at)
        age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
        if age_hours > _CHECKPOINT_TTL_HOURS:
            logger.info(f"[checkpoint] Checkpoint expired ({age_hours:.1f}h old) — starting fresh")
            clear_checkpoint()
            return None
    except Exception:
        pass

    # Check if already complete
    if data.get("completed", False):
        logger.info("[checkpoint] Previous run completed successfully — starting fresh")
        clear_checkpoint()
        return None

    pending = data.get("pending_jobs", [])
    total = data.get("total_jobs", 0)
    done = total - len(pending)
    logger.info(
        f"[checkpoint] Resuming: {done}/{total} jobs already processed, "
        f"{len(pending)} remaining"
    )
    return data


def save_after_scrape(raw_jobs: list[dict]) -> None:
    """
    Save scraped jobs immediately after scraping completes.
    Call this BEFORE starting analysis so a crash during analysis
    won't lose the scraping work.
    """
    data = {
        "created_at": _now_iso(),
        "completed": False,
        "total_jobs": len(raw_jobs),
        "pending_jobs": raw_jobs,    # all jobs are pending initially
        "done_jobs": [],             # grows as analysis completes
        "stats": {
            "found": len(raw_jobs),
            "applied": 0,
            "manual": 0,
            "skipped": 0,
            "failed": 0,
        },
    }
    _save_raw(data)
    logger.info(f"[checkpoint] Saved {len(raw_jobs)} scraped jobs to {_CHECKPOINT_FILE}")


def mark_job_done(job_data: dict, status: str) -> None:
    """
    Record a completed job. Called after each job finishes analysis+apply.
    Thread-safe via file reload+save pattern (pipeline is single-threaded for analysis).
    """
    data = _load_raw()
    if not data:
        return

    # Move job from pending → done
    job_url = job_data.get("apply_url", "")
    job_title = job_data.get("title", "")

    pending = data.get("pending_jobs", [])
    # Remove by URL match (most reliable unique key)
    new_pending = [
        j for j in pending
        if j.get("apply_url", "") != job_url or j.get("title", "") != job_title
    ]
    data["pending_jobs"] = new_pending
    data["done_jobs"].append({"title": job_title, "status": status, "apply_url": job_url})

    # Update stats
    stats = data.get("stats", {})
    if status in stats:
        stats[status] = stats.get(status, 0) + 1
    data["stats"] = stats
    data["updated_at"] = _now_iso()

    _save_raw(data)


def get_pending_jobs() -> list[dict]:
    """Get list of jobs not yet processed (resume point)."""
    data = _load_raw()
    if not data:
        return []
    return data.get("pending_jobs", [])


def get_checkpoint_stats() -> dict:
    """Get current stats from checkpoint."""
    data = _load_raw()
    if not data:
        return {}
    return data.get("stats", {})


def mark_complete(final_stats: dict) -> None:
    """
    Mark pipeline as successfully completed. Call at end of a successful run.
    This flags the checkpoint so next run starts fresh.
    """
    data = _load_raw()
    if data:
        data["completed"] = True
        data["completed_at"] = _now_iso()
        data["stats"] = final_stats
        _save_raw(data)
    logger.info(f"[checkpoint] Pipeline completed. Stats: {final_stats}")
    # Clean up immediately
    clear_checkpoint()


def clear_checkpoint() -> None:
    """Delete the checkpoint file. Called on successful completion or expiry."""
    try:
        if _checkpoint_exists():
            os.remove(_CHECKPOINT_FILE)
            logger.info("[checkpoint] Checkpoint cleared")
    except Exception as e:
        logger.warning(f"[checkpoint] Could not clear checkpoint: {e}")


def checkpoint_summary() -> str:
    """Return a human-readable summary of checkpoint state."""
    if not _checkpoint_exists():
        return "No checkpoint (fresh run)"
    data = _load_raw()
    if not data:
        return "Checkpoint unreadable"
    total = data.get("total_jobs", 0)
    pending = len(data.get("pending_jobs", []))
    done = total - pending
    created = data.get("created_at", "?")
    return f"Checkpoint: {done}/{total} done, {pending} pending (from {created})"
