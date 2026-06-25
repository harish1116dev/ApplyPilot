"""Module 2 — Resume Library: selects the right resume PDF/DOCX per job."""
import os
from utils.logger import setup_logger

logger = setup_logger("resume_library")

RESUMES_DIR = os.path.join("config", "resumes")

# Supported extensions in preference order
EXTENSIONS = [".pdf", ".docx", ".doc"]


def _find_resume_file(variant: str) -> str | None:
    for ext in EXTENSIONS:
        path = os.path.join(RESUMES_DIR, f"{variant}_resume{ext}")
        if os.path.exists(path):
            return path
    return None


def select_resume(job_analysis: dict, profile: dict) -> str:
    """Return file path to the best matching resume for this job."""
    required_skills = [s.lower() for s in job_analysis.get("skills_required", [])]
    title_words = job_analysis.get("title", "").lower().split()

    variant_scores: dict[str, int] = {}

    for variant, variant_skills in profile.get("resume_variants", {}).items():
        score = sum(
            1 for skill in variant_skills
            if skill.lower() in " ".join(required_skills + title_words)
        )
        variant_scores[variant] = score

    best_variant = max(variant_scores, key=variant_scores.get) if variant_scores else "fullstack"

    # Try best variant first, then fallback to master
    path = _find_resume_file(best_variant)
    if not path:
        path = _find_resume_file("master")
    if not path:
        # Last resort: any resume in the folder
        for f in os.listdir(RESUMES_DIR):
            if any(f.endswith(ext) for ext in EXTENSIONS):
                path = os.path.join(RESUMES_DIR, f)
                break

    logger.info(f"Selected resume variant: {best_variant} → {path}")
    return path
