"""
modules/resume_versioning.py — Track which resume version leads to interviews.

Every application records:
- Which file was sent (hash)
- Which variant (frontend / ai / fullstack ...)
- What outcome it got

Later: "Your AI resume: 40% interview rate vs fullstack: 15%"
"""
import hashlib
import os
from db.supabase_client import get_client
from utils.logger import setup_logger

logger = setup_logger("resume_versioning")


def _file_hash(path: str) -> str:
    """SHA256 hash of file — detects if resume changed."""
    if not path or not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def record_version(job_db_id: str, resume_path: str, variant: str) -> str:
    """
    Record a resume version for this application.
    Returns the version_id (UUID from Supabase).
    """
    file_hash = _file_hash(resume_path)
    payload = {
        "variant": variant,
        "optimized_for_job": job_db_id,
        "file_path": resume_path,
        "keywords_added": [],
        "file_hash": file_hash,
    }
    try:
        res = get_client().table("resumes").insert(payload).execute()
        version_id = res.data[0]["id"]
        logger.debug(f"[resume_versioning] Recorded version {version_id} ({variant})")
        return version_id
    except Exception as e:
        logger.warning(f"[resume_versioning] Failed to record version: {e}")
        return ""


def get_win_rates() -> list[dict]:
    """
    Calculate interview rate per resume variant.
    Returns: [{"variant": "ai", "total": 20, "interviews": 8, "rate_pct": 40}, ...]
    """
    try:
        res = (
            get_client()
            .table("applications")
            .select("resume_variant, status")
            .execute()
        )
        apps = res.data or []

        stats: dict[str, dict] = {}
        for app in apps:
            v = app.get("resume_variant") or "unknown"
            stats.setdefault(v, {"variant": v, "total": 0, "interviews": 0})
            stats[v]["total"] += 1
            if app.get("status") == "interview":
                stats[v]["interviews"] += 1

        result = []
        for v, s in stats.items():
            rate = round(s["interviews"] / s["total"] * 100, 1) if s["total"] > 0 else 0
            result.append({**s, "rate_pct": rate})

        result.sort(key=lambda x: x["rate_pct"], reverse=True)
        return result
    except Exception as e:
        logger.error(f"[resume_versioning] get_win_rates error: {e}")
        return []


def get_best_variant() -> str:
    """Return the resume variant with highest interview rate (min 5 applications)."""
    rates = get_win_rates()
    qualified = [r for r in rates if r["total"] >= 5]
    if qualified:
        best = qualified[0]["variant"]
        logger.info(f"[resume_versioning] Best variant: {best} ({qualified[0]['rate_pct']}% interview rate)")
        return best
    return "fullstack"  # default before enough data
