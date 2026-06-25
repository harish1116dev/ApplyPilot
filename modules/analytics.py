"""Module 15 — Analytics: stats aggregation from Supabase."""
from db.supabase_client import get_client
from utils.logger import setup_logger

logger = setup_logger("analytics")


def get_summary_stats() -> dict:
    """Return overview stats across all tables."""
    try:
        db = get_client()
        jobs_res = db.table("jobs").select("status, match_score").execute()
        apps_res = db.table("applications").select("status").execute()

        jobs = jobs_res.data or []
        apps = apps_res.data or []

        total_found = len(jobs)
        applied = sum(1 for j in jobs if j["status"] == "applied")
        skipped = sum(1 for j in jobs if j["status"] == "skipped")
        scores = [j["match_score"] for j in jobs if j.get("match_score")]
        avg_match = round(sum(scores) / len(scores), 1) if scores else 0

        interviews = sum(1 for a in apps if a["status"] == "interview")
        rejected = sum(1 for a in apps if a["status"] == "rejected")
        offers = sum(1 for a in apps if a["status"] == "offer")

        pending_manual = db.table("manual_tasks").select("id").eq("status", "pending").execute()

        return {
            "total_found": total_found,
            "applied": applied,
            "manual_pending": len(pending_manual.data or []),
            "skipped": skipped,
            "interviews": interviews,
            "rejected": rejected,
            "offers": offers,
            "avg_match": avg_match,
        }
    except Exception as e:
        logger.error(f"Analytics error: {e}")
        return {}


def get_top_missing_skills(limit: int = 10) -> list[str]:
    try:
        res = get_client().table("jobs").select("missing_skills").execute()
        skill_counts: dict[str, int] = {}
        for row in res.data or []:
            for skill in row.get("missing_skills") or []:
                skill_counts[skill] = skill_counts.get(skill, 0) + 1
        sorted_skills = sorted(skill_counts, key=skill_counts.get, reverse=True)
        return sorted_skills[:limit]
    except Exception as e:
        logger.error(f"get_top_missing_skills error: {e}")
        return []


def get_company_stats() -> list[dict]:
    try:
        res = (
            get_client()
            .table("applications")
            .select("status, jobs(company)")
            .execute()
        )
        company_map: dict[str, dict] = {}
        for row in res.data or []:
            company = (row.get("jobs") or {}).get("company", "Unknown")
            if company not in company_map:
                company_map[company] = {"company": company, "total": 0, "interview": 0}
            company_map[company]["total"] += 1
            if row["status"] == "interview":
                company_map[company]["interview"] += 1
        return sorted(company_map.values(), key=lambda x: x["total"], reverse=True)
    except Exception as e:
        logger.error(f"get_company_stats error: {e}")
        return []


def get_weekly_trend() -> list[dict]:
    try:
        res = (
            get_client()
            .table("applications")
            .select("applied_at, status")
            .order("applied_at", desc=True)
            .limit(50)
            .execute()
        )
        return res.data or []
    except Exception as e:
        logger.error(f"get_weekly_trend error: {e}")
        return []
