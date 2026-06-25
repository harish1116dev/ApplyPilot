"""Module 9 — Cover Letter Agent: generates cover letter only when required."""
from utils.gemini_client import call_gemini
from utils.logger import setup_logger

logger = setup_logger("cover_letter_agent")

COVER_LETTER_PROMPT = """
Write a concise, genuine cover letter for this fresher applying to this role.
Max 200 words. No generic filler. Focus on specific skills that match.
Sound human, not robotic.

Candidate: {profile_summary}
Job: {job_title} at {company}
Why they match: {strong_matches}

Return only the cover letter text, no subject line, no formatting.
"""


def generate_cover_letter(profile: dict, job_analysis: dict, strong_matches: list[str] = None) -> str:
    p = profile["personal"]
    skills_flat = []
    for v in profile["skills"].values():
        skills_flat.extend(v[:3])  # top skills per category

    profile_summary = (
        f"{p['name']}, B.Tech AI & DS from S.A. Engineering College (2024). "
        f"Skills: {', '.join(skills_flat[:10])}. "
        f"Projects: {', '.join(proj['name'] for proj in profile.get('projects', [])[:3])}."
    )

    prompt = COVER_LETTER_PROMPT.format(
        profile_summary=profile_summary,
        job_title=job_analysis.get("title", ""),
        company=job_analysis.get("company", ""),
        strong_matches=", ".join(strong_matches or job_analysis.get("skills_required", [])[:5]),
    )

    try:
        letter = call_gemini(prompt).strip()
        logger.info(f"Cover letter generated ({len(letter)} chars)")
        return letter
    except Exception as e:
        logger.error(f"Cover letter generation failed: {e}")
        return ""
