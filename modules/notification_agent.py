"""Module 16 — Notification Agent: Telegram notifications via Bot API."""
import os
import httpx
from utils.logger import setup_logger
from db.supabase_client import insert_notification

logger = setup_logger("notification_agent")

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _send(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logger.warning("Telegram credentials not set — skipping notification")
        return

    url = TELEGRAM_API.format(token=token)
    try:
        resp = httpx.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"Telegram send failed: {resp.text}")
        else:
            logger.debug("Telegram message sent")
            try:
                insert_notification({"type": "generic", "message": text[:500]})
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Telegram error: {e}")


def send_message(text: str) -> None:
    _send(text)


def send_morning_report(stats: dict) -> None:
    text = (
        "🌅 <b>Good morning, Harish!</b>\n"
        "📊 <b>Last run:</b>\n"
        f"• Jobs found: {stats.get('found', 0)}\n"
        f"• Auto-applied: {stats.get('applied', 0)}\n"
        f"• Manual needed: {stats.get('manual', 0)}\n"
        f"• Skipped: {stats.get('skipped', 0)}"
    )
    _send(text)
    try:
        insert_notification({"type": "morning_summary", "message": text})
    except Exception:
        pass


def send_application_update(job: dict, result: str) -> None:
    text = (
        f"✅ <b>Applied!</b>\n"
        f"Company: {job.get('company')}\n"
        f"Role: {job.get('title')}\n"
        f"Match: {job.get('match_score', '?')}%\n"
        f"Platform: {job.get('platform')}\n"
        f"URL: {job.get('apply_url', '')}"
    )
    _send(text)
    try:
        insert_notification({"type": "applied", "message": text})
    except Exception:
        pass


def send_manual_alert(job: dict, answers: dict, reason: str = "unknown") -> None:
    apply_url = job.get('apply_url', '')
    answers_text = "\n".join(f"Q: {q}\nA: {a}" for q, a in (answers or {}).items())
    alert_text = (
        f"\U0001f7e1 <b>Apply Manually</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"\U0001f3e2 <b>{job.get('company')}</b>\n"
        f"\U0001f4bc Role: {job.get('title')}\n"
        f"\U0001f4cd Location: {job.get('location', 'N/A')}\n"
        f"\U0001f3af Match: <b>{job.get('match_score', '?')}%</b>\n"
        f"\u26a0\ufe0f Reason: {reason}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"\U0001f517 <a href=\"{apply_url}\">👆 TAP HERE TO APPLY</a>\n\n"
        f"Resume variant: <code>{job.get('resume_variant', 'master')}</code>\n"
        f"I've prepared all answers below \u2193"
    )
    _send(alert_text)

    if answers_text:
        _send(f"\U0001f4cb <b>Prepared Answers:</b>\n\n{answers_text[:3000]}")

    try:
        insert_notification({"type": "manual_action", "message": alert_text})
    except Exception:
        pass


def send_weekly_digest(learning_data: dict) -> None:
    recs = learning_data.get("recommendations", [])
    top_rec = recs[0].get("action", "Keep applying!") if recs else "Keep applying!"
    top_skill = (learning_data.get("top_missing_skills") or ["N/A"])[0]

    text = (
        f"📈 <b>Weekly Summary</b>\n"
        f"Applications: {learning_data.get('total_applications', 0)}\n"
        f"Interviews: {learning_data.get('total_interviews', 0)}\n"
        f"Avg match score: {learning_data.get('avg_match_score', 0):.0f}%\n"
        f"Top missing skill: {top_skill}\n"
        f"Recommendation: {top_rec}"
    )
    _send(text)
    try:
        insert_notification({"type": "weekly_report", "message": text})
    except Exception:
        pass
