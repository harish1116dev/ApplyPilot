"""
models/job.py — The single Job Object passed through the entire pipeline.
Every module enriches this object. No more passing 20 dicts around.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid


@dataclass
class FailureRecord:
    stage: str                   # 'scrape' | 'analyze' | 'match' | 'apply'
    error: str
    traceback: str = ""
    screenshot_path: str = ""
    html_snapshot_path: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class HistoryEntry:
    event: str                   # 'found' | 'analyzed' | 'applied' | 'rejected' | 'interview'
    detail: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class Job:
    # ── Core identity (set by scraper) ──────────────────────────────────────
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    company: str = ""
    location: str = ""
    remote: bool = False
    apply_url: str = ""
    platform: str = ""           # 'naukri' | 'linkedin' | 'wellfound' | 'indeed' | 'careers_page'
    source_urls: list = field(default_factory=list)
    raw_jd: str = ""

    # ── Scraped extras ───────────────────────────────────────────────────────
    salary_text: str = ""
    experience_text: str = ""

    # ── Analysis (set by job_analyzer) ──────────────────────────────────────
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    experience_required: str = ""
    skills_required: list = field(default_factory=list)
    questions: list = field(default_factory=list)
    cover_letter_required: bool = False
    apply_method: str = ""
    deadline: Optional[str] = None
    hiring_manager: Optional[str] = None
    summary: str = ""

    # ── Stage 1: Python Fresher Filter (set by fresher_filter) ────────────────
    python_filter_verdict: str = ""  # 'pass' | 'reject' | 'uncertain'
    python_filter_reason: str = ""   # matched signal explanation
    python_filter_signal: str = ""   # exact keyword / regex that triggered

    # ── Stage 2: Gemini Verdict (set by job_analyzer) ────────────────────────
    is_fresher_job: bool = False      # Gemini confirmed fresher-eligible
    confidence: int = 0               # Gemini confidence 0-100
    jd_cached: bool = False           # True if JD was served from jd_cache

    # ── Match (set by job_analyzer via Gemini) ───────────────────────────────
    match_score: int = 0
    match_reason: str = ""
    missing_skills: list = field(default_factory=list)
    strong_matches: list = field(default_factory=list)

    # ── Decision (set by decision_engine) ───────────────────────────────────
    decision: str = "pending"    # 'auto_apply' | 'apply' | 'manual_review' | 'ignore' | 'pending'

    # ── Application prep (set by resume/cover letter/qa agents) ─────────────
    resume_path: str = ""
    resume_variant: str = ""
    resume_version_id: str = ""  # for resume versioning
    cover_letter: str = ""
    answers: dict = field(default_factory=dict)
    optimized: dict = field(default_factory=dict)

    # ── Application result (set by plugin) ──────────────────────────────────
    status: str = "found"        # 'found'|'analyzed'|'applied'|'skipped'|'manual'|'failed'
    apply_result: str = ""       # 'success'|'captcha'|'human_needed'|'partial'|'failed'
    applied_at: Optional[str] = None

    # ── Company memory ───────────────────────────────────────────────────────
    company_known: bool = False
    company_platform: str = ""
    company_typical_questions: list = field(default_factory=list)

    # ── Tracking ─────────────────────────────────────────────────────────────
    db_id: Optional[str] = None  # Supabase UUID after insert
    failure_log: list[FailureRecord] = field(default_factory=list)
    history: list[HistoryEntry] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    retry_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # ── Methods ──────────────────────────────────────────────────────────────

    def log_event(self, event: str, detail: str = "") -> None:
        self.history.append(HistoryEntry(event=event, detail=detail))

    def log_failure(
        self,
        stage: str,
        error: str,
        traceback: str = "",
        screenshot_path: str = "",
        html_snapshot_path: str = "",
    ) -> None:
        self.failure_log.append(FailureRecord(
            stage=stage,
            error=error,
            traceback=traceback,
            screenshot_path=screenshot_path,
            html_snapshot_path=html_snapshot_path,
        ))
        self.log_event("failure", f"{stage}: {error[:100]}")

    def add_screenshot(self, path: str) -> None:
        self.screenshots.append(path)

    def to_db_payload(self) -> dict:
        """Convert to flat dict for Supabase insert."""
        return {
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "remote": self.remote,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "experience_required": self.experience_required,
            "skills_required": self.skills_required,
            "description": self.summary,
            "apply_url": self.apply_url,
            "apply_method": self.apply_method,
            "platform": self.platform,
            "source_urls": self.source_urls,
            "questions": self.questions,
            "raw_jd": self.raw_jd[:3000],
            "match_score": self.match_score,
            "match_reason": self.match_reason,
            "missing_skills": self.missing_skills,
            "decision": self.decision,
            "status": self.status,
            # Stage 1 + 2 metadata
            "python_filter_verdict": self.python_filter_verdict,
            "is_fresher_job": self.is_fresher_job,
            "confidence": self.confidence,
        }

    @classmethod
    def from_scraper_dict(cls, d: dict) -> "Job":
        """Build a Job from a raw scraper dict."""
        return cls(
            title=d.get("title", ""),
            company=d.get("company", ""),
            location=d.get("location", ""),
            apply_url=d.get("apply_url", ""),
            platform=d.get("platform", ""),
            source_urls=d.get("source_urls", [d.get("apply_url", "")]),
            raw_jd=d.get("raw_jd", ""),
            salary_text=d.get("salary_text", ""),
            experience_text=d.get("experience_text", ""),
        )

    def __repr__(self) -> str:
        return f"<Job [{self.status}] {self.title!r} @ {self.company!r} score={self.match_score}>"
