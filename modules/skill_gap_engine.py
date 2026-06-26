"""
modules/skill_gap_engine.py — Your secret weapon.

Analyzes rejected applications to find the most impactful missing skills.
Output: "Learn Docker → increases your match by 14%"

Runs:
- After every rejection is recorded
- Weekly batch analysis
- On demand via: python -c "from modules.skill_gap_engine import run; run()"
"""
import json
from collections import Counter
from db.supabase_client import get_client
from utils.gemini_client import call_gemini_json
from utils.logger import setup_logger

logger = setup_logger("skill_gap_engine")

ANALYSIS_PROMPT = """
You are a career advisor AI. Analyze these rejected job applications and calculate
the concrete skill impact for a fresher developer.

Candidate's current skills:
{current_skills}

Missing skills from rejected jobs (with frequency):
{missing_skills_freq}

For each top missing skill, estimate:
1. How much would the match score increase if the candidate learned it?
2. How quickly can it be learned (days)?
3. Which resources to use?

Return ONLY valid JSON:
{{
  "skill_gaps": [
    {{
      "skill": "Docker",
      "frequency": 12,
      "match_increase_percent": 14,
      "learn_days": 7,
      "priority": "high",
      "resources": ["Docker official docs", "Play with Docker"],
      "reason": "Appears in 60% of backend rejections"
    }}
  ],
  "summary": "Top recommendation: Learn Docker this week."
}}
"""


def analyze_skill_gaps(profile: dict) -> dict:
    """
    Fetch all rejected jobs, tally missing skills, run Gemini analysis.
    Returns structured skill gap report.
    """
    logger.info("[skill_gap] Running skill gap analysis...")

    try:
        # Get rejected jobs with their missing_skills
        res = (
            get_client()
            .table("jobs")
            .select("missing_skills, match_score, title, company")
            .in_("status", ["skipped", "applied"])
            .not_.is_("missing_skills", "null")
            .execute()
        )
        jobs_data = res.data or []
    except Exception as e:
        logger.error(f"[skill_gap] DB fetch error: {e}")
        return {}

    if not jobs_data:
        logger.info("[skill_gap] No data yet for analysis")
        return {}

    # Tally all missing skills
    all_missing = []
    for row in jobs_data:
        skills = row.get("missing_skills") or []
        all_missing.extend([s.lower().strip() for s in skills if s])

    if not all_missing:
        return {}

    skill_freq = Counter(all_missing).most_common(20)
    logger.info(f"[skill_gap] Top gaps: {skill_freq[:5]}")

    # Build current skills flat list
    all_skills = []
    for v in profile.get("skills", {}).values():
        all_skills.extend(v)

    prompt = ANALYSIS_PROMPT.format(
        current_skills=", ".join(all_skills),
        missing_skills_freq=json.dumps(
            [{"skill": s, "count": c} for s, c in skill_freq], indent=2
        ),
    )

    try:
        analysis = call_gemini_json(prompt)
    except Exception as e:
        logger.error(f"[skill_gap] Gemini analysis error: {e}")
        # Return raw frequency data as fallback
        return {
            "skill_gaps": [
                {"skill": s, "frequency": c, "priority": "unknown"}
                for s, c in skill_freq[:10]
            ],
            "summary": f"Top missing skill: {skill_freq[0][0]} (seen {skill_freq[0][1]} times)",
        }

    # Persist to Supabase
    try:
        get_client().table("skill_gaps").insert({
            "gaps": analysis.get("skill_gaps", []),
            "summary": analysis.get("summary", ""),
            "total_jobs_analyzed": len(jobs_data),
        }).execute()
        logger.info("[skill_gap] Persisted to skill_gaps table")
    except Exception as e:
        logger.warning(f"[skill_gap] Failed to persist: {e}")

    return analysis


def get_latest_gaps(limit: int = 10) -> list[dict]:
    """Fetch the most recent skill gap analysis from DB."""
    try:
        res = (
            get_client()
            .table("skill_gaps")
            .select("gaps, summary, created_at")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            return (res.data[0].get("gaps") or [])[:limit]
        return []
    except Exception as e:
        logger.error(f"[skill_gap] get_latest_gaps error: {e}")
        return []


def run(profile: dict = None) -> dict:
    """Convenience entry point."""
    if profile is None:
        from modules.profile_brain import load_profile
        profile = load_profile()
    return analyze_skill_gaps(profile)
