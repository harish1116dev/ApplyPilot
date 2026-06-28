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

    Rules (evaluated in order — first match wins):
      1. is_fresher_job == False  →  ignore   (experience requirement too high)
      2. profile_match < 80       →  ignore   (profile doesn't fit)
      3. confidence < 80          →  manual_review  (Gemini is unsure)
      4. else                     →  auto_apply

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
    confidence = result.get("confidence", 0)
    # Also respect Gemini's own recommendation if it explicitly said IGNORE
    gemini_rec = result.get("recommendation", "ignore")

    # Rule 1 — Not a fresher role
    if not is_fresher_job:
        logger.debug(
            f"[decision] IGNORE — not a fresher job "
            f"(exp_reason: {result.get('experience_reason', '')[:80]})"
        )
        return "ignore"

    # Rule 2 — Gemini explicitly recommended ignore (e.g. profile mismatch it detected)
    if gemini_rec == "ignore":
        logger.debug(f"[decision] IGNORE — Gemini recommended IGNORE "
                     f"(profile_match={profile_match}%)")
        return "ignore"

    # Rule 3 — Profile match too low
    if profile_match < 80:
        logger.debug(f"[decision] IGNORE — profile_match={profile_match}% < 80%")
        return "ignore"

    # Rule 4 — Confidence too low → surface for human review
    if confidence < 80:
        logger.debug(
            f"[decision] MANUAL_REVIEW — confidence={confidence}% < 80% "
            f"(profile_match={profile_match}%)"
        )
        return "manual_review"

    # Rule 5 — All checks passed
    logger.debug(
        f"[decision] AUTO_APPLY — fresher_job=True, "
        f"profile_match={profile_match}%, confidence={confidence}%"
    )
    return "auto_apply"


def decide(match_score: int, settings: dict) -> str:
    """
    Legacy threshold-based decision.  Kept for backward compatibility.
    New code should use decide_from_gemini() instead.

    Returns 'auto_apply' | 'apply' | 'manual_review' | 'ignore'.
    """
    thresholds = settings.get("match_thresholds", {})
    if match_score >= thresholds.get("auto_apply", 85):
        decision = "auto_apply"
    elif match_score >= thresholds.get("apply", 80):
        decision = "apply"
    elif match_score >= thresholds.get("manual_review", 70):
        decision = "manual_review"
    elif match_score >= thresholds.get("ignore_below", 60):
        decision = "manual_review"  # borderline — still surface it
    else:
        decision = "ignore"
    logger.debug(f"[decision] (legacy) score={match_score} → {decision}")
    return decision
