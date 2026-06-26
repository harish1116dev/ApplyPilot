"""
dashboard/app.py — CareerOS Dashboard (FastAPI)

Run locally: python -m uvicorn dashboard.app:app --reload --port 8000
Then open: http://localhost:8000
"""
import os
import json
import traceback
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="CareerOS Dashboard", version="2.0")

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _read_template(name: str) -> str:
    with open(TEMPLATES_DIR / name, encoding="utf-8") as f:
        return f.read()


# ─── Pages ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(_read_template("index.html"))


# ─── API endpoints (called by dashboard JS) ──────────────────────────────────

@app.get("/api/stats")
async def get_stats():
    try:
        from modules.analytics import get_summary_stats
        return JSONResponse(get_summary_stats())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/jobs")
async def get_jobs(limit: int = 50, status: str = None, decision: str = None):
    try:
        from db.supabase_client import get_client
        q = get_client().table("jobs").select("*").order("created_at", desc=True)
        if status:
            q = q.eq("status", status)
        if decision:
            q = q.eq("decision", decision)
        res = q.limit(limit).execute()
        return JSONResponse(res.data or [])
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/failures")
async def get_failures(limit: int = 20):
    try:
        from modules.failure_analyzer import get_recent_failures
        return JSONResponse(get_recent_failures(limit))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/skill-gaps")
async def get_skill_gaps():
    try:
        from modules.skill_gap_engine import get_latest_gaps
        return JSONResponse(get_latest_gaps())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/resume-versions")
async def get_resume_versions():
    try:
        from modules.resume_versioning import get_win_rates
        return JSONResponse(get_win_rates())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/manual-tasks")
async def get_manual_tasks():
    try:
        from db.supabase_client import get_pending_manual_tasks
        return JSONResponse(get_pending_manual_tasks())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/run-pipeline")
async def trigger_pipeline():
    """Manually trigger a pipeline run (async background). Logs errors properly."""
    import threading
    from utils.logger import setup_logger

    bg_logger = setup_logger("dashboard_bg")

    def _run():
        try:
            from main import run_pipeline
            stats = run_pipeline()
            bg_logger.info(f"[dashboard] Background pipeline complete: {stats}")
        except Exception as e:
            bg_logger.error(
                f"[dashboard] Background pipeline FAILED: {e}\n{traceback.format_exc()}"
            )

    t = threading.Thread(target=_run, daemon=True, name="pipeline-bg")
    t.start()
    return JSONResponse({"status": "Pipeline started in background", "thread": t.name})


@app.get("/api/rate-stats")
async def rate_stats():
    try:
        from utils.rate_limiter import get_rate_stats
        return JSONResponse(get_rate_stats())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/gemini-usage")
async def gemini_usage():
    """Return current Gemini daily usage stats."""
    try:
        from utils.gemini_client import get_daily_usage
        return JSONResponse(get_daily_usage())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/complete-manual-task/{task_id}")
async def complete_manual_task(task_id: str):
    try:
        from db.supabase_client import complete_manual_task as db_complete
        db_complete(task_id)
        return JSONResponse({"status": "completed", "task_id": task_id})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
