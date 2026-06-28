"""
core/pipeline.py — Streaming, Job-at-a-Time Pipeline.

Architecture:
  For each job (one at a time, in order):
    1. Python fresher filter (FREE, instant)
       → REJECT: skip, move to next job
    2. JD cache check
       → HIT with verdict: reuse, skip Gemini
    3. Gemini eligibility + profile match (PAID, ~7s)
       → is_fresher_job=False or low match: skip
    4. Apply immediately (don't wait for other jobs)
    5. Telegram notification on success
    → Move to next job

Why streaming instead of batch?
  - Applies to a good job IMMEDIATELY — no waiting for 130 jobs to finish
  - Naturally spaces out Gemini calls (apply takes 30-60s between calls)
  - If Ctrl+C'd, jobs already applied are done — no work lost
  - No "134 Gemini calls in 15 minutes → rate limit" problem

Gemini rate limit is still enforced by gemini_client's lock + RPM counter.
"""
import traceback
from models.job import Job
from utils.logger import setup_logger
from utils.retry import with_retry
from utils.rate_limiter import wait_before_apply, record_application
from utils.shutdown import is_shutdown, request_shutdown

logger = setup_logger("pipeline")


# ─── Per-Job Processor ────────────────────────────────────────────────────────

def process_single_job(job: Job, profile: dict, settings: dict) -> str:
    """
    Run the full pipeline for ONE job end-to-end:
      Stage 1 (filter) → Stage 2 (Gemini) → Stage 3 (apply)

    Returns the final status string:
      'python_rejected' | 'ignore' | 'manual' | 'applied' | 'failed' | 'skipped'
    """
    # ── Stage 1: Python Fresher Filter (FREE) ──────────────────────────────
    from modules.fresher_filter import filter_job

    job_dict = {
        "title": job.title,
        "company": job.company,
        "experience_text": job.experience_text,
        "raw_jd": job.raw_jd,
    }
    filter_result = filter_job(job_dict)
    job.python_filter_verdict = filter_result.verdict
    job.python_filter_reason = filter_result.reason
    job.python_filter_signal = filter_result.matched_signal

    if filter_result.verdict == "reject":
        job.decision = "ignore"
        job.status = "python_rejected"
        job.log_event("python_rejected", filter_result.reason)
        logger.debug(
            f"[pipeline] SKIP (python) '{job.title}' @ '{job.company}' "
            f"— {filter_result.reason}"
        )
        return "python_rejected"

    # ── Stage 2: Gemini Eligibility + Profile Match ─────────────────────────
    if is_shutdown():
        job.status = "skipped"
        return "skipped"

    from modules.job_analyzer import analyze_job
    from modules.decision_engine import decide_from_gemini
    from modules.jd_cache import get_cached_jd, save_jd, save_gemini_verdict
    from db.company_memory import enrich_job_from_memory

    try:
        enrich_job_from_memory(job)

        # JD cache: check for existing verdict
        cached = get_cached_jd(job.apply_url)
        if cached and cached.get("gemini_verdict"):
            analysis = cached["gemini_verdict"]
            job.jd_cached = True
            logger.info(
                f"[pipeline] CACHE HIT — '{job.title}' @ '{job.company}' "
                f"(skipping Gemini)"
            )
        else:
            # Save raw JD to cache before calling Gemini
            if job.raw_jd and job.apply_url:
                save_jd(job.apply_url, job.raw_jd)

            raw = {
                "title": job.title, "company": job.company,
                "location": job.location, "raw_jd": job.raw_jd,
                "apply_url": job.apply_url, "platform": job.platform,
                "salary_text": job.salary_text,
                "experience_text": job.experience_text,
                "source_urls": job.source_urls,
            }
            analysis = analyze_job(raw, profile=profile)

            # Persist verdict so next run reuses it
            if job.apply_url:
                save_gemini_verdict(job.apply_url, analysis)

        # Enrich Job object
        job.salary_min = analysis.get("salary_min")
        job.salary_max = analysis.get("salary_max")
        job.experience_required = (
            analysis.get("experience_requirement")
            or analysis.get("experience_required", "")
        )
        job.skills_required = analysis.get("skills_required", [])
        job.questions = analysis.get("questions", job.company_typical_questions)
        job.cover_letter_required = analysis.get("cover_letter_required", False)
        job.apply_method = analysis.get("apply_method", "")
        job.summary = analysis.get("summary", "")
        job.is_fresher_job = analysis.get("is_fresher_job", False)
        job.confidence = analysis.get("confidence", 0)
        job.match_score = analysis.get("profile_match", analysis.get("match", 0))
        job.match_reason = analysis.get("profile_reason", analysis.get("match_reason", ""))
        job.missing_skills = analysis.get("missing_skills", [])
        job.strong_matches = analysis.get("strong_matches", [])

        # Rule-based decision
        job.decision = decide_from_gemini(analysis)
        job.status = "analyzed"
        job.log_event(
            "analyzed",
            f"fresher={job.is_fresher_job} score={job.match_score} "
            f"conf={job.confidence} -> {job.decision}"
        )

    except Exception as e:
        tb = traceback.format_exc()
        logger.error(
            f"[pipeline] Gemini failed for '{job.title}' @ '{job.company}': {e}\n{tb}"
        )
        job.log_failure("analyze", str(e), tb)
        job.decision = "ignore"
        job.status = "failed"
        return "failed"

    # If Gemini says skip, stop here (no DB write, no apply)
    if job.decision == "ignore":
        logger.debug(
            f"[pipeline] IGNORE '{job.title}' @ '{job.company}' "
            f"(match={job.match_score}% conf={job.confidence}%)"
        )
        return "ignore"

    # ── Stage 3: Apply ──────────────────────────────────────────────────────
    if is_shutdown():
        job.status = "skipped"
        return "skipped"

    from modules.resume_library import select_resume
    from modules.resume_optimizer import optimize_resume
    from modules.cover_letter_agent import generate_cover_letter
    from modules.qa_agent import generate_answers
    from modules.platform_detector import detect_platform
    from modules.plugins import get_plugin
    from modules.human_assist import trigger_human_assist
    from modules.resume_versioning import record_version
    from modules.jd_cache import mark_applied
    from db.company_memory import record_application as cm_record
    from db.supabase_client import (
        insert_application, update_job_status, insert_job, job_exists,
    )

    try:
        # Deduplication check against DB
        if job_exists(job.title, job.company):
            logger.info(
                f"[pipeline] SKIP (duplicate DB) '{job.title}' @ '{job.company}'"
            )
            job.status = "skipped"
            return "skipped"

        # Save to DB
        db_payload = job.to_db_payload()
        job.db_id = insert_job(db_payload)
        job.log_event("db_saved", f"db_id={job.db_id}")

        if job.decision == "manual_review":
            from modules.notification_agent import send_manual_alert
            send_manual_alert(job.__dict__, {}, reason="manual_review")
            update_job_status(job.db_id, "manual")
            job.status = "manual"
            return "manual"

        # Prepare application
        job.resume_path = select_resume(job.__dict__, profile)
        if not job.resume_path:
            logger.warning(
                f"[pipeline] No resume for '{job.title}' — manual fallback"
            )
            trigger_human_assist(job.__dict__, "", job.answers, reason="no_resume")
            update_job_status(job.db_id, "manual")
            job.status = "manual"
            return "manual"

        optimized = optimize_resume(profile, job.__dict__, job.resume_path)
        job.resume_variant = optimized.get("recommended_variant", "fullstack")
        job.optimized = optimized

        if job.cover_letter_required:
            job.cover_letter = generate_cover_letter(
                profile, job.__dict__, job.strong_matches
            )

        if job.questions:
            job.answers = generate_answers(job.questions, profile, job.__dict__)

        # Detect platform + rate limit
        platform = job.company_platform or detect_platform(job.apply_url)
        wait_before_apply(platform)

        # Apply via plugin
        plugin = get_plugin(platform)
        result = with_retry(
            plugin.apply,
            args=(
                job.__dict__, job.resume_path,
                job.cover_letter, job.answers, profile,
            ),
            attempts=3, delay=5, backoff=2, fallback="human_needed",
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
            job.resume_version_id = record_version(
                job.db_id, job.resume_path, job.resume_variant
            )
            record_application(platform)
            update_job_status(job.db_id, "applied")
            mark_applied(job.apply_url)
            job.status = "applied"
            job.log_event("applied", f"platform={platform}")
            cm_record(job.company, platform, job.match_score, job.questions)
            from modules.notification_agent import send_application_update
            send_application_update(job.__dict__, result)
            return "applied"

        elif result in ("captcha", "human_needed", "partial"):
            trigger_human_assist(
                job.__dict__, job.resume_path, job.answers, reason=result
            )
            update_job_status(job.db_id, "manual")
            job.status = "manual"
            job.log_event("manual", f"reason={result}")
            return "manual"

        else:
            logger.warning(
                f"[pipeline] Unexpected apply result '{result}' "
                f"for '{job.title}'"
            )
            update_job_status(job.db_id, "failed")
            job.status = "failed"
            return "failed"

    except Exception as e:
        tb = traceback.format_exc()
        logger.error(
            f"[pipeline] apply failed for '{job.title}' @ '{job.company}': {e}\n{tb}"
        )
        job.log_failure("apply", str(e), tb)
        job.status = "failed"
        if job.db_id:
            try:
                from db.supabase_client import update_job_status
                update_job_status(job.db_id, "failed")
            except Exception:
                pass
        return "failed"


# ─── Orchestrator ─────────────────────────────────────────────────────────────

class CareerPipeline:
    def __init__(self, profile: dict, settings: dict):
        self.profile = profile
        self.settings = settings
        self.cache_enabled = settings.get("jd_cache", {}).get("enabled", True)

    def run(self, raw_jobs: list[dict]) -> dict:
        """
        Streaming pipeline: process each job completely end-to-end before
        moving to the next one.

          job1: filter → Gemini → apply
          job2: filter → Gemini → apply
          ...

        This ensures:
          - Applications go out immediately (no waiting for 130 Gemini calls)
          - Gemini calls are naturally spaced by apply time (30-60s each)
          - No rate-limit bursts from parallel Gemini threads
          - Ctrl+C safety: any applied jobs stay applied

        Returns stats dict.
        """
        if not raw_jobs:
            logger.info("[pipeline] No jobs to process.")
            return {
                "found": 0, "python_rejected": 0, "cache_hits": 0,
                "gemini_calls": 0, "applied": 0, "manual": 0,
                "skipped": 0, "failed": 0,
            }

        jobs = [Job.from_scraper_dict(d) for d in raw_jobs]
        total = len(jobs)
        logger.info(
            f"[pipeline] Streaming {total} jobs one-at-a-time "
            f"(jd_cache={'on' if self.cache_enabled else 'off'})"
        )

        stats = {
            "found": total,
            "python_rejected": 0,
            "cache_hits": 0,
            "gemini_calls": 0,
            "applied": 0,
            "manual": 0,
            "skipped": 0,
            "failed": 0,
        }

        for idx, job in enumerate(jobs, start=1):
            if is_shutdown():
                logger.warning(
                    f"[pipeline] Shutdown at job {idx}/{total} — stopping"
                )
                break

            logger.info(
                f"[pipeline] [{idx}/{total}] "
                f"'{job.title}' @ '{job.company}'"
            )

            status = process_single_job(job, self.profile, self.settings)

            # Track stats
            if status == "python_rejected":
                stats["python_rejected"] += 1
            elif status == "applied":
                stats["applied"] += 1
                if job.jd_cached:
                    stats["cache_hits"] += 1
                else:
                    stats["gemini_calls"] += 1
            elif status == "manual":
                stats["manual"] += 1
                if not job.jd_cached:
                    stats["gemini_calls"] += 1
            elif status == "ignore":
                stats["skipped"] += 1
                if not job.jd_cached:
                    stats["gemini_calls"] += 1
            elif status == "skipped":
                stats["skipped"] += 1
            elif status == "failed":
                stats["failed"] += 1

            # Update checkpoint after each job so a crash loses minimal work
            try:
                from utils.checkpoint import mark_job_done
                mark_job_done({"apply_url": job.apply_url, "title": job.title}, status)
            except Exception:
                pass  # checkpoint is optional — never crash the pipeline for it

        logger.info(f"[pipeline] Complete: {stats}")
        return stats
