"""
core/pipeline.py — Queue-driven, crash-isolated pipeline.

Architecture:
  raw_jobs → [analyze_workers x2] → match/decision → [apply_workers x3] → notify

Gemini calls are globally serialized by a lock (one API key → one request at a time).
analyze_workers=2 keeps threads alive to overlap DB/network I/O while Gemini processes.
Ctrl+C safe: workers check shutdown event; executors are cancelled on KeyboardInterrupt.
"""
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
from models.job import Job
from utils.logger import setup_logger
from utils.retry import with_retry
from utils.rate_limiter import wait_before_apply, record_application
from utils.shutdown import is_shutdown, request_shutdown

logger = setup_logger("pipeline")


# ─── Stage Workers ────────────────────────────────────────────────────────────

def analyze_worker(job: Job, profile: dict, settings: dict) -> Job:
    """Stage 1+2: Analyze JD + calculate match + decide (1 Gemini call)."""
    if is_shutdown():
        job.decision = "ignore"
        job.status = "skipped"
        return job

    from modules.job_analyzer import analyze_job
    from modules.match_engine import calculate_match
    from modules.decision_engine import decide
    from db.company_memory import enrich_job_from_memory

    try:
        # Check company memory first (fast, no Gemini needed)
        enrich_job_from_memory(job)

        # Build raw dict for analyzer
        raw = {
            "title": job.title, "company": job.company,
            "location": job.location, "raw_jd": job.raw_jd,
            "apply_url": job.apply_url, "platform": job.platform,
            "salary_text": job.salary_text, "experience_text": job.experience_text,
            "source_urls": job.source_urls,
        }

        # ONE combined Gemini call: analyze JD + score match simultaneously
        analysis = analyze_job(raw, profile=profile)

        # Enrich Job Object
        job.salary_min = analysis.get("salary_min")
        job.salary_max = analysis.get("salary_max")
        job.experience_required = analysis.get("experience_required", "")
        job.skills_required = analysis.get("skills_required", [])
        job.questions = analysis.get("questions", job.company_typical_questions)
        job.cover_letter_required = analysis.get("cover_letter_required", False)
        job.apply_method = analysis.get("apply_method", "")
        job.summary = analysis.get("summary", "")

        # Match result is embedded in the same analysis response
        if "match" in analysis:
            job.match_score = analysis.get("match", 0)
            job.match_reason = analysis.get("match_reason", "")
            job.missing_skills = analysis.get("missing_skills", [])
            job.strong_matches = analysis.get("strong_matches", [])
        else:
            # Fallback: separate match call only if combined call didn't return match fields
            logger.debug(f"[pipeline] Combined call missing match fields — running separate match")
            match_result = calculate_match(profile, analysis)
            job.match_score = match_result.get("match", 0)
            job.match_reason = match_result.get("reason", "")
            job.missing_skills = match_result.get("missing_skills", [])
            job.strong_matches = match_result.get("strong_matches", [])

        # Decide
        job.decision = decide(job.match_score, settings)
        job.status = "analyzed"
        job.log_event("analyzed", f"score={job.match_score} decision={job.decision}")

    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"[pipeline] analyze_worker failed for '{job.title}' @ '{job.company}': {e}\n{tb}")
        job.log_failure("analyze", str(e), tb)
        job.decision = "ignore"
        job.status = "failed"

    return job


