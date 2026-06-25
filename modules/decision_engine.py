"""Module 7 — Decision Engine: threshold logic."""
from utils.logger import setup_logger

logger = setup_logger("decision_engine")


def decide(match_score: int, settings: dict) -> str:
    """Return 'auto_apply' | 'apply' | 'manual_review' | 'ignore'."""
    thresholds = settings["match_thresholds"]
    if match_score >= thresholds["auto_apply"]:
        decision = "auto_apply"
    elif match_score >= thresholds["apply"]:
        decision = "apply"
    elif match_score >= thresholds["manual_review"]:
        decision = "manual_review"
    else:
        decision = "ignore"
    logger.debug(f"Score {match_score} → decision: {decision}")
    return decision
