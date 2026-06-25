"""Supabase connection + all DB operations."""
import os
from supabase import create_client, Client
from utils.logger import setup_logger

logger = setup_logger("supabase_client")

_client: Client = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise EnvironmentError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
        _client = create_client(url, key)
    return _client


# ─── Jobs ────────────────────────────────────────────────────────────────────

def insert_job(job_data: dict) -> str:
    """Insert a job record and return its UUID."""
    res = get_client().table("jobs").insert(job_data).execute()
    job_id = res.data[0]["id"]
    logger.debug(f"Inserted job {job_id}: {job_data.get('title')} @ {job_data.get('company')}")
    return job_id


def get_job_by_id(job_id: str) -> dict | None:
    res = get_client().table("jobs").select("*").eq("id", job_id).single().execute()
    return res.data


def update_job_status(job_id: str, status: str) -> None:
    get_client().table("jobs").update({"status": status}).eq("id", job_id).execute()
    logger.debug(f"Job {job_id} status → {status}")


def get_jobs_by_decision(decision: str) -> list[dict]:
    res = get_client().table("jobs").select("*").eq("decision", decision).execute()
    return res.data or []


def job_exists(title: str, company: str) -> bool:
    """Check if a job with same title+company already exists (exact match)."""
    res = (
        get_client()
        .table("jobs")
        .select("id")
        .ilike("title", title)
        .ilike("company", company)
        .limit(1)
        .execute()
    )
    return len(res.data) > 0


# ─── Applications ─────────────────────────────────────────────────────────────

def insert_application(app_data: dict) -> str:
    res = get_client().table("applications").insert(app_data).execute()
    return res.data[0]["id"]


def update_application_status(app_id: str, status: str) -> None:
    get_client().table("applications").update({"status": status}).eq("id", app_id).execute()


def get_applications_summary() -> list[dict]:
    res = (
        get_client()
        .table("applications")
        .select("*, jobs(title, company, match_score)")
        .order("applied_at", desc=True)
        .limit(100)
        .execute()
    )
    return res.data or []


# ─── Manual Tasks ─────────────────────────────────────────────────────────────

def insert_manual_task(task_data: dict) -> str:
    res = get_client().table("manual_tasks").insert(task_data).execute()
    return res.data[0]["id"]


def get_pending_manual_tasks() -> list[dict]:
    res = get_client().table("manual_tasks").select("*").eq("status", "pending").execute()
    return res.data or []


def complete_manual_task(task_id: str) -> None:
    from datetime import datetime, timezone
    get_client().table("manual_tasks").update({
        "status": "completed",
        "completed_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", task_id).execute()


# ─── Learning ─────────────────────────────────────────────────────────────────

def insert_learning_log(log_data: dict) -> str:
    res = get_client().table("learning_log").insert(log_data).execute()
    return res.data[0]["id"]


def get_outcomes_for_analysis(limit: int = 100) -> list[dict]:
    res = (
        get_client()
        .table("outcomes")
        .select("*, applications(*, jobs(title, company, skills_required, match_score))")
        .order("recorded_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


# ─── Notifications ────────────────────────────────────────────────────────────

def insert_notification(notif_data: dict) -> None:
    get_client().table("notifications").insert(notif_data).execute()
