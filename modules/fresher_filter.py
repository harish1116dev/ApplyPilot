"""
modules/fresher_filter.py — Stage 1: Free Python Fresher Filter.

Zero Gemini calls. Pure regex + keyword matching.
Runs on every job BEFORE the Gemini analysis stage.

Goal: reject 70-80% of jobs that are clearly NOT fresher roles,
      so Gemini only spends API quota on genuinely promising candidates.

Verdict logic (in order):
  1. Check ACCEPT signals first (explicit fresher/entry-level markers).
     → If any found: PASS immediately (do not risk blocking a valid job).
  2. Check REJECT signals (senior/lead/high-experience markers).
     → If any found: REJECT.
  3. Neither found → UNCERTAIN → sent to Gemini as a safe fallback.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from utils.logger import setup_logger

logger = setup_logger("fresher_filter")


# ─── Signal Definitions ───────────────────────────────────────────────────────

# Keywords that CONFIRM a fresher role (case-insensitive, whole-word match)
_ACCEPT_KEYWORDS = [
    "fresher", "freshers", "fresh graduate", "fresh graduates",
    "entry level", "entry-level",
    "graduate engineer trainee", "graduate trainee", "graduate engineer",
    "get ", "get,",          # Graduate Engineer Trainee abbreviation (note trailing space/comma)
    "2025 batch", "2026 batch", "2024 batch",
    "campus hire", "campus recruitment", "campus drive",
    "trainee", "associate engineer", "junior engineer",
    "0 years experience", "0 year experience",
    "no experience required", "no prior experience",
    "recent graduate", "recent graduates",
    "any graduate", "any graduation",
    "b.tech fresher", "be fresher", "engineering fresher",
]

# Regex patterns that CONFIRM a fresher-eligible experience range.
# Matches things like: 0-1 year, 0–2 years, 0 to 3 years, 0 - 1 years, etc.
_ACCEPT_EXP_PATTERNS = [
    r"\b0\s*[-–to]\s*[1-3]\s*years?\b",      # 0-1, 0-2, 0-3, 0 to 2, 0–3
    r"\b0\s*[-–to]\s*0\s*years?\b",           # 0-0 years (no experience)
    r"\b0\s*years?\s*(experience|exp)?\b",    # 0 years, 0 yrs experience
]

# Keywords that REJECT a non-fresher role (case-insensitive)
_REJECT_KEYWORDS = [
    "senior", "sr.", "sr ",
    "lead engineer", "lead developer", "lead developer", "tech lead", "team lead",
    "principal", "staff engineer", "staff developer",
    "architect", "solution architect", "software architect",
    "manager", "engineering manager", "delivery manager", "project manager",
    "director", "vp of", "vice president", "head of engineering", "head of",
    "cto", "cxo",
    "10+ years", "9+ years", "8+ years", "7+ years", "6+ years", "5+ years",
    "10 years", "9 years", "8 years", "7 years",
]

# Regex patterns that REJECT based on experience requirement.
# Minimum experience starts at 1 year or more.
#
# Patterns covered:
#   "3+ years", "4+ years", "5-7 years", "minimum 2 years", "at least 3 years"
#   "2-4 years", "1.5 - 3 years", "1 year of experience" (1-year min)
#
# NOT covered (intentionally accepted): "0-1 years", "0-3 years"
_REJECT_EXP_PATTERNS = [
    # N+ years where N >= 3
    r"\b[3-9]\d*\s*\+\s*years?\b",
    # Range patterns: X-Y or X to Y where minimum (X) >= 2
    # Catches: 2-4, 3-5, 4-6, 2 to 4, etc.
    r"\b([2-9]|\d{2,})\s*[-–to]+\s*\d+\s*years?\b",
    # Minimum / at least X years where X >= 2
    r"\bminimum\s+([2-9]|\d{2,})\s*years?\b",
    r"\bat\s+least\s+([2-9]|\d{2,})\s*years?\b",
    r"\b([2-9]|\d{2,})\s*years?\s+(of\s+)?(experience|exp)\b",
]


# ─── Result Object ────────────────────────────────────────────────────────────

@dataclass
class FilterResult:
    verdict: str            # "pass" | "reject" | "uncertain"
    reason: str             # Human-readable explanation
    matched_signal: str     # The exact keyword / pattern that triggered
    confidence: int         # 0-100 how confident the filter is


# ─── Core Logic ───────────────────────────────────────────────────────────────

def _build_search_text(job: dict) -> str:
    """Concatenate all searchable fields into a single lowercase string."""
    parts = [
        job.get("title", ""),
        job.get("experience_text", ""),
        job.get("raw_jd", ""),
        job.get("description", ""),
        job.get("requirements", ""),
        job.get("qualifications", ""),
        job.get("responsibilities", ""),
    ]
    return " ".join(p for p in parts if p).lower()


def _check_accept(text: str) -> Optional[FilterResult]:
    """Return a PASS result if an accept signal is found, else None."""
    # Keyword match
    for kw in _ACCEPT_KEYWORDS:
        if kw.lower() in text:
            return FilterResult(
                verdict="pass",
                reason=f"Found fresher accept keyword: '{kw}'",
                matched_signal=kw,
                confidence=92,
            )

    # Regex match
    for pattern in _ACCEPT_EXP_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return FilterResult(
                verdict="pass",
                reason=f"Found fresher experience pattern: '{m.group()}'",
                matched_signal=m.group(),
                confidence=95,
            )

    return None


def _check_reject(text: str) -> Optional[FilterResult]:
    """Return a REJECT result if a reject signal is found, else None."""
    # Keyword match
    for kw in _REJECT_KEYWORDS:
        if kw.lower() in text:
            return FilterResult(
                verdict="reject",
                reason=f"Found senior/high-experience keyword: '{kw}'",
                matched_signal=kw,
                confidence=90,
            )

    # Regex match
    for pattern in _REJECT_EXP_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            # Extra safety: don't reject if the SAME region also had "0-" before it
            # e.g. "0-2 years or 3+ years" — we still want to accept these
            # This is handled by checking accept first (accept takes priority).
            return FilterResult(
                verdict="reject",
                reason=f"Found high-experience requirement: '{m.group()}'",
                matched_signal=m.group(),
                confidence=88,
            )

    return None


def filter_job(job: dict) -> FilterResult:
    """
    Run the Stage 1 filter on a single job dict.

    Priority order:
      1. Accept signals (explicit fresher markers) → PASS immediately
      2. Reject signals (senior/experience markers) → REJECT
      3. Neither → UNCERTAIN (safe: still sent to Gemini)
    """
    text = _build_search_text(job)

    # Step 1: Accept signals take priority — never block a potentially valid job
    accept_result = _check_accept(text)
    if accept_result:
        logger.debug(
            f"[fresher_filter] PASS '{job.get('title')}' @ '{job.get('company')}' "
            f"— {accept_result.reason}"
        )
        return accept_result

    # Step 2: Reject signals
    reject_result = _check_reject(text)
    if reject_result:
        logger.debug(
            f"[fresher_filter] REJECT '{job.get('title')}' @ '{job.get('company')}' "
            f"— {reject_result.reason}"
        )
        return reject_result

    # Step 3: Ambiguous — let Gemini decide
    logger.debug(
        f"[fresher_filter] UNCERTAIN '{job.get('title')}' @ '{job.get('company')}' "
        f"— no clear signal, forwarding to Gemini"
    )
    return FilterResult(
        verdict="uncertain",
        reason="No clear fresher or senior signals found",
        matched_signal="",
        confidence=50,
    )


def run_batch(jobs: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """
    Run Stage 1 filter on a batch of job dicts.

    Returns:
        gemini_queue  — jobs that should be sent to Gemini (pass + uncertain)
        rejected      — jobs that were hard-rejected by Python
        stats         — breakdown dict for logging
    """
    gemini_queue: list[dict] = []
    rejected: list[dict] = []

    counts = {"pass": 0, "reject": 0, "uncertain": 0}

    for job in jobs:
        result = filter_job(job)
        # Attach filter metadata directly onto the job dict
        job["_python_filter_verdict"] = result.verdict
        job["_python_filter_reason"] = result.reason
        job["_python_filter_signal"] = result.matched_signal

        counts[result.verdict] += 1

        if result.verdict == "reject":
            rejected.append(job)
        else:
            gemini_queue.append(job)

    total = len(jobs)
    reject_pct = (counts["reject"] / total * 100) if total else 0
    logger.info(
        f"[fresher_filter] {total} jobs → "
        f"PASS={counts['pass']} | UNCERTAIN={counts['uncertain']} | "
        f"REJECT={counts['reject']} ({reject_pct:.0f}% filtered out) "
        f"→ {len(gemini_queue)} forwarded to Gemini"
    )

    stats = {
        "total": total,
        "pass": counts["pass"],
        "uncertain": counts["uncertain"],
        "python_rejected": counts["reject"],
        "forwarded_to_gemini": len(gemini_queue),
        "filter_rate_pct": round(reject_pct, 1),
    }

    return gemini_queue, rejected, stats
