import google.generativeai as genai
import time
import json
import os
from utils.logger import setup_logger

logger = setup_logger("gemini_client")

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.0-flash")

# Rate limiter state
_last_call_time = 0.0
_MIN_INTERVAL = 60 / 14  # 14 RPM ≈ 4.3 seconds between calls


def call_gemini(prompt: str, retries: int = 3) -> str:
    global _last_call_time

    elapsed = time.time() - _last_call_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)

    for attempt in range(retries):
        try:
            response = model.generate_content(prompt)
            _last_call_time = time.time()
            logger.debug(f"Gemini response ({len(response.text)} chars)")
            return response.text
        except Exception as e:
            if "429" in str(e):
                wait = (2 ** attempt) * 5  # 5s, 10s, 20s
                logger.warning(f"Gemini rate limited — waiting {wait}s (attempt {attempt + 1})")
                time.sleep(wait)
            else:
                logger.error(f"Gemini error: {e}")
                raise e

    raise Exception("Gemini API failed after all retries")


def call_gemini_json(prompt: str) -> dict:
    raw = call_gemini(prompt)
    # Strip markdown wrapper if present
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1]  # drop first ```json line
        clean = clean.rsplit("```", 1)[0]  # drop trailing ```
    clean = clean.strip()
    return json.loads(clean)
