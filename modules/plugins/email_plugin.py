"""Email application plugin — applies via Gmail SMTP."""
import os
import smtplib
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from utils.logger import setup_logger

logger = setup_logger("email_plugin")


def _extract_email(text: str) -> str | None:
    matches = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text or "")
    return matches[0] if matches else None


def apply(job: dict, resume_path: str, cover_letter: str, answers: dict, profile: dict) -> str:
    gmail = os.getenv("GMAIL_ADDRESS")
    app_password = os.getenv("GMAIL_APP_PASSWORD")

    if not gmail or not app_password:
        logger.error("Gmail credentials not set in .env")
        return "human_needed"

    # Try to find hiring email
    hiring_email = (
        job.get("hiring_manager_email")
        or _extract_email(job.get("raw_jd", ""))
        or _extract_email(job.get("description", ""))
    )

    if not hiring_email:
        logger.warning(f"No email found for {job.get('company')} — cannot email apply")
        return "human_needed"

    p = profile["personal"]
    subject = f"Application for {job.get('title')} — {p['name']} | Fresher | B.Tech AI & DS"

    body = f"""Dear Hiring Team,

I am writing to express my interest in the {job.get('title')} position at {job.get('company')}.

I am a fresher with a B.Tech in Artificial Intelligence and Data Science (S.A. Engineering College, 2024), with hands-on experience in full-stack development, AI/ML, and building production-ready applications.

{cover_letter or 'I believe my skills align well with your requirements and I would welcome the opportunity to contribute to your team.'}

Key highlights:
• Full-stack: React.js, Node.js, Express.js, Supabase
• AI/ML: Python, TensorFlow, scikit-learn, Gemini API
• Projects: Twitter Backend, Compass (AI news app), Fake Healthcare News Detector

LinkedIn: {p.get('linkedin', '')}
GitHub: {p.get('github', '')}
Portfolio: {p.get('portfolio', '')}

I am an immediate joiner with zero notice period.

Please find my resume attached. I would love to discuss how I can contribute to {job.get('company')}.

Best regards,
{p['name']}
{p['phone']} | {p['email']}
"""

    try:
        msg = MIMEMultipart()
        msg["From"] = gmail
        msg["To"] = hiring_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        # Attach resume
        if resume_path and os.path.exists(resume_path):
            with open(resume_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{os.path.basename(resume_path)}"',
            )
            msg.attach(part)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail, app_password)
            server.sendmail(gmail, hiring_email, msg.as_string())

        logger.info(f"Email sent to {hiring_email} for {job.get('title')} @ {job.get('company')}")
        return "success"

    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return "human_needed"
