"""
modules/job_analyzer.py — Stage 2: Gemini Eligibility + Profile Match.

Only called AFTER the Python fresher filter (Stage 1) has already rejected
70-80% of jobs.  This module is responsible for:

  1. Determining whether a job is genuinely fresher-eligible
  2. Scoring the candidate's profile against the job
  3. Returning a structured verdict for the decision engine

Design principles:
  - ONE Gemini call per job (analyze + match combined)
  - Strict prompt: "Your job is to REJECT unsuitable jobs"
  - Returns new schema with is_fresher_job + confidence + recommendation
  - Full JD cached by jd_cache before this module is called (see pipeline.py)
"""
from utils.gemini_client import call_gemini_json
from utils.logger import setup_logger

logger = setup_logger("job_analyzer")


# ─── Prompt ───────────────────────────────────────────────────────────────────

GEMINI_ELIGIBILITY_PROMPT = """SYSTEM
You are an experienced technical recruiter reviewing job descriptions.

Your job is NOT to maximize matches.
Your job is to REJECT unsuitable jobs.

Be extremely strict.
If the job is not clearly suitable for a fresher, recommend IGNORE.
Never assume. Only use information explicitly present in the job description.
Avoid inflated scores. A profile_match above 85 should only be given when
the candidate realistically has a high chance of being shortlisted.

────────────────────────────────────────────────────────────────────
CANDIDATE PROFILE
────────────────────────────────────────────────────────────────────
{profile_block}

────────────────────────────────────────────────────────────────────
JOB DESCRIPTION
────────────────────────────────────────────────────────────────────
Title:   {title}
Company: {company}

{raw_jd}

────────────────────────────────────────────────────────────────────
INSTRUCTIONS
────────────────────────────────────────────────────────────────────
STEP 1 — Fresher Eligibility

A job is fresher-eligible ONLY if it meets at least one of:
  • Explicitly mentions: Fresher, Entry Level, Graduate, Trainee, Campus
  • Experience starts from 0 (e.g. 0-1, 0-2, 0-3 years)
  • No experience requirement stated at all

Set is_fresher_job = false and recommendation = "IGNORE" if:
  • Minimum experience starts from 1 year or more
  • Requires 2+ years, 3+ years, or any N+ years where N >= 2
  • Job title contains Senior, Lead, Principal, Staff, Manager, Architect,
    Director, Head of, VP

If experience requirement is ambiguous or unstated, set is_fresher_job = true
but set recommendation = "MANUAL_REVIEW" and confidence <= 70.

STEP 2 — Profile Match (only if is_fresher_job = true)

Compare the candidate against the job. Consider:
  • Education (degree, field, graduation year)
  • Skills (required vs. candidate's skills)
  • Projects (relevance to the role)
  • Location (preferred cities vs. job location / remote)
  • Experience level fit

Do NOT ignore experience requirements simply because skills match.
Experience eligibility has higher priority than skill alignment.

STEP 3 — Output

Return ONLY valid JSON, no markdown, no explanation.

{{
  "is_fresher_job": <true|false>,
  "experience_requirement": "<exact text from JD or 'not stated'>",
  "experience_reason": "<one line explaining why is_fresher_job is true/false>",
  "profile_match": <integer 0-100>,
  "profile_reason": "<one line explaining the match score>",
  "missing_skills": ["skill1", "skill2"],
  "strong_matches": ["skill1", "skill2"],
  "recommendation": "<AUTO_APPLY|MANUAL_REVIEW|IGNORE>",
  "confidence": <integer 0-100>,
  "title": "{title}",
  "company": "{company}",
  "location": "<job location from JD>",
  "remote": <true|false>,
  "salary_min": <integer LPA or null>,
  "salary_max": <integer LPA or null>,
  "skills_required": ["skill1", "skill2"],
  "apply_method": "<direct|easy_apply|email|not_stated>",
  "questions": [],
  "cover_letter_required": <true|false>,
  "summary": "<2-3 sentence summary of the role>"
}}
"""


# ─── Profile Builder ──────────────────────────────────────────────────────────

