"""Module 4 — Duplicate Detector: fuzzy deduplication across scrapers."""
from rapidfuzz import fuzz
from utils.logger import setup_logger

logger = setup_logger("duplicate_detector")

SIMILARITY_THRESHOLD = 85


def _normalize(text: str) -> str:
    return text.lower().strip() if text else ""


def deduplicate(jobs: list[dict]) -> list[dict]:
    unique: list[dict] = []

    for job in jobs:
        title = _normalize(job.get("title", ""))
        company = _normalize(job.get("company", ""))
        is_dup = False

        for existing in unique:
            ex_title = _normalize(existing.get("title", ""))
            ex_company = _normalize(existing.get("company", ""))

            title_sim = fuzz.ratio(title, ex_title)
            same_company = fuzz.ratio(company, ex_company) > 85

            if title_sim >= SIMILARITY_THRESHOLD and same_company:
                # Merge source URLs
                existing.setdefault("source_urls", [existing.get("apply_url", "")])
                if job.get("apply_url") and job["apply_url"] not in existing["source_urls"]:
                    existing["source_urls"].append(job["apply_url"])
                is_dup = True
                break

        if not is_dup:
            job["source_urls"] = [job.get("apply_url", "")]
            unique.append(job)

    logger.info(f"Deduplicated: {len(jobs)} → {len(unique)} unique jobs")
    return unique