def apply_worker(job: Job, profile: dict, settings: dict) -> Job:
    """Stage 3: Prepare + apply."""
    if is_shutdown():
        job.status = "skipped"
        return job

    from modules.resume_library import select_resume
    from modules.resume_optimizer import optimize_resume
    from modules.cover_letter_agent import generate_cover_letter
    from modules.qa_agent import generate_answers
    from modules.platform_detector import detect_platform
    from modules.plugins import get_plugin
    from modules.human_assist import trigger_human_assist
    from modules.resume_versioning import record_version
    from db.company_memory import record_application as cm_record
    from db.supabase_client import insert_application, update_job_status, insert_job, job_exists

    try:
        # Deduplication check against DB
        if job_exists(job.title, job.company):
            logger.info(f"[pipeline] Skipping duplicate: '{job.title}' @ '{job.company}'")
            job.status = "skipped"
            return job

        # Save to DB
        db_payload = job.to_db_payload()
        job.db_id = insert_job(db_payload)
        job.log_event("db_saved", f"db_id={job.db_id}")

        if job.decision == "ignore":
            update_job_status(job.db_id, "skipped")
            job.status = "skipped"
            return job

        if job.decision == "manual_review":
            from modules.notification_agent import send_manual_alert
            send_manual_alert(job.__dict__, {}, reason="manual_review")
            update_job_status(job.db_id, "manual")
            job.status = "manual"
            return job

        # ── Prepare application ──────────────────────────────────────────
        job.resume_path = select_resume(job.__dict__, profile)
        if not job.resume_path:
            logger.warning(f"[pipeline] No resume found for '{job.title}' — using manual fallback")
            trigger_human_assist(job.__dict__, "", job.answers, reason="no_resume")
            update_job_status(job.db_id, "manual")
            job.status = "manual"
            return job

        optimized = optimize_resume(profile, job.__dict__, job.resume_path)
        job.resume_variant = optimized.get("recommended_variant", "fullstack")
        job.optimized = optimized

        if job.cover_letter_required:
            job.cover_letter = generate_cover_letter(profile, job.__dict__, job.strong_matches)

        if job.questions:
            job.answers = generate_answers(job.questions, profile, job.__dict__)

        # ── Detect platform ──────────────────────────────────────────────
        platform = job.company_platform or detect_platform(job.apply_url)

        # ── Rate limiting ────────────────────────────────────────────────
        wait_before_apply(platform)

        # ── Apply via plugin (with retry) ────────────────────────────────
        plugin = get_plugin(platform)
        result = with_retry(
            plugin.apply,
            args=(job.__dict__, job.resume_path, job.cover_letter, job.answers, profile),
            attempts=3, delay=5, backoff=2, fallback="human_needed"
        )
        job.apply_result = result

        if result == "success":
            from datetime import datetime, timezone
            job.applied_at = datetime.now(timezone.utc).isoformat()
            insert_application({
                "job_id": job.db_id,
                "resume_variant": job.resume_variant,
                "cover_letter_used": bool(job.cover_letter),
                "apply_method": platform,
            })
            job.resume_version_id = record_version(job.db_id, job.resume_path, job.resume_variant)
            record_application(platform)
            update_job_status(job.db_id, "applied")
            job.status = "applied"
            job.log_event("applied", f"platform={platform}")
            cm_record(job.company, platform, job.match_score, job.questions)
            from modules.notification_agent import send_application_update
            send_application_update(job.__dict__, result)

        elif result in ("captcha", "human_needed", "partial"):
            trigger_human_assist(job.__dict__, job.resume_path, job.answers, reason=result)
            update_job_status(job.db_id, "manual")
            job.status = "manual"
            job.log_event("manual", f"reason={result}")

        else:
            # Unexpected result — treat as failure
            logger.warning(f"[pipeline] Unexpected apply result '{result}' for '{job.title}'")
            update_job_status(job.db_id, "failed")
            job.status = "failed"

    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"[pipeline] apply_worker failed for '{job.title}' @ '{job.company}': {e}\n{tb}")
        job.log_failure("apply", str(e), tb)
        job.status = "failed"
        # Attempt to update DB status if we have an ID
        if job.db_id:
            try:
                from db.supabase_client import update_job_status
                update_job_status(job.db_id, "failed")
            except Exception:
                pass

    return job


# ─── Queue Orchestrator ────────────────────────────────────────────────────────

