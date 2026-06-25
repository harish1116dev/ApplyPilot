"""Module 10 — QA Agent: answers application questions using Gemini."""
from utils.gemini_client import call_gemini
from utils.logger import setup_logger

logger = setup_logger("qa_agent")

QA_PROMPT = """
You are helping a fresher answer this job application question honestly.
Answer in first person. Be specific, genuine, concise (max 100 words per answer).

Candidate profile:
Name: {name}
Education: B.Tech AI & Data Science, S.A. Engineering College (2024)
Skills: {skills}
Target Role: {job_title} at {company}
Expected CTC: {salary_min}-{salary_max} LPA
Notice Period: Immediate joiner

Question: {question}

Return only the answer text.
"""

HARDCODED = {
    "expected ctc": "I am flexible and open to discussion. My expectation is in the range of 4–8 LPA based on industry standards for freshers.",
    "notice period": "I am an immediate joiner with zero notice period.",
    "current ctc": "I am a fresher and currently not employed, so I do not have a current CTC.",
    "are you a fresher": "Yes, I am a fresher with hands-on project experience in full-stack development and AI/ML.",
}


def _check_hardcoded(question: str) -> str | None:
    q_lower = question.lower()
    for key, answer in HARDCODED.items():
        if key in q_lower:
            return answer
    return None


def generate_answers(questions: list[str], profile: dict, job_analysis: dict) -> dict[str, str]:
    p = profile["personal"]
    skills_flat = []
    for v in profile["skills"].values():
        skills_flat.extend(v)
    skills_str = ", ".join(skills_flat[:12])

    answers = {}
    for question in questions:
        # Try hardcoded first
        hardcoded = _check_hardcoded(question)
        if hardcoded:
            answers[question] = hardcoded
            continue

        prompt = QA_PROMPT.format(
            name=p["name"],
            skills=skills_str,
            job_title=job_analysis.get("title", ""),
            company=job_analysis.get("company", ""),
            salary_min=profile["target"]["salary_expectation_lpa"]["min"],
            salary_max=profile["target"]["salary_expectation_lpa"]["max"],
            question=question,
        )
        try:
            answer = call_gemini(prompt).strip()
            answers[question] = answer
            logger.debug(f"Answered: {question[:60]}...")
        except Exception as e:
            logger.error(f"QA agent error for question '{question[:40]}': {e}")
            answers[question] = ""

    return answers
