"""Module 5 — Job Analyzer: Gemini extracts structured JSON from JD."""
from utils.gemini_client import call_gemini_json
from utils.logger import setup_logger

logger = setup_logger("job_analyzer")

ANALYSIS_PROMPT = """
You are a job description parser. Extract structured data from this job description.
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


def analyze_job(job: dict) -> dict:
    """Analyze a raw job dict and return structured analysis."""
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

    prompt = ANALYSIS_PROMPT.format(
        title=job.get("title", ""),
        company=job.get("company", ""),
        raw_jd=raw_jd[:6000],  # cap to avoid token overflow
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
        logger.info(f"Analyzed: {analysis.get('title')} @ {analysis.get('company')}")
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
            "apply_url": job.get("apply_url", ""),
            "platform": job.get("platform", ""),
            "source_urls": job.get("source_urls", []),
            "raw_jd": raw_jd[:3000],
        }
