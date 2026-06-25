"""Module 8 — Resume Optimizer: Gemini tailors resume emphasis per job."""
import json
from utils.gemini_client import call_gemini_json
from utils.logger import setup_logger

logger = setup_logger("resume_optimizer")

OPTIMIZE_PROMPT = """
You are an ATS resume optimizer. Given this candidate profile and job description,
suggest how to reorder/emphasize existing experience for maximum ATS score.
DO NOT add skills the candidate doesn't have. Only reorder and emphasize.
Return ONLY valid JSON.

Profile:
{profile}

Job:
{job_analysis}

Return:
{{
  "recommended_variant": "frontend|backend|ai|fullstack|flutter",
  "keywords_to_emphasize": [],
  "project_order": [],
  "skills_to_highlight": [],
  "summary_rewrite": ""
}}
"""


def optimize_resume(profile: dict, job_analysis: dict, resume_path: str) -> dict:
    profile_str = json.dumps({
        "skills": profile.get("skills"),
        "projects": [{"name": p["name"], "tech_stack": p["tech_stack"]} for p in profile.get("projects", [])],
        "resume_variants": profile.get("resume_variants"),
    }, indent=2)

    job_str = json.dumps({
        "title": job_analysis.get("title"),
        "skills_required": job_analysis.get("skills_required", []),
        "summary": job_analysis.get("summary", "")[:300],
    }, indent=2)

    prompt = OPTIMIZE_PROMPT.format(profile=profile_str, job_analysis=job_str)

    try:
        result = call_gemini_json(prompt)
        logger.info(f"Resume optimized: variant={result.get('recommended_variant')}")
        return result
    except Exception as e:
        logger.error(f"Resume optimizer error: {e}")
        return {
            "recommended_variant": "fullstack",
            "keywords_to_emphasize": [],
            "project_order": [],
            "skills_to_highlight": [],
            "summary_rewrite": "",
        }
