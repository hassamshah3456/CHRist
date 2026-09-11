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
You are a data-entry assistant reading ONE scanned page of a paper screening
register — a CRIST child-screening sheet or any similar survey form.
{language_hint}

Sheets vary: columns sit in different orders, the printed labels differ, the
questions are worded differently, the language may be Hindi, Kannada, English
or a mix, and the page may be skewed, faint or photographed at an angle. Work
out THIS page's layout first, then map what it holds onto the fixed JSON
schema below. The schema never changes, whatever the sheet looks like.

FIRST decide which of three kinds of page this is, and say so in
"sheet_type". A child's record is not always on a single page:

- "register": the classic combined sheet. One table where each row has an age
  AND that row's own yes/no answers. Return one JSON row per table line.

- "roster": a list of children with NO questions anywhere on the page. Its
  columns are typically a serial number, the child's name, an age or date of
  birth, the mother's name, a mobile number and an address. Return one JSON
  row per listed child, with q1-q4 all null.

- "questionnaire": a full page of questions about ONE child, each question
  followed by its own yes/no boxes. Return EXACTLY ONE JSON row holding that
  child's four answers. The identity is handwritten across the top of the
  page, usually a number (often circled), a name, a village and a date of
  birth. Put the number in "serial" and the date in "date_of_birth" — those
  two are what link this page back to the roster, so read them carefully. If
  the top of the page has no number leave "serial" null, and if it has no date
  leave "date_of_birth" null. Never invent either.

Return ONLY a JSON object — no markdown fences, no commentary:
{{
  "sheet_type": "register" | "roster" | "questionnaire",
  "language": "hi" | "kn" | "en" | other ISO code,
  "header": {{"place": "", "block": "", "district": "", "date": ""}},
  "rows": [
    {{
      "serial": 1,
      "age_text": "the age cell exactly as written",
      "date_of_birth": "YYYY-MM-DD or null",
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

HEADER — the location details, wherever they sit and whatever they are
labelled. On these sheets they are often one handwritten line above the table,
such as a date next to a village name, rather than a printed box:
- "place": village / gram / mohalla / locality / ward / town.
- "block": block / taluk / taluka / tehsil / mandal / area / circle.
- "district": district / zilla / jila.
- "date": the sheet's date, copied exactly as written.
Leave "" for anything the sheet does not have. Never guess a district from a
village name.

ROWS — on a register or roster page, one object per table line that has
any handwriting on it; skip blank lines. On a questionnaire page, exactly one
object. Use the sheet's own serial number, including a number written or
circled at the top of a questionnaire page. Only if nothing is numbered,
number the rows 1, 2, 3… from the top.

AGE — the hardest column, because sheets record it in different ways:
- Always copy the cell verbatim into "age_text", in its original script.
- If the cell is a DATE OF BIRTH (any format: 12/03/2019, 12-3-19, 2019-03-12,
  12 Jan 2020, १२/०३/२०१९, or a column headed DOB / जन्म तिथि / ಜನ್ಮ ದಿನಾಂಕ),
  put it in "date_of_birth" as YYYY-MM-DD and leave age_years and age_months
  null. Do NOT work out the age yourself — the server does that from the
  sheet's date.
- Otherwise fill age_years / age_months: "3 माह" / "3 ತಿಂಗಳು" / "3 months" →
  0 years 3 months; "2½" or "2.5" → 2 years 6 months; "18 months" → 1 year
  6 months; "45 days" → 0 years 1 month; "पांच साल" / "five years" → 5 years.
- A bare number with no unit is years unless the column header says otherwise.
- If the cell is unreadable, keep age_text and leave both numbers null.

QUESTIONS — a page may carry any number of yes/no screening questions,
whatever they ask. Take them in the order they appear, left to right in a
table and top to bottom on a questionnaire page, and put the first four into
q1, q2, q3, q4. If there are fewer than four, leave the rest null; if there
are more, use the first four. A roster page has none, so leave all four null
rather than guessing.
- An answer may be marked any way: a tick or cross inside or beside a bracket,
  a filled or darkened bubble, a circled word, a struck-through option, or
  "Y"/"N"/हाँ/नहीं/ಹೌದು/ಇಲ್ಲ written in by hand.
- Ticks are messy and often drift right of the bracket they belong to — judge
  by which option the mark starts in or sits closest to.
- Nothing marked, or both marked → "blank", and set "uncertain": true.

MOBILE — the contact-number column, usually filled only for positive cases.
Use "" when empty. Convert any Devanagari/Kannada digits to Western digits.

FOOTER — the person who filled the sheet: name, designation/post, mobile.

RULES:
- Transcribe text verbatim in its original script; write every NUMBER (dates,
  ages, mobiles, serials) in Western digits.
- Ignore any other columns the sheet may have — participant names, addresses,
  remarks, weights. They are deliberately not stored.
- Never invent a value. Use "" or null for anything not on the page.
- Set "uncertain": true on any row where you are not fully confident about a
  cell — an ambiguous mark, a smudged age, a doubtful digit.
"""


def _prompt(language: str) -> str:
    hints = {
        "hi": "This sheet is in Hindi.",
        "kn": "This sheet is in Kannada.",
        "en": "This sheet is in English.",
    }
    return _EXTRACTION_PROMPT.format(
        language_hint=hints.get(
            language, "The sheet's language is not known — detect it yourself."
        )
    )


def _parse_json_reply(text: str):
    """Extract the JSON payload from a model reply.

    Tolerates code fences, a sentence of preamble, and a model that answers
    with a bare array of rows instead of the object it was asked for —
    omr_normalize sorts the shape out afterwards.
    """
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    candidates = []
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            candidates.append((start, text[start:end + 1]))
    if not candidates:
        raise AiRequestError("Model reply did not contain JSON: " + text[:300])
    # If both shapes appear, the one that starts first is the whole payload.
    candidates.sort(key=lambda pair: pair[0])
    last_error = None
    for _, blob in candidates:
        try:
            return json.loads(blob)
        except json.JSONDecodeError as e:
            last_error = e
    raise AiRequestError(f"Model returned invalid JSON ({last_error}).")


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
                 mime: str = "image/jpeg"):
    """Run the vision model on one sheet image; returns the parsed JSON.

    The reply is whatever the model produced. Pass it through
    omr_normalize.normalize_extraction before storing any of it.
    """
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
