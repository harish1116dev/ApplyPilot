"""Workday application plugin — triggers human assist (Workday is too dynamic to automate reliably)."""
from utils.logger import setup_logger

logger = setup_logger("workday_plugin")


def apply(job: dict, resume_path: str, cover_letter: str, answers: dict, profile: dict) -> str:
    """
    Workday is highly dynamic, varies company-by-company, and often requires account creation.
    Strategy: immediately delegate to human_assist with prepared materials.
    """
    logger.info(
        f"Workday detected for {job.get('title')} @ {job.get('company')} — "
        "delegating to human_assist (account creation / dynamic forms)"
    )
    return "human_needed"
