"""
modules/decision_engine.py — Rule-based decision logic.

Stage 2 path (new): decide_from_gemini()
  Uses is_fresher_job + profile_match + confidence from Gemini's new schema.
  Rule-based — NOT a single numeric threshold.

Stage 1 path (kept for backward compat): decide()
  Simple threshold logic on match_score, still used as fallback if needed.
"""
from utils.logger import setup_logger

logger = setup_logger("decision_engine")


def decide_from_gemini(result: dict) -> str:
    """
    Rule-based decision using Gemini's structured verdict.

    Thresholds:
      profile_match >= 80  ->  auto_apply   (bot applies; if it fails -> manual)
      profile_match >= 70  ->  manual_review (send to Telegram for Harish to apply)
      profile_match <  70  ->  ignore

    Rules (evaluated in order — first match wins):
      1. is_fresher_job == False  →  ignore (experience req too high, skip entirely)
      2. Gemini rec == ignore     →  ignore (Gemini explicitly rejected)
      3. profile_match >= 80      →  auto_apply
      4. profile_match >= 70      →  manual_review
      5. else                     →  ignore

    Note: confidence is no longer a hard gate — low-confidence jobs in the
    70-79 range still go to manual_review so Harish can decide.

    Parameters
    ----------
    result : dict
        The full dict returned by job_analyzer.analyze_job().

    Returns
    -------
    str : 'auto_apply' | 'manual_review' | 'ignore'
    """
    is_fresher_job = result.get("is_fresher_job", False)
    profile_match = result.get("profile_match", 0)
    gemini_rec = result.get("recommendation", "ignore")

    # Rule 1 — Not a fresher role at all
    if not is_fresher_job:
        logger.debug(
            f"[decision] IGNORE — not a fresher job "
            f"(exp_reason: {result.get('experience_reason', '')[:80]})"
        )
        return "ignore"

    # Rule 2 — Gemini explicitly recommended ignore
    if gemini_rec == "ignore":
        logger.debug(
            f"[decision] IGNORE — Gemini recommended IGNORE "
            f"(profile_match={profile_match}%)"
        )
        return "ignore"

    # Rule 3 — Strong match -> auto apply
    if profile_match >= 80:
        logger.debug(
            f"[decision] AUTO_APPLY — fresher_job=True, profile_match={profile_match}%"
        )
        return "auto_apply"

    # Rule 4 — Decent match -> send to Telegram for manual review
    if profile_match >= 70:
        logger.debug(
            f"[decision] MANUAL_REVIEW — profile_match={profile_match}% (70-79 range)"
        )
        return "manual_review"

    # Rule 5 — Too low -> ignore
    logger.debug(f"[decision] IGNORE — profile_match={profile_match}% < 70%")
    return "ignore"


def decide(match_score: int, settings: dict) -> str:
    """
    Legacy threshold-based decision.  Kept for backward compatibility.
    New code should use decide_from_gemini() instead.

    Returns 'auto_apply' | 'manual_review' | 'ignore'.
    """
    thresholds = settings.get("match_thresholds", {})
    if match_score >= thresholds.get("auto_apply", 80):
        decision = "auto_apply"
    elif match_score >= thresholds.get("manual_review", 70):
        decision = "manual_review"
    else:
        decision = "ignore"
    logger.debug(f"[decision] (legacy) score={match_score} → {decision}")
    return decision
