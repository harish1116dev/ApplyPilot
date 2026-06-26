"""
db/company_memory.py — Company intelligence database.

Before applying to any company, the bot checks memory:
- What platform do they use?
- What questions do they typically ask?
- What's the average match score?
- Have we applied before?

This makes every repeat-company application much faster and smarter.
"""
from db.supabase_client import get_client
from utils.logger import setup_logger

logger = setup_logger("company_memory")


def get_company(company_name: str) -> dict | None:
    """Fetch company memory record. Returns None if not known."""
    try:
        res = (
            get_client()
            .table("companies")
            .select("*")
            .ilike("company_name", company_name.strip())
            .limit(1)
            .execute()
        )
        if res.data:
            logger.debug(f"[company_memory] Found record for {company_name}")
            return res.data[0]
        return None
    except Exception as e:
        logger.warning(f"[company_memory] get_company error: {e}")
        return None


def upsert_company(company_name: str, update: dict) -> None:
    """Create or update a company memory record."""
    try:
        existing = get_company(company_name)
        if existing:
            get_client().table("companies").update(update).eq("company_name", existing["company_name"]).execute()
            logger.debug(f"[company_memory] Updated {company_name}")
        else:
            data = {"company_name": company_name, **update}
            get_client().table("companies").insert(data).execute()
            logger.debug(f"[company_memory] Created record for {company_name}")
    except Exception as e:
        logger.warning(f"[company_memory] upsert_company error: {e}")


def record_application(company_name: str, platform: str, match_score: int, questions: list) -> None:
    """Called after every application to update company memory."""
    try:
        existing = get_company(company_name)
        if existing:
            # Update rolling avg match score
            prev_avg = existing.get("avg_match_score") or match_score
            prev_count = existing.get("total_applications") or 0
            new_avg = round((prev_avg * prev_count + match_score) / (prev_count + 1), 1)

            # Merge questions (keep unique)
            existing_qs = existing.get("typical_questions") or []
            merged_qs = list({q for q in existing_qs + questions})[:20]

            upsert_company(company_name, {
                "platform": platform or existing.get("platform", ""),
                "avg_match_score": new_avg,
                "total_applications": prev_count + 1,
                "typical_questions": merged_qs,
            })
        else:
            upsert_company(company_name, {
                "platform": platform,
                "avg_match_score": match_score,
                "total_applications": 1,
                "typical_questions": questions[:20],
            })
    except Exception as e:
        logger.warning(f"[company_memory] record_application error: {e}")


def enrich_job_from_memory(job) -> None:
    """
    Enriches a Job object with company memory data in-place.
    Call this early in the pipeline to skip re-detecting platform/questions.
    """
    from models.job import Job
    memory = get_company(job.company)
    if not memory:
        return

    job.company_known = True
    if memory.get("platform") and not job.company_platform:
        job.company_platform = memory["platform"]
    if memory.get("typical_questions") and not job.questions:
        job.company_typical_questions = memory["typical_questions"]

    logger.info(
        f"[company_memory] Enriched {job.company} from memory "
        f"(platform={job.company_platform}, "
        f"past_applications={memory.get('total_applications', 0)}, "
        f"avg_match={memory.get('avg_match_score', '?')}%)"
    )
