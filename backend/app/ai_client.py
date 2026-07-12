"""AI vision client for OMR sheet extraction.

The admin configures an OpenAI-compatible endpoint (base URL + API key +
model) in Settings. Any provider that speaks the /chat/completions shape with
image input works: OpenAI, OpenRouter (which also serves Claude models),
Gemini's compat endpoint, local vLLM, …

Special case: when the base URL points at api.anthropic.com we call the
native Anthropic Messages API instead, since Anthropic doesn't expose the
OpenAI wire format.
"""
import base64
import json
import re
from typing import List, Optional

import httpx
from sqlalchemy.orm import Session

from . import payments

AI_BASE_URL_KEY = "ai_base_url"
AI_API_KEY_KEY = "ai_api_key"
AI_MODEL_KEY = "ai_model"

REQUEST_TIMEOUT = 300.0  # a full 22-row sheet can take a while at high effort


class AiConfigError(Exception):
    """AI integration is not configured or the request is invalid."""


class AiRequestError(Exception):
    """The provider rejected the request or returned garbage."""


def get_ai_config(db: Session) -> dict:
    return {
        "base_url": (payments.get_setting(db, AI_BASE_URL_KEY) or "").strip().rstrip("/"),
        "api_key": (payments.get_setting(db, AI_API_KEY_KEY) or "").strip(),
        "model": (payments.get_setting(db, AI_MODEL_KEY) or "").strip(),
    }


def set_ai_config(db: Session, base_url: str, api_key: Optional[str], model: str) -> None:
    pairs = {
        AI_BASE_URL_KEY: (base_url or "").strip().rstrip("/"),
        AI_MODEL_KEY: (model or "").strip(),
    }
    # Empty/None api_key means "keep the stored one" (the dashboard never
    # echoes the real key back, so an untouched field arrives empty).
    if api_key:
        pairs[AI_API_KEY_KEY] = api_key.strip()
    payments.set_settings(db, pairs)


def _require(cfg: dict, need_model: bool = True) -> None:
    if not cfg.get("base_url"):
        raise AiConfigError("AI base URL is not configured (Settings → AI Integration).")
    if not cfg.get("api_key"):
        raise AiConfigError("AI API key is not configured (Settings → AI Integration).")
    if need_model and not cfg.get("model"):
        raise AiConfigError("No AI model selected (Settings → AI Integration).")


def _is_anthropic(base_url: str) -> bool:
    return "api.anthropic.com" in (base_url or "")


def list_models(cfg: dict) -> List[str]:
    """Model IDs offered by the configured endpoint."""
    _require(cfg, need_model=False)
    base = cfg["base_url"]
    if _is_anthropic(base):
        url = base if base.endswith("/v1") else base + "/v1"
        resp = httpx.get(
            url + "/models",
            headers={
                "x-api-key": cfg["api_key"],
                "anthropic-version": "2023-06-01",
            },
            timeout=30.0,
        )
    else:
        resp = httpx.get(
            base + "/models",
            headers={"Authorization": "Bearer " + cfg["api_key"]},
            timeout=30.0,
        )
    if resp.status_code != 200:
        raise AiRequestError(f"Model list failed ({resp.status_code}): {resp.text[:300]}")
    data = resp.json().get("data") or []
    ids = [m.get("id") for m in data if isinstance(m, dict) and m.get("id")]
    return sorted(ids)


# ---------- extraction ----------

_EXTRACTION_PROMPT = """\
You are reading a scanned paper "CRIST screening questionnaire" register sheet.
The sheet may be in Hindi, Kannada, or English. {language_hint}

Layout of every sheet:
- A header box "location details" with: place (village/mohalla), block/area,
  district, and date (day/month/year) — all handwritten.
- A table with up to 22 numbered rows. Each row has:
  - age of the child, handwritten (may be Devanagari/Kannada digits or words,
    e.g. "५ वर्ष" = 5 years, "3 माह"/"3 ಮಾಹೆ" = 3 months, "2½" = 2 years 6 months,
    "1½ साल" = 1 year 6 months);
  - four yes/no questions. For each question the row shows "Yes ( )  No ( )"
    (हाँ/नहीं). A handwritten tick/check mark placed in or right next to one of
    the brackets marks the answer. Ticks are messy and often drift to the right
    of the bracket they belong to — judge by which bracket the mark starts in
    or is closest to;
  - a final column for a mobile number (only filled for triple-positive cases,
    usually empty).
- A footer with the filler's name (भरणकर्ता का नाम), designation (पद),
  signature, and mobile number.

Return ONLY a JSON object, no markdown fences, no commentary:
{{
  "language": "hi" | "kn" | "en",
  "header": {{"place": "", "block": "", "district": "", "date": ""}},
  "rows": [
    {{
      "serial": 1,
      "age_text": "verbatim age as written",
      "age_years": 5,
      "age_months": 0,
      "q1": "yes" | "no" | "blank",
      "q2": "yes" | "no" | "blank",
      "q3": "yes" | "no" | "blank",
      "q4": "yes" | "no" | "blank",
      "mobile": "",
      "uncertain": false
    }}
  ],
  "footer": {{"filler_name": "", "designation": "", "mobile": ""}}
}}

Rules:
- Include ONLY rows that contain any handwriting (age or at least one tick).
  Skip completely empty rows.
- Transcribe header/footer text verbatim in its original script; convert
  Devanagari/Kannada digits in numbers (dates, ages, mobiles) to Western digits.
- age_years/age_months: convert the written age. "X माह/month" → years 0,
  months X. "X½" → X years 6 months. If unreadable, set both to null and keep
  age_text.
- Set "uncertain": true on a row if you are not confident about any of its
  cells (ambiguous tick placement, unreadable age, etc.).
- Mobile numbers are 10 digits; leave "" when the column is empty.
"""