def _build_profile_block(profile: dict) -> str:
    """Build a richly formatted profile string for the Gemini prompt."""
    p = profile.get("personal", {})
    edu = profile.get("education", [{}])[0]
    target = profile.get("target", {})

    # Flatten all skills
    skills_flat = []
    for category, skill_list in profile.get("skills", {}).items():
        skills_flat.extend(skill_list)

    # Projects with tech stacks
    project_lines = []
    for proj in profile.get("projects", []):
        stack = ", ".join(proj.get("tech_stack", []))
        project_lines.append(f"  • {proj['name']} ({stack})")

    grad_year = edu.get("year", "N/A")
    experience_level = target.get("experience_level", "Fresher")
    preferred_cities = ", ".join(target.get("preferred_cities", []))
    target_roles = ", ".join(target.get("roles", [])[:8])
    certs = ", ".join(profile.get("certifications", [])[:4])

    block = f"""Name:              {p.get('name', '')}
Experience Level:  {experience_level} (0 years professional experience)
Education:         {edu.get('degree', '')} in {edu.get('field', '')}
Institution:       {edu.get('institution', '')}
Graduation Year:   {grad_year}
Location:          {p.get('location', '')}
Preferred Cities:  {preferred_cities}
Target Roles:      {target_roles}

Skills:
  {', '.join(skills_flat)}

Key Projects:
{chr(10).join(project_lines)}

Certifications:    {certs}
Current Training:  {profile.get('current_training', '')}"""
    return block


# ─── Main Analyzer ────────────────────────────────────────────────────────────

def analyze_job(job: dict, profile: dict = None) -> dict:
    """
    Run Gemini Stage 2 analysis on a job dict.

    Returns a dict compatible with the Job object fields PLUS the new
    is_fresher_job / confidence / recommendation fields from the new schema.

    If profile is None, falls back to analysis-only (no match scoring).
    """
    raw_jd = job.get("raw_jd") or job.get("description") or ""

    # Build minimal JD from available fields if raw text is empty
    if not raw_jd:
        raw_jd = (
            f"Job Title: {job.get('title', '')}\n"
            f"Company: {job.get('company', '')}\n"
            f"Location: {job.get('location', '')}\n"
            f"Experience: {job.get('experience_text', '')}\n"
            f"Salary: {job.get('salary_text', '')}"
        )

    if profile:
        profile_block = _build_profile_block(profile)
        prompt = GEMINI_ELIGIBILITY_PROMPT.format(
            title=job.get("title", ""),
            company=job.get("company", ""),
            raw_jd=raw_jd[:6000],
            profile_block=profile_block,
        )
    else:
        # Profile-free fallback: minimal prompt asking only for structure
        prompt = GEMINI_ELIGIBILITY_PROMPT.format(
            title=job.get("title", ""),
            company=job.get("company", ""),
            raw_jd=raw_jd[:6000],
            profile_block="(No candidate profile provided — skip profile match. Set profile_match=0.)",
        )

    try:
        analysis = call_gemini_json(prompt)

        # Normalize recommendation to lowercase for downstream compatibility
        rec = analysis.get("recommendation", "IGNORE").upper()
        # Map new schema → old pipeline decision values
        rec_map = {
            "AUTO_APPLY": "auto_apply",
            "MANUAL_REVIEW": "manual_review",
            "IGNORE": "ignore",
        }
        analysis["recommendation"] = rec_map.get(rec, "ignore")

        # Bridge: expose profile_match as "match" for backward compatibility
        analysis["match"] = analysis.get("profile_match", 0)
        analysis["match_reason"] = analysis.get("profile_reason", "")

        # Merge scraped fields as fallback
        analysis.setdefault("title", job.get("title", ""))
        analysis.setdefault("company", job.get("company", ""))
        analysis.setdefault("location", job.get("location", ""))
        analysis["apply_url"] = job.get("apply_url", "")
        analysis["platform"] = job.get("platform", "")
        analysis["source_urls"] = job.get("source_urls", [])
        analysis["raw_jd"] = raw_jd[:3000]

        # Log summary
        is_fresher = analysis.get("is_fresher_job", False)
        score = analysis.get("profile_match", 0)
        confidence = analysis.get("confidence", 0)
        rec_out = analysis.get("recommendation", "ignore")
        logger.info(
            f"[job_analyzer] '{analysis.get('title')}' @ '{analysis.get('company')}' "
            f"| fresher={is_fresher} | match={score}% | conf={confidence}% "
            f"| → {rec_out.upper()}"
        )

        return analysis

    except Exception as e:
        logger.error(f"[job_analyzer] Gemini failed for '{job.get('title')}': {e}")
        # Return a safe fallback that will be ignored by the decision engine
        return {
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "location": job.get("location", ""),
            "remote": False,
            "salary_min": None,
            "salary_max": None,
            "experience_required": "",
            "experience_requirement": "",
            "experience_reason": "Analysis failed",
            "skills_required": [],
            "apply_method": "",
            "questions": [],
            "cover_letter_required": False,
            "summary": "",
            "is_fresher_job": False,
            "profile_match": 0,
            "profile_reason": "Analysis failed",
            "match": 0,
            "match_reason": "Analysis failed",
            "missing_skills": [],
            "strong_matches": [],
            "recommendation": "ignore",
            "confidence": 0,
            "apply_url": job.get("apply_url", ""),
            "platform": job.get("platform", ""),
            "source_urls": job.get("source_urls", []),
            "raw_jd": raw_jd[:3000],
        }
