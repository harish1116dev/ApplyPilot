"""Module 5 — Job Analyzer: Gemini extracts structured JSON from JD.

Optimized: if a profile is passed, analyze + match is done in ONE Gemini call
instead of two, halving API usage and eliminating the rate-limit bottleneck.
"""
from utils.gemini_client import call_gemini_json
from utils.logger import setup_logger

logger = setup_logger("job_analyzer")

ANALYSIS_PROMPT = """
You are a job description parser AND recruitment AI combined.
Extract structured data from this job description AND score the candidate match.
Return ONLY valid JSON, no markdown, no explanation.

Job Title: {title}
Company: {company}
Job Description:
{raw_jd}

Candidate Profile:
{profile_summary}

IMPORTANT SCORING RULES:
- If the job says experience required is 0, 0-1, 0-2, or 0-3 years (even without the word 'fresher'), treat it as VALID for this fresher candidate.
- Do NOT penalize for missing the word 'fresher' in the JD. Judge purely on skills and experience range.
- If experience starts from 0, the candidate is 100% eligible experience-wise.
- If experience required is 3+ years, set score below 50 and recommend 'ignore'.

Return this exact JSON structure:
{{
  "title": "",
  "company": "",
  "location": "",
  "remote": false,
  "salary_min": null,
  "salary_max": null,
  "experience_required": "",
  "skills_required": [],
  "deadline": null,
  "hiring_manager": null,
  "apply_method": "",
  "questions": [],
  "cover_letter_required": false,
  "summary": "",
  "match": <integer 0-100>,
  "match_reason": "<one line explanation>",
  "missing_skills": [],
  "strong_matches": [],
  "recommendation": "auto_apply|apply|manual_review|ignore"
}}

Scoring guide:
- 90-100: Perfect fit — all skills match, experience starts from 0
- 75-89: Strong fit — most skills match, experience 0-2 years
- 60-74: Moderate fit — some skill gaps but experience is eligible
- Below 60: Poor fit — major skill gaps OR experience > 2 years required
"""

ANALYSIS_ONLY_PROMPT = """
You are a job description parser.
Extract structured data from this job description.
Return ONLY valid JSON, no markdown, no explanation.

Job Title: {title}
Company: {company}
Job Description:
{raw_jd}

Return this exact JSON structure:
{{
  "title": "",
  "company": "",
  "location": "",
  "remote": false,
  "salary_min": null,
  "salary_max": null,
  "experience_required": "",
  "skills_required": [],
  "deadline": null,
  "hiring_manager": null,
  "apply_method": "",
  "questions": [],
  "cover_letter_required": false,
  "summary": ""
}}
"""


def _build_profile_summary(profile: dict) -> str:
    skills_flat = []
    for v in profile.get("skills", {}).values():
        skills_flat.extend(v)
    projects = [proj["name"] for proj in profile.get("projects", [])]
    p = profile["personal"]
    return (
        f"Name: {p['name']}\n"
        f"Experience: {profile['target']['experience_level']}\n"
        f"Education: {profile['education'][0]['degree']} in {profile['education'][0]['field']}\n"
        f"Skills: {', '.join(skills_flat)}\n"
        f"Projects: {', '.join(projects)}\n"
        f"Target Roles: {', '.join(profile['target']['roles'][:8])}\n"
        f"Preferred Cities: {', '.join(profile['target']['preferred_cities'])}"
    )


def analyze_job(job: dict, profile: dict = None) -> dict:
    """Analyze a raw job dict and return structured analysis.
    
    If profile is provided, match scoring is included in the SAME Gemini call
    (1 API call instead of 2), dramatically reducing rate-limit stalls.
    """
    raw_jd = job.get("raw_jd") or job.get("description") or ""

    # If no JD text, build a minimal prompt from what we have
    if not raw_jd:
        raw_jd = (
            f"Job Title: {job.get('title', '')}\n"
            f"Company: {job.get('company', '')}\n"
            f"Location: {job.get('location', '')}\n"
            f"Experience: {job.get('experience_text', '')}\n"
            f"Salary: {job.get('salary_text', '')}"
        )

    if profile:
        profile_summary = _build_profile_summary(profile)
        prompt = ANALYSIS_PROMPT.format(
            title=job.get("title", ""),
            company=job.get("company", ""),
            raw_jd=raw_jd[:5000],
            profile_summary=profile_summary,
        )
    else:
        prompt = ANALYSIS_ONLY_PROMPT.format(
            title=job.get("title", ""),
            company=job.get("company", ""),
            raw_jd=raw_jd[:6000],
        )

    try:
        analysis = call_gemini_json(prompt)
        # Merge scraped fields as fallback
        analysis.setdefault("title", job.get("title", ""))
        analysis.setdefault("company", job.get("company", ""))
        analysis.setdefault("location", job.get("location", ""))
        analysis["apply_url"] = job.get("apply_url", "")
        analysis["platform"] = job.get("platform", "")
        analysis["source_urls"] = job.get("source_urls", [])
        analysis["raw_jd"] = raw_jd[:3000]
        match_score = analysis.get("match", 0)
        logger.info(
            f"Analyzed: {analysis.get('title')} @ {analysis.get('company')} "
            + (f"| match={match_score}%" if profile else "")
        )
        return analysis
    except Exception as e:
        logger.error(f"Job analysis failed for {job.get('title')}: {e}")
        # Return minimal fallback
        return {
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "location": job.get("location", ""),
            "remote": False,
            "salary_min": None,
            "salary_max": None,
            "experience_required": "",
            "skills_required": [],
            "apply_method": "",
            "questions": [],
            "cover_letter_required": False,
            "summary": "",
            "match": 0,
            "match_reason": "Analysis failed",
            "missing_skills": [],
            "strong_matches": [],
            "recommendation": "ignore",
            "apply_url": job.get("apply_url", ""),
            "platform": job.get("platform", ""),
            "source_urls": job.get("source_urls", []),
            "raw_jd": raw_jd[:3000],
        }
