"""
CareerOS v2 — Main Orchestrator
Run locally:         python main.py
Dashboard:           python -m uvicorn dashboard.app:app --reload --port 8000
Weekly skill gaps:   python -c "from modules.skill_gap_engine import run; run()"
GitHub Actions runs this on schedule (9AM + 3PM IST).

Ctrl+C / SIGTERM safe:
  - Signal handler calls request_shutdown() immediately (prints message, no hang)
  - All worker threads, sleeps, and Gemini retries check is_shutdown() and exit cleanly
  - Browser sessions (Playwright) are closed in finally blocks inside each plugin
"""
import json
import os
import sys
import signal

from dotenv import load_dotenv
load_dotenv()

from utils.shutdown import request_shutdown, is_shutdown
from modules.profile_brain import load_profile, validate_profile
from modules.job_scout.scout import run_all_scrapers
from modules.duplicate_detector import deduplicate
from modules.notification_agent import send_morning_report
from utils.logger import setup_logger

logger = setup_logger()


# ─── Signal Handling ──────────────────────────────────────────────────────────

def _handle_signal(signum, frame):
    """Called on Ctrl+C (SIGINT) or SIGTERM. Triggers graceful shutdown."""
    sig_name = "SIGINT (Ctrl+C)" if signum == signal.SIGINT else "SIGTERM"
    print(f"\n\n⛔  {sig_name} received — shutting down gracefully...", flush=True)
    print("   (Workers will stop after their current job. Please wait a moment.)\n", flush=True)
    logger.warning(f"[main] {sig_name} received \u2014 requesting shutdown")
    request_shutdown()


# Register handlers (works on all platforms for SIGINT; SIGTERM on Unix only)
signal.signal(signal.SIGINT, _handle_signal)
try:
    signal.signal(signal.SIGTERM, _handle_signal)
except (OSError, AttributeError):
    pass  # SIGTERM not available on Windows in some environments


# ─── Settings ─────────────────────────────────────────────────────────────────

def load_settings() -> dict:
    with open(os.path.join("config", "settings.json"), encoding="utf-8") as f:
        return json.load(f)


# ─── Pipeline ─────────────────────────────────────────────────────────────────

def run_pipeline():
    logger.info("=== CareerOS v2 Pipeline Starting ===")
    settings = load_settings()

    from utils.checkpoint import (
        load_checkpoint, save_after_scrape, mark_complete,
        clear_checkpoint, checkpoint_summary,
    )

    # Step 1: Load + validate profile
    profile = load_profile()
    valid, errors = validate_profile(profile)
    if not valid:
        logger.error(f"Profile validation failed: {errors}")
        sys.exit(1)

    if is_shutdown():
        logger.info("[main] Shutdown before scraping — exiting")
        return {}

    # ── Check for an existing checkpoint (resume from crash) ──────────────────
    checkpoint = load_checkpoint()

    if checkpoint:
        # Resume: skip scraping, use pending jobs from checkpoint
        unique_jobs = checkpoint["pending_jobs"]
        logger.info(
            f"[main] RESUMING from checkpoint — {len(unique_jobs)} jobs remaining "
            f"(checkpoint: {checkpoint_summary()})"
        )
        print(f"\n♻️  Resuming from checkpoint: {len(unique_jobs)} jobs left to process\n", flush=True)
    else:
        # Fresh run: scrape → dedup → save checkpoint
        if is_shutdown():
            logger.info("[main] Shutdown before scraping — exiting")
            return {}

        # Step 2: Scrape jobs from all sources
        logger.info("Scraping jobs...")
        raw_jobs = run_all_scrapers(profile, settings)
        logger.info(f"Raw: {len(raw_jobs)} jobs")

        if is_shutdown():
            logger.info("[main] Shutdown after scraping — exiting")
            return {}

        # Step 3: Deduplicate
        unique_jobs = deduplicate(raw_jobs)
        logger.info(f"Unique: {len(unique_jobs)} jobs after dedup")

        if is_shutdown():
            logger.info("[main] Shutdown after dedup — exiting")
            return {}

        # ── Save checkpoint immediately after scraping ─────────────────────────
        # This means if Gemini analysis crashes, next run skips scraping entirely
        save_after_scrape(unique_jobs)

    # Step 4: Run queue-based parallel pipeline (analyze + apply)
    from core.pipeline import CareerPipeline
    pipeline = CareerPipeline(profile=profile, settings=settings)
    stats = pipeline.run(raw_jobs=unique_jobs)

    if is_shutdown():
        logger.warning(f"[main] Pipeline interrupted early. Partial stats: {stats}")
        print(f"\n⚠️  Interrupted. Partial results: {stats}", flush=True)
        print("   Next run will resume from where it left off (checkpoint saved).\n", flush=True)
        return stats

    # Step 5: Success — mark checkpoint complete (clears it) + send Telegram report
    mark_complete(stats)
    send_morning_report(stats)
    logger.info(f"=== Pipeline Complete: {stats} ===")
    return stats


if __name__ == "__main__":
    try:
        run_pipeline()
    except KeyboardInterrupt:
        # Fallback: in case signal handler wasn't called fast enough
        print("\n\n⛔  Interrupted — exiting.", flush=True)
        request_shutdown()
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as e:
        logger.exception(f"[main] Fatal error: {e}")
        sys.exit(1)
