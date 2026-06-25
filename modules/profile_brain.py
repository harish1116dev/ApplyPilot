"""Module 1 — Profile Brain: loads and validates profile.json."""
import json
import os
from utils.logger import setup_logger

logger = setup_logger("profile_brain")
PROFILE_PATH = os.path.join("config", "profile.json")


def load_profile() -> dict:
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        profile = json.load(f)
    logger.info("Profile loaded successfully.")
    return profile


def validate_profile(profile: dict) -> tuple[bool, list[str]]:
    errors = []
    required_personal = ["name", "email", "phone"]
    for field in required_personal:
        if not profile.get("personal", {}).get(field):
            errors.append(f"Missing personal.{field}")
    if not profile.get("target", {}).get("roles"):
        errors.append("No target roles defined")
    if not profile.get("skills"):
        errors.append("No skills defined")
    if errors:
        logger.warning(f"Profile validation issues: {errors}")
        return False, errors
    return True, []


def get_skills_flat(profile: dict) -> list[str]:
    skills = profile.get("skills", {})
    flat = []
    for category_skills in skills.values():
        flat.extend(category_skills)
    return list(dict.fromkeys(flat))  # deduplicated, order preserved


def get_resume_variant_for_role(profile: dict, role_keywords: list[str]) -> str:
    """Map job role keywords to a resume variant name."""
    keywords_lower = [k.lower() for k in role_keywords]
    variant_map = {
        "ai": ["ai", "ml", "machine learning", "deep learning", "data science", "nlp", "llm"],
        "flutter": ["flutter", "dart", "mobile", "android", "ios"],
        "frontend": ["frontend", "front-end", "react", "ui", "html", "css"],
        "backend": ["backend", "back-end", "node", "express", "api", "server"],
        "fullstack": ["full stack", "fullstack", "full-stack"],
    }
    scores = {variant: 0 for variant in variant_map}
    for variant, terms in variant_map.items():
        for term in terms:
            if any(term in kw for kw in keywords_lower):
                scores[variant] += 1

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "fullstack"  # sensible default
    return best
