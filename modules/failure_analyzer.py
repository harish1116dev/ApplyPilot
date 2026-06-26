"""
modules/failure_analyzer.py — Captures full failure context for easy debugging.

On any plugin failure, stores:
- Company + role + URL
- Stage where it failed
- Exception + full traceback
- Screenshot (PNG)
- HTML snapshot
- Timestamp

All queryable from the dashboard.
"""
import os
import traceback as tb_module
from datetime import datetime
from models.job import Job
from db.supabase_client import get_client
from utils.logger import setup_logger

logger = setup_logger("failure_analyzer")

FAILURES_DIR = os.path.join("logs", "failures")
os.makedirs(FAILURES_DIR, exist_ok=True)


def capture_failure(
    job: Job,
    stage: str,
    error: Exception,
    page=None,            # Playwright page object (optional)
    extra: dict = None,
) -> str:
    """
    Captures a failure with full context.
    Returns failure_id (saved to Supabase).
    """
    error_str = str(error)
    traceback_str = tb_module.format_exc()
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_company = "".join(c for c in job.company if c.isalnum() or c in "-_")[:30]
    base_name = f"{safe_company}_{stage}_{ts}"

    screenshot_path = ""
    html_path = ""

    # Try to capture screenshot and HTML
    if page is not None:
        try:
            screenshot_path = os.path.join(FAILURES_DIR, f"{base_name}.png")
            page.screenshot(path=screenshot_path, full_page=True)
            logger.debug(f"[failure] Screenshot saved: {screenshot_path}")
        except Exception as se:
            logger.warning(f"[failure] Screenshot failed: {se}")

        try:
            html_path = os.path.join(FAILURES_DIR, f"{base_name}.html")
            html = page.content()
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            logger.debug(f"[failure] HTML snapshot saved: {html_path}")
        except Exception as he:
            logger.warning(f"[failure] HTML snapshot failed: {he}")

    # Record on Job Object
    job.log_failure(
        stage=stage,
        error=error_str,
        traceback=traceback_str,
        screenshot_path=screenshot_path,
        html_snapshot_path=html_path,
    )
    if screenshot_path:
        job.add_screenshot(screenshot_path)

    # Persist to Supabase
    failure_id = ""
    payload = {
        "job_id": job.db_id,
        "company": job.company,
        "title": job.title,
        "apply_url": job.apply_url,
        "stage": stage,
        "error": error_str[:1000],
        "traceback": traceback_str[:3000],
        "screenshot_path": screenshot_path,
        "html_path": html_path,
        "extra": extra or {},
    }
    try:
        res = get_client().table("failure_log").insert(payload).execute()
        failure_id = res.data[0]["id"]
        logger.info(f"[failure] Logged failure {failure_id} for {job.company} / {stage}")
    except Exception as e:
        logger.warning(f"[failure] Failed to persist to DB: {e}")

    logger.error(
        f"[failure] {stage} failed for {job.title!r} @ {job.company!r}: {error_str}"
    )
    return failure_id


def get_recent_failures(limit: int = 20) -> list[dict]:
    """Fetch recent failures for dashboard display."""
    try:
        res = (
            get_client()
            .table("failure_log")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception as e:
        logger.error(f"[failure] get_recent_failures error: {e}")
        return []