def _prompt(language: str) -> str:
    hints = {
        "hi": "This sheet is in Hindi.",
        "kn": "This sheet is in Kannada.",
        "en": "This sheet is in English.",
    }
    return _EXTRACTION_PROMPT.format(
        language_hint=hints.get(language, "Detect the language yourself.")
    )


def _parse_json_reply(text: str) -> dict:
    """Extract the JSON object from a model reply (tolerates code fences)."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise AiRequestError("Model reply did not contain JSON: " + text[:300])
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise AiRequestError(f"Model returned invalid JSON ({e}).")


def _chat_openai(cfg: dict, prompt: str, image_b64: str, mime: str) -> str:
    body = {
        "model": cfg["model"],
        "max_tokens": 8000,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{image_b64}"},
                },
                {"type": "text", "text": prompt},
            ],
        }],
    }
    resp = httpx.post(
        cfg["base_url"] + "/chat/completions",
        headers={
            "Authorization": "Bearer " + cfg["api_key"],
            "Content-Type": "application/json",
        },
        json=body,
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        raise AiRequestError(f"AI request failed ({resp.status_code}): {resp.text[:300]}")
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise AiRequestError("Unexpected AI response shape: " + json.dumps(data)[:300])


def _chat_anthropic(cfg: dict, prompt: str, image_b64: str, mime: str) -> str:
    base = cfg["base_url"]
    url = (base if base.endswith("/v1") else base + "/v1") + "/messages"
    body = {
        "model": cfg["model"],
        "max_tokens": 8000,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime,
                        "data": image_b64,
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }],
    }
    resp = httpx.post(
        url,
        headers={
            "x-api-key": cfg["api_key"],
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        raise AiRequestError(f"AI request failed ({resp.status_code}): {resp.text[:300]}")
    data = resp.json()
    if data.get("stop_reason") == "refusal":
        raise AiRequestError("The model declined to process this image.")
    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    if not parts:
        raise AiRequestError("Unexpected AI response shape: " + json.dumps(data)[:300])
    return "".join(parts)


def extract_page(cfg: dict, image_bytes: bytes, language: str = "auto",
                 mime: str = "image/jpeg") -> dict:
    """Run the vision model on one sheet image; returns the parsed dict."""
    _require(cfg)
    image_b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    prompt = _prompt(language)
    if _is_anthropic(cfg["base_url"]):
        reply = _chat_anthropic(cfg, prompt, image_b64, mime)
    else:
        reply = _chat_openai(cfg, prompt, image_b64, mime)
    return _parse_json_reply(reply)


def test_connection(cfg: dict) -> str:
    """Cheap round-trip to verify URL + key + model. Returns the model reply."""
    _require(cfg)
    if _is_anthropic(cfg["base_url"]):
        base = cfg["base_url"]
        url = (base if base.endswith("/v1") else base + "/v1") + "/messages"
        resp = httpx.post(
            url,
            headers={
                "x-api-key": cfg["api_key"],
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": cfg["model"],
                "max_tokens": 32,
                "messages": [{"role": "user", "content": "Reply with the single word OK."}],
            },
            timeout=60.0,
        )
        if resp.status_code != 200:
            raise AiRequestError(f"Test failed ({resp.status_code}): {resp.text[:300]}")
        data = resp.json()
        parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        return ("".join(parts)).strip() or "OK"
    resp = httpx.post(
        cfg["base_url"] + "/chat/completions",
        headers={
            "Authorization": "Bearer " + cfg["api_key"],
            "Content-Type": "application/json",
        },
        json={
            "model": cfg["model"],
            "max_tokens": 32,
            "messages": [{"role": "user", "content": "Reply with the single word OK."}],
        },
        timeout=60.0,
    )
    if resp.status_code != 200:
        raise AiRequestError(f"Test failed ({resp.status_code}): {resp.text[:300]}")
    try:
        return (resp.json()["choices"][0]["message"]["content"] or "").strip() or "OK"
    except (KeyError, IndexError, TypeError):
        raise AiRequestError("Unexpected test response: " + resp.text[:300])
