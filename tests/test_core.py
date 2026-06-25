"""Basic smoke tests for core modules (no external services needed)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.profile_brain import load_profile, validate_profile, get_skills_flat, get_resume_variant_for_role
from modules.duplicate_detector import deduplicate
from modules.decision_engine import decide
from modules.resume_library import select_resume
from modules.platform_detector import detect_platform


def test_profile_loads():
    profile = load_profile()
    assert profile["personal"]["name"] == "Harish S"
    assert len(profile["target"]["roles"]) > 0
    print("✅ test_profile_loads passed")


def test_profile_validates():
    profile = load_profile()
    valid, errors = validate_profile(profile)
    assert valid, f"Validation errors: {errors}"
    print("✅ test_profile_validates passed")


def test_skills_flat():
    profile = load_profile()
    skills = get_skills_flat(profile)
    assert "React.js" in skills
    assert "Python" in skills
    print(f"✅ test_skills_flat passed — {len(skills)} skills")


def test_resume_variant_detection():
    profile = load_profile()
    assert get_resume_variant_for_role(profile, ["React", "frontend"]) == "frontend"
    assert get_resume_variant_for_role(profile, ["Python", "TensorFlow", "ML"]) == "ai"
    assert get_resume_variant_for_role(profile, ["Flutter", "Dart"]) == "flutter"
    print("✅ test_resume_variant_detection passed")


def test_deduplication():
    jobs = [
        {"title": "Software Engineer", "company": "Zoho", "apply_url": "https://a.com"},
        {"title": "Software engineer", "company": "zoho", "apply_url": "https://b.com"},  # dup
        {"title": "Frontend Developer", "company": "Freshworks", "apply_url": "https://c.com"},
    ]
    unique = deduplicate(jobs)
    assert len(unique) == 2, f"Expected 2, got {len(unique)}"
    print("✅ test_deduplication passed")


def test_decision_engine():
    settings = {
        "match_thresholds": {
            "auto_apply": 90, "apply": 80, "manual_review": 70, "ignore_below": 70
        }
    }
    assert decide(95, settings) == "auto_apply"
    assert decide(85, settings) == "apply"
    assert decide(72, settings) == "manual_review"
    assert decide(50, settings) == "ignore"
    print("✅ test_decision_engine passed")


def test_platform_detector():
    assert detect_platform("https://jobs.lever.co/company/abc") == "lever"
    assert detect_platform("https://boards.greenhouse.io/company/jobs/123") == "greenhouse"
    assert detect_platform("https://docs.google.com/forms/d/abc") == "google_form"
    assert detect_platform("https://linkedin.com/jobs/view/123") == "linkedin"
    print("✅ test_platform_detector passed")


def test_resume_selection():
    profile = load_profile()
    job_ai = {"title": "ML Engineer", "skills_required": ["Python", "TensorFlow", "scikit-learn"]}
    path = select_resume(job_ai, profile)
    assert path is not None
    print(f"✅ test_resume_selection passed — selected: {path}")


if __name__ == "__main__":
    tests = [
        test_profile_loads,
        test_profile_validates,
        test_skills_flat,
        test_resume_variant_detection,
        test_deduplication,
        test_decision_engine,
        test_platform_detector,
        test_resume_selection,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"❌ {t.__name__} FAILED: {e}")

    print(f"\n{'='*40}")
    print(f"Results: {passed}/{len(tests)} tests passed")
