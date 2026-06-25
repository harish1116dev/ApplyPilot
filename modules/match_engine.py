"""Module 6 — Match Engine: Gemini compares profile vs job."""
import json
from utils.gemini_client import call_gemini_json
from utils.logger import setup_logger

logger = setup_logger("match_engine")

MATCH_PROMPT = """
You are a recruitment AI. Compare this candidate profile against this job requirement.
Return ONLY valid JSON, no markdown.

Candidate Profile:
{profile_summary}

Job Requirements:
{job_analysis}

Return:
{{
  "match": <integer 0-100>,
  "reason": "<one line explanation>",
  "missing_skills": ["skill1", "skill2"],
  "strong_matches": ["skill1", "skill2"],
  "recommendation": "auto_apply|apply|manual_review|ignore"
}}

Scoring guide:
- 95-100: Perfect fit, all required skills match
- 80-94: Strong fit, minor gaps
- 70-79: Moderate fit, some important gaps
- Below 70: Poor fit, significant gaps
"""


def _build_profile_summary(profile: dict) -> str:
    p = profile["personal"]
    skills_flat = []
    for v in profile["skills"].values():
        skills_flat.extend(v)
    projects = [proj["name"] for proj in profile.get("projects", [])]
    return (
        f"Name: {p['name']}\n"
        f"Experience: {profile['target']['experience_level']}\n"
        f"Education: {profile['education'][0]['degree']} in {profile['education'][0]['field']}\n"
        f"Skills: {', '.join(skills_flat)}\n"
        f"Projects: {', '.join(projects)}\n"
        f"Target Roles: {', '.join(profile['target']['roles'])}\n"
        f"Preferred Cities: {', '.join(profile['target']['preferred_cities'])}"
    )


def calculate_match(profile: dict, job_analysis: dict) -> dict:
    profile_summary = _build_profile_summary(profile)
    job_str = json.dumps({
        "title": job_analysis.get("title"),
        "company": job_analysis.get("company"),
        "skills_required": job_analysis.get("skills_required", []),
        "experience_required": job_analysis.get("experience_required"),
        "summary": job_analysis.get("summary", "")[:500],
    }, indent=2)

    prompt = MATCH_PROMPT.format(
        profile_summary=profile_summary,
        job_analysis=job_str,
    )

    try:
        result = call_gemini_json(prompt)
        logger.info(
            f"Match for {job_analysis.get('title')} @ {job_analysis.get('company')}: "
            f"{result.get('match')}% — {result.get('recommendation')}"
        )
        return result
    except Exception as e:
        logger.error(f"Match engine error: {e}")
        return {
            "match": 0,
            "reason": "Analysis failed",
            "missing_skills": [],
            "strong_matches": [],
            "recommendation": "ignore",
        }
