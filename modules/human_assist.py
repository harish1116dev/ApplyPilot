"""Module 13 — Human Assist: handles CAPTCHA, OTP, account creation fallbacks."""
import webbrowser
import os
from db.supabase_client import insert_manual_task
from modules.notification_agent import send_manual_alert
from utils.logger import setup_logger

logger = setup_logger("human_assist")


def trigger_human_assist(
    job: dict,
    resume_path: str,
    answers: dict,
    reason: str = "unknown",
) -> None:
    """
    Saves all prepared materials to manual_tasks table and notifies via Telegram.
    Opens the apply URL in the default browser for manual action.
    """
    logger.info(
        f"Human assist triggered: {job.get('title')} @ {job.get('company')} "
        f"— reason: {reason}"
    )

    task_data = {
        "job_id": job.get("id"),
        "reason": reason,
        "apply_url": job.get("apply_url", ""),
        "resume_path": resume_path or "",
        "prepared_answers": answers or {},
        "status": "pending",
    }

    try:
        task_id = insert_manual_task(task_data)
        logger.info(f"Manual task saved: {task_id}")
    except Exception as e:
        logger.error(f"Failed to save manual task: {e}")

    # Send Telegram alert
    try:
        send_manual_alert(job, answers, reason)
    except Exception as e:
        logger.error(f"Telegram alert failed: {e}")

    # Open browser for manual action
    apply_url = job.get("apply_url", "")
    if apply_url:
        try:
            webbrowser.open(apply_url)
            logger.info(f"Opened browser: {apply_url}")
        except Exception as e:
            logger.warning(f"Could not open browser: {e}")
