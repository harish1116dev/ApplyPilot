"""
Career Bot — Main Orchestrator
Run locally: python main.py
GitHub Actions runs this on schedule.
"""
import json
import logging
import os
import sys

from dotenv import load_dotenv
load_dotenv()

from modules.profile_brain import load_profile, validate_profile
from modules.job_scout.scout import run_all_scrapers
from modules.duplicate_detector import deduplicate
from modules.job_analyzer import analyze_job
from modules.match_engine import calculate_match
from modules.decision_engine import decide
from modules.resume_library import select_resume
from modules.resume_optimizer import optimize_resume
from modules.cover_letter_agent import generate_cover_letter
from modules.qa_agent import generate_answers
from modules.platform_detector import detect_platform
from modules.plugins import get_plugin
from modules.human_assist import trigger_human_assist
from modules.notification_agent import send_morning_report, send_application_update, send_manual_alert
from modules.analytics import get_summary_stats
from db.supabase_client import insert_job, update_job_status, insert_application, job_exists
from utils.logger import setup_logger

logger = setup_logger()


def load_settings() -> dict:
    with open(os.path.join("config", "settings.json"), encoding="utf-8") as f:
        return json.load(f)


def run_pipeline():
    logger.info("=== Career Bot Pipeline Starting ===")
    settings = load_settings()

    # Step 1: Load + validate profile
    profile = load_profile()
    valid, errors = validate_profile(profile)
    if not valid:
        logger.error(f"Profile validation failed: {errors}")
        sys.exit(1)

    # Step 2: Scrape jobs
    logger.info("Scraping jobs from all sources...")
    raw_jobs = run_all_scrapers(profile, settings)
    logger.info(f"Found {len(raw_jobs)} raw jobs")

    # Step 3: Deduplicate
    jobs = deduplicate(raw_jobs)
    logger.info(f"After dedup: {len(jobs)} unique jobs")

    stats = {"found": len(jobs), "applied": 0, "manual": 0, "skipped": 0}

    for job in jobs:
        try:
            # Skip if already in DB
            if job_exists(job.get("title", ""), job.get("company", "")):
                logger.debug(f"Already exists: {job.get('title')} @ {job.get('company')}")
                continue

            # Step 4: Analyze JD with Gemini
            job_analysis = analyze_job(job)

            # Step 5: Match profile vs job
            match_result = calculate_match(profile, job_analysis)
            job_analysis["match_score"] = match_result["match"]
            job_analysis["match_reason"] = match_result["reason"]
            job_analysis["missing_skills"] = match_result.get("missing_skills", [])

            # Step 6: Decide
            decision = decide(match_result["match"], settings)
            job_analysis["decision"] = decision

            # Save to Supabase
            db_payload = {
                "title": job_analysis.get("title", ""),
                "company": job_analysis.get("company", ""),
                "location": job_analysis.get("location", ""),
                "remote": job_analysis.get("remote", False),
                "salary_min": job_analysis.get("salary_min"),
                "salary_max": job_analysis.get("salary_max"),
                "experience_required": job_analysis.get("experience_required", ""),
                "skills_required": job_analysis.get("skills_required", []),
                "description": job_analysis.get("summary", ""),
                "apply_url": job_analysis.get("apply_url", ""),
                "apply_method": job_analysis.get("apply_method", ""),
                "platform": job_analysis.get("platform", ""),
                "source_urls": job_analysis.get("source_urls", []),
                "questions": job_analysis.get("questions", []),
                "raw_jd": job_analysis.get("raw_jd", "")[:3000],
                "match_score": match_result["match"],
                "match_reason": match_result["reason"],
                "missing_skills": match_result.get("missing_skills", []),
                "decision": decision,
                "status": "analyzed",
            }
            job_id = insert_job(db_payload)
            job_analysis["id"] = job_id

            if decision == "ignore":
                update_job_status(job_id, "skipped")
                stats["skipped"] += 1
                continue

            if decision == "manual_review":
                send_manual_alert(job_analysis, answers={}, reason="manual_review")
                update_job_status(job_id, "manual")
                stats["manual"] += 1
                continue

            # Step 7: Prepare application
            resume_path = select_resume(job_analysis, profile)
            optimized = optimize_resume(profile, job_analysis, resume_path)

            cover_letter = None
            if job_analysis.get("cover_letter_required"):
                cover_letter = generate_cover_letter(
                    profile, job_analysis,
                    strong_matches=match_result.get("strong_matches", [])
                )

            answers = {}
            if job_analysis.get("questions"):
                answers = generate_answers(job_analysis["questions"], profile, job_analysis)

            # Step 8: Detect apply platform
            platform = detect_platform(job_analysis.get("apply_url", ""))

            # Step 9: Apply via plugin
            plugin = get_plugin(platform)
            result = plugin.apply(job_analysis, resume_path, cover_letter, answers, profile)
            logger.info(f"Plugin result: {result} for {job_analysis.get('title')} @ {job_analysis.get('company')}")

            if result == "success":
                app_id = insert_application({
                    "job_id": job_id,
                    "resume_variant": optimized.get("recommended_variant", "fullstack"),
                    "cover_letter_used": cover_letter is not None,
                    "apply_method": platform,
                })
                update_job_status(job_id, "applied")
                send_application_update(job_analysis, result)
                stats["applied"] += 1

            elif result in ("captcha", "human_needed", "partial"):
                trigger_human_assist(job_analysis, resume_path, answers, reason=result)
                update_job_status(job_id, "manual")
                stats["manual"] += 1

        except Exception as e:
            logger.error(
                f"Error processing job '{job.get('title')}' @ '{job.get('company')}': {e}",
                exc_info=True,
            )
            continue

    # Step 10: Send summary report
    send_morning_report(stats)
    logger.info(f"=== Pipeline Complete: {stats} ===")


if __name__ == "__main__":
    run_pipeline()