class CareerPipeline:
    def __init__(self, profile: dict, settings: dict):
        self.profile = profile
        self.settings = settings
        # Gemini calls are serialized by the global lock in gemini_client.
        # analyze_workers=2 lets one thread overlap DB/network I/O while the other waits on Gemini.
        self.analyze_workers = settings.get("pipeline", {}).get("analyze_workers", 2)
        self.apply_workers = settings.get("pipeline", {}).get("apply_workers", 3)

    def run(self, raw_jobs: list[dict]) -> dict:
        """
        Full pipeline: raw_jobs → Job objects → analyze → apply → stats.
        Returns stats dict.
        """
        if not raw_jobs:
            logger.info("[pipeline] No jobs to process.")
            return {"found": 0, "applied": 0, "manual": 0, "skipped": 0, "failed": 0}

        jobs = [Job.from_scraper_dict(d) for d in raw_jobs]
        logger.info(f"[pipeline] Starting: {len(jobs)} jobs "
                    f"(analyze_workers={self.analyze_workers}, apply_workers={self.apply_workers})")

        stats = {"found": len(jobs), "applied": 0, "manual": 0, "skipped": 0, "failed": 0}

        # ── Stage 1+2: Analyze + Match (parallel) ────────────────────────
        analyzed_jobs: list[Job] = []
        with ThreadPoolExecutor(
            max_workers=self.analyze_workers,
            thread_name_prefix="analyze"
        ) as pool:
            futures = {
                pool.submit(analyze_worker, job, self.profile, self.settings): job
                for job in jobs
            }
            for future in as_completed(futures):
                original = futures[future]
                try:
                    result = future.result(timeout=180)
                    analyzed_jobs.append(result)
                except FuturesTimeout:
                    logger.error(
                        f"[pipeline] analyze_worker timed out for '{original.title}' "
                        f"@ '{original.company}'"
                    )
                    original.status = "failed"
                    original.decision = "ignore"
                    analyzed_jobs.append(original)
                except Exception as e:
                    logger.error(
                        f"[pipeline] analyze_worker raised for '{original.title}': {e}"
                    )
                    original.status = "failed"
                    original.decision = "ignore"
                    analyzed_jobs.append(original)

        logger.info(
            f"[pipeline] Analysis complete: {len(analyzed_jobs)} jobs processed, "
            f"{sum(1 for j in analyzed_jobs if j.status == 'failed')} failed"
        )

        if is_shutdown():
            logger.warning("[pipeline] Shutdown requested — skipping apply stage")
            return stats

        # Filter what goes to apply stage
        apply_queue = [
            j for j in analyzed_jobs
            if j.decision in ("auto_apply", "apply", "manual_review")
        ]
        skip_count = len([j for j in analyzed_jobs if j.decision == "ignore" or j.status == "failed"])
        stats["skipped"] += skip_count
        logger.info(f"[pipeline] Apply queue: {len(apply_queue)} jobs (skipping {skip_count})")

        # ── Stage 3: Apply (parallel, rate-limited) ───────────────────────
        if apply_queue:
            apply_pool = ThreadPoolExecutor(
                max_workers=self.apply_workers,
                thread_name_prefix="apply"
            )
            try:
                futures = {
                    apply_pool.submit(apply_worker, job, self.profile, self.settings): job
                    for job in apply_queue
                }
                for future in as_completed(futures):
                    if is_shutdown():
                        logger.warning("[pipeline] Shutdown — cancelling remaining apply jobs")
                        for f in futures:
                            f.cancel()
                        break
                    original = futures[future]
                    try:
                        result = future.result(timeout=600)
                        if result.status == "applied":
                            stats["applied"] += 1
                        elif result.status == "manual":
                            stats["manual"] += 1
                        elif result.status == "failed":
                            stats["failed"] += 1
                        elif result.status == "skipped":
                            stats["skipped"] += 1
                    except FuturesTimeout:
                        logger.error(
                            f"[pipeline] apply_worker timed out for '{original.title}'"
                        )
                        stats["failed"] += 1
                    except Exception as e:
                        logger.error(f"[pipeline] apply_worker raised: {e}")
                        stats["failed"] += 1
            finally:
                apply_pool.shutdown(wait=False, cancel_futures=True)

        logger.info(f"[pipeline] Complete: {stats}")
        return stats
