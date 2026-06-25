"""Module 14 — Learning Engine: pattern detection from outcomes."""
import json
from db.supabase_client import get_outcomes_for_analysis, insert_learning_log, get_client
from modules.notification_agent import send_weekly_digest
from utils.gemini_client import call_gemini_json
from utils.logger import setup_logger

logger = setup_logger("learning_engine")

ANALYSIS_PROMPT = """
Analyze these job application outcomes and identify actionable patterns.
Return JSON with specific, actionable recommendations.

Applications data:
{applications_summary}

Outcomes data:
{outcomes_summary}

Return:
{{
  "top_missing_skills": [],
  "best_performing_companies": [],
  "worst_performing_platforms": [],
  "avg_match_score_interviews": 0,
  "avg_match_score_rejections": 0,
  "recommendations": [
    {{"priority": "high", "action": "Learn Docker", "reason": "Appears in 60% of rejections"}}
  ]
}}
"""


def run_weekly_analysis() -> dict:
    logger.info("Running weekly learning analysis...")

    outcomes = get_outcomes_for_analysis(limit=100)
    if not outcomes:
        logger.info("No outcomes data yet — skipping analysis")
        return {}

    # Build summaries
    apps_summary = []
    outcomes_summary = []

    for o in outcomes:
        app = o.get("applications") or {}
        job = app.get("jobs") or {}
        apps_summary.append({
            "company": job.get("company"),
            "title": job.get("title"),
            "match_score": job.get("match_score"),
            "skills_required": job.get("skills_required", []),
        })
        outcomes_summary.append({
            "outcome": o.get("outcome"),
            "days_to_response": o.get("days_to_response"),
        })

    prompt = ANALYSIS_PROMPT.format(
        applications_summary=json.dumps(apps_summary[:30], indent=2),
        outcomes_summary=json.dumps(outcomes_summary[:30], indent=2),
    )

    try:
        analysis = call_gemini_json(prompt)
    except Exception as e:
        logger.error(f"Learning engine Gemini error: {e}")
        return {}

    # Count totals
    total_apps = len(outcomes)
    total_interviews = sum(1 for o in outcomes if "interview" in (o.get("outcome") or ""))
    total_rejected = sum(1 for o in outcomes if o.get("outcome") == "rejected")
    total_ghosted = sum(1 for o in outcomes if o.get("outcome") == "ghosted")

    log_entry = {
        "total_applications": total_apps,
        "total_rejected": total_rejected,
        "total_interviews": total_interviews,
        "total_ghosted": total_ghosted,
        "top_missing_skills": analysis.get("top_missing_skills", []),
        "top_companies_applied": analysis.get("best_performing_companies", []),
        "avg_match_score": analysis.get("avg_match_score_interviews", 0),
        "recommendations": analysis.get("recommendations", []),
    }

    try:
        insert_learning_log(log_entry)
        logger.info("Learning log saved to Supabase")
    except Exception as e:
        logger.error(f"Failed to save learning log: {e}")

    # Send Telegram weekly digest
    try:
        send_weekly_digest(log_entry)
    except Exception as e:
        logger.error(f"Failed to send weekly digest: {e}")

    return log_entry
