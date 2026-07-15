"""Content Service — Gemini API Client

Uses Vertex AI global endpoint (aiplatform.googleapis.com) with ADC.
Auth: Application Default Credentials (gcloud auth application-default login).
Billing goes through GCP project, not AI Studio.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
import time
from collections import deque
from typing import Optional, Type, TypeVar

import requests

from pydantic import BaseModel

from src.core.config import get_settings

log = logging.getLogger(__name__)

TSchema = TypeVar("TSchema", bound=BaseModel)


class QuotaExhaustedError(Exception):
    """Raised when Vertex AI returns 429 and caller wants to skip retries."""


# Vertex AI global endpoint — works with ADC, billed via GCP
_VERTEX_BASE = (
    "https://aiplatform.googleapis.com/v1/projects/{project}/locations/{location}"
    "/publishers/google/models/{model}:generateContent"
)


def _vertex_project() -> str:
    project = get_settings().vertex_project_id.strip()
    if not project:
        raise RuntimeError(
            "VERTEX_PROJECT_ID is not set. Add it to .env (GCP project id)."
        )
    return project


def _vertex_location() -> str:
    return get_settings().vertex_location.strip() or "global"


# ── Rate limiter ─────────────────────────────────────────────────────────
# Sliding window per model family. Shared between call_deepseek and
# call_deepseek_vision so per-paragraph workloads stay under quota.


class _SlidingWindowLimiter:
    """Thread-safe sliding window: max N calls per 60s.

    On 429 response, caller invokes penalize() to back off the whole window.
    """

    def __init__(self, rpm: int):
        self.rpm = max(1, rpm)
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()
        self._penalty_until: float = 0.0

    def acquire(self) -> None:
        """Block until under limit. Logs if waiting."""
        while True:
            now = time.monotonic()
            with self._lock:
                # Honour penalty from prior 429
                if now < self._penalty_until:
                    sleep_for = self._penalty_until - now
                else:
                    # Drop calls older than 60s
                    cutoff = now - 60.0
                    while self._calls and self._calls[0] < cutoff:
                        self._calls.popleft()
                    if len(self._calls) < self.rpm:
                        self._calls.append(now)
                        return
                    # Sleep until oldest call ages out
                    sleep_for = 60.0 - (now - self._calls[0]) + 0.05
            if sleep_for > 0:
                if sleep_for > 1.0:
                    log.debug("RateLimiter: waiting %.1fs (%d/%d in window)",
                              sleep_for, len(self._calls), self.rpm)
                time.sleep(min(sleep_for, 5.0))

    def penalize(self, seconds: float) -> None:
        """Force a backoff after a 429. Affects all subsequent acquires."""
        with self._lock:
            self._penalty_until = max(self._penalty_until, time.monotonic() + seconds)


_PRO_LIMITER: Optional[_SlidingWindowLimiter] = None
_FLASH_LIMITER: Optional[_SlidingWindowLimiter] = None


def _limiter_for(model: str) -> _SlidingWindowLimiter:
    global _PRO_LIMITER, _FLASH_LIMITER
    s = get_settings()
    if "flash" in model.lower():
        if _FLASH_LIMITER is None or _FLASH_LIMITER.rpm != s.gemini_flash_rpm:
            _FLASH_LIMITER = _SlidingWindowLimiter(s.gemini_flash_rpm)
        return _FLASH_LIMITER
    if _PRO_LIMITER is None or _PRO_LIMITER.rpm != s.gemini_pro_rpm:
        _PRO_LIMITER = _SlidingWindowLimiter(s.gemini_pro_rpm)
    return _PRO_LIMITER


def get_deepseek_model() -> str:
    return get_settings().gemini_flash_model


def get_deepseek_model() -> str:
    return get_settings().gemini_pro_model


def get_deepseek_key() -> str:
    return get_settings().gemini_api_key


def _get_adc_token() -> str:
    """Get OAuth2 access token via gcloud ADC."""
    # Try google-auth library first
    try:
        import google.auth
        import google.auth.transport.requests
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(google.auth.transport.requests.Request())
        if creds.token:
            return creds.token
    except Exception:
        pass
    # Fallback to gcloud CLI
    try:
        result = subprocess.run(
            ["gcloud", "auth", "application-default", "print-access-token"],
            capture_output=True, text=True, timeout=10,
        )
        token = result.stdout.strip()
        if token:
            return token
    except Exception:
        pass
    raise RuntimeError("Cannot get ADC token. Run: gcloud auth application-default login")


def call_deepseek(
    prompt: str,
    *,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 4096,
    json_mode: bool = True,
    timeout: int = 300,
    max_retries: int = 3,
    thinking_budget: Optional[int] = 0,
) -> str:
    """Call Gemini via Vertex AI global endpoint with ADC. Billed via GCP.

    thinking_budget:
      0     — default. Disables thinking so maxOutputTokens is fully
              available for the actual response. Works for Gemini 3.x Flash
              and 2.5 Flash. Pro models do not support 0 — pass >=128.
      >0    — cap thinking tokens (use for Pro models).
      None  — use the model's default (NOT recommended: 3.5 Flash will spend
              all tokens thinking and return empty text).

    Raises:
        requests.HTTPError — after all retries exhausted.
        RuntimeError      — empty response or auth failure.
    """
    mdl = model or get_deepseek_model()
    url = _VERTEX_BASE.format(
        project=_vertex_project(), location=_vertex_location(), model=mdl,
    )

    gen_config: dict = {
        "temperature": temperature,
        "maxOutputTokens": max_tokens,
    }
    if thinking_budget is not None:
        gen_config["thinkingConfig"] = {"thinkingBudget": thinking_budget}
    if json_mode:
        gen_config["responseMimeType"] = "application/json"

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": gen_config,
    }

    bearer = _get_adc_token()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {bearer}",
    }

    limiter = _limiter_for(mdl)
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            limiter.acquire()
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code == 401 and attempt < max_retries - 1:
                log.warning("Gemini 401 — refreshing ADC token (attempt %d)", attempt + 1)
                bearer = _get_adc_token()
                headers["Authorization"] = f"Bearer {bearer}"
                time.sleep(1)
                continue
            if resp.status_code in (429, 500, 502, 503, 504):
                if resp.status_code == 429:
                    wait = min(15 * (2 ** attempt), 240)
                    limiter.penalize(wait)
                else:
                    wait = 2 ** (attempt + 1)
                log.warning(
                    "Gemini HTTP %s (attempt %d/%d), retry in %ds",
                    resp.status_code, attempt + 1, max_retries, wait,
                )
                time.sleep(wait)
                last_exc = requests.HTTPError(response=resp)
                continue

            if 400 <= resp.status_code < 500:
                log.error("Gemini HTTP %s body: %s", resp.status_code, resp.text[:1000])
            resp.raise_for_status()
            data = resp.json()
            candidate = data["candidates"][0]
            finish = candidate.get("finishReason", "")
            parts = candidate["content"].get("parts", [])
            text = " ".join(p.get("text", "") for p in parts).strip()
            if not text:
                raise RuntimeError("Gemini returned empty text (thinking used all tokens?)")
            if finish == "MAX_TOKENS":
                log.warning(
                    "Gemini MAX_TOKENS for model %s — returning truncated response (%d chars)",
                    mdl, len(text),
                )
            return text

        except requests.ConnectionError as exc:
            wait = 2 ** (attempt + 1)
            log.warning(
                "Gemini connection error (attempt %d/%d), retry in %ds: %s",
                attempt + 1, max_retries, wait, exc,
            )
            time.sleep(wait)
            last_exc = exc

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Gemini API: no response after all retries")


def call_deepseek_structured(
    prompt: str,
    schema: Type[TSchema],
    *,
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 4096,
    timeout: int = 300,
    max_retries: int = 3,
    thinking_budget: Optional[int] = 0,
) -> TSchema:
    """Call Gemini with JSON responseSchema enforced via Pydantic model."""
    mdl = model or get_deepseek_model()
    url = _VERTEX_BASE.format(
        project=_vertex_project(), location=_vertex_location(), model=mdl,
    )

    gen_config: dict = {
        "temperature": temperature,
        "maxOutputTokens": max_tokens,
        "responseMimeType": "application/json",
        "responseSchema": schema.model_json_schema(),
    }
    if thinking_budget is not None:
        gen_config["thinkingConfig"] = {"thinkingBudget": thinking_budget}

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": gen_config,
    }

    bearer = _get_adc_token()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {bearer}",
    }

    limiter = _limiter_for(mdl)
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            limiter.acquire()
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code == 401 and attempt < max_retries - 1:
                bearer = _get_adc_token()
                headers["Authorization"] = f"Bearer {bearer}"
                time.sleep(1)
                continue
            if resp.status_code in (429, 500, 502, 503, 504):
                if resp.status_code == 429:
                    wait = min(15 * (2 ** attempt), 240)
                    limiter.penalize(wait)
                else:
                    wait = 2 ** (attempt + 1)
                log.warning(
                    "Gemini structured HTTP %s (attempt %d/%d), retry in %ds",
                    resp.status_code, attempt + 1, max_retries, wait,
                )
                time.sleep(wait)
                last_exc = requests.HTTPError(response=resp)
                continue

            if 400 <= resp.status_code < 500:
                log.error("Gemini structured HTTP %s: %s", resp.status_code, resp.text[:1500])
            resp.raise_for_status()

            data = resp.json()
            candidate = data["candidates"][0]
            parts = candidate["content"].get("parts", [])
            text = " ".join(p.get("text", "") for p in parts).strip()
            if not text:
                raise RuntimeError("Gemini structured returned empty text")

            parsed = parse_json_response(text)
            if isinstance(parsed, dict):
                return schema.model_validate(parsed)
            raise ValueError(f"expected JSON object, got {type(parsed)}")

        except (requests.ConnectionError, ValueError, RuntimeError) as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            raise

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Gemini structured: no response after retries")


def _extract_text_from_parts(parts: list[dict]) -> str:
    """Collect JSON/text from Gemini response parts (incl. code_execution)."""
    texts: list[str] = []
    for part in parts:
        if "text" in part and part["text"]:
            texts.append(part["text"].strip())
        # Some models return execution output in codeExecutionResult
        cer = part.get("codeExecutionResult") or {}
        if isinstance(cer, dict) and cer.get("output"):
            texts.append(str(cer["output"]).strip())

    if not texts:
        return ""

    # Prefer last part that looks like JSON object
    for t in reversed(texts):
        if t.startswith("{") or t.startswith("["):
            return t
    return texts[-1]


def call_deepseek_code_execution(
    prompt: str,
    *,
    schema: Type[TSchema],
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 8192,
    timeout: int = 300,
    max_retries: int = 3,
) -> TSchema:
    """
  Call Gemini Flash with code_execution tool; parse structured JSON into Pydantic schema.
    """
    mdl = model or get_deepseek_model()
    url = _VERTEX_BASE.format(
        project=_vertex_project(), location=_vertex_location(), model=mdl,
    )

    gen_config: dict = {
        "temperature": temperature,
        "maxOutputTokens": max_tokens,
        "responseMimeType": "application/json",
        "thinkingConfig": {"thinkingBudget": 0},
    }

    payload: dict = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "tools": [{"codeExecution": {}}],
        "generationConfig": gen_config,
    }

    bearer = _get_adc_token()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {bearer}",
    }

    limiter = _limiter_for(mdl)
    last_exc: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            limiter.acquire()
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code == 401 and attempt < max_retries - 1:
                bearer = _get_adc_token()
                headers["Authorization"] = f"Bearer {bearer}"
                time.sleep(1)
                continue
            if resp.status_code in (429, 500, 502, 503, 504):
                if resp.status_code == 429:
                    wait = min(15 * (2 ** attempt), 240)
                    limiter.penalize(wait)
                else:
                    wait = 2 ** (attempt + 1)
                log.warning(
                    "Gemini code_execution HTTP %s (attempt %d/%d), retry in %ds",
                    resp.status_code, attempt + 1, max_retries, wait,
                )
                time.sleep(wait)
                last_exc = requests.HTTPError(response=resp)
                continue

            if 400 <= resp.status_code < 500:
                log.error("Gemini code_execution HTTP %s: %s", resp.status_code, resp.text[:1500])
            resp.raise_for_status()

            data = resp.json()
            candidate = data["candidates"][0]
            parts = candidate["content"].get("parts", [])
            text = _extract_text_from_parts(parts)
            if not text:
                raise RuntimeError("Gemini code_execution returned no parseable text")

            parsed = parse_json_response(text)
            if isinstance(parsed, dict):
                return schema.model_validate(parsed)
            raise ValueError(f"expected JSON object, got {type(parsed)}")

        except (requests.ConnectionError, ValueError, RuntimeError) as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            raise

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Gemini code_execution: no response after retries")


_VALID_ESCAPE_NEXT = set('"\\/bfnrtu')


def _repair_json_backslashes(text: str) -> str:
    """Walk through JSON text and double any stray backslashes that occur
    INSIDE string literals and are not followed by a valid JSON escape
    character. `\\uXXXX` requires 4 hex digits — if missing, also doubled.
    """
    out = []
    i = 0
    n = len(text)
    in_str = False
    while i < n:
        c = text[i]
        if not in_str:
            out.append(c)
            if c == '"':
                in_str = True
            i += 1
            continue
        # inside a string
        if c == '"':
            out.append(c)
            in_str = False
            i += 1
            continue
        if c != '\\':
            out.append(c)
            i += 1
            continue
        # backslash inside string — peek next
        nxt = text[i + 1] if i + 1 < n else ''
        if nxt in _VALID_ESCAPE_NEXT:
            if nxt == 'u':
                # need 4 hex digits
                hexpart = text[i + 2:i + 6]
                if len(hexpart) == 4 and all(ch in '0123456789abcdefABCDEF' for ch in hexpart):
                    out.append(text[i:i + 6])
                    i += 6
                    continue
                # bad \u — escape the backslash
                out.append('\\\\')
                i += 1
                continue
            # valid 2-char escape (\" \\ \/ \b \f \n \r \t)
            out.append(text[i:i + 2])
            i += 2
            continue
        # stray backslash — double it
        out.append('\\\\')
        i += 1
    return ''.join(out)


def parse_json_response(text: str) -> object:
    """Parse JSON from Gemini response, tolerant of common LLM glitches:
      * markdown code fences (``` or ```json)
      * trailing junk after the JSON value
      * raw LaTeX backslashes (\\frac, \\cdot, \\pi …) that are illegal in JSON
      * MAX_TOKENS truncation in the middle of an array
    """
    raw = text.strip()
    # 1. Strip markdown fence
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
    if m:
        raw = m.group(1).strip()

    # 2. Fast path — tolerate trailing garbage via raw_decode (Gemini sometimes
    #    appends repeated closing brackets or extra newlines after the object).
    try:
        obj, _ = json.JSONDecoder().raw_decode(raw)
        return obj
    except json.JSONDecodeError:
        pass

    # 3. Repair stray backslashes (LaTeX) — escape any \ not followed by a
    #    valid JSON escape: \" \\ \/ \b \f \n \r \t \uXXXX (4 hex digits).
    #    Walk the string char-by-char (only INSIDE JSON strings) so we handle
    #    runs of N backslashes deterministically without lookahead pitfalls.
    repaired = _repair_json_backslashes(raw)
    try:
        obj, _ = json.JSONDecoder().raw_decode(repaired)
        return obj
    except json.JSONDecodeError as exc:
        # Dump raw bytes around failure point for diagnosis
        ctx = repaired[max(0, exc.pos - 60):exc.pos + 60]
        log.warning(
            "parse_json_response: still invalid after repair: %s\n"
            "  near (repr): %r\n"
            "  bytes hex  : %s",
            exc, ctx, ctx.encode("utf-8", errors="replace").hex(),
        )

    # 4. Try truncated-array recovery: find the LAST complete top-level
    #    object inside an array and rebuild a valid JSON array up to that point.
    if repaired.lstrip().startswith("["):
        recovered = _recover_truncated_array(repaired)
        if recovered is not None:
            try:
                return json.loads(recovered)
            except json.JSONDecodeError:
                pass

    # Last resort — re-raise the original error
    return json.loads(raw)


def _recover_truncated_array(text: str) -> Optional[str]:
    """Scan a partially-truncated JSON array and return a valid JSON string
    containing only the fully-closed top-level objects."""
    in_str = False
    esc = False
    depth = 0          # nesting depth INSIDE the array (objects/sub-arrays)
    array_started = False
    last_good = -1     # index of '}' that closed a top-level object
    for i, ch in enumerate(text):
        if not array_started:
            if ch == "[":
                array_started = True
            continue
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0 and ch == "}":
                last_good = i
    if last_good < 0:
        return None
    return text[: last_good + 1] + "]"


def call_deepseek_vision(
    prompt: str,
    image_parts: list[dict],
    *,
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 8192,
    timeout: int = 120,
    max_retries: int = 3,
    response_mime_type: Optional[str] = None,
    skip_retry_on_429: bool = False,
) -> str:
    """Call Gemini with image/PDF parts via Vertex AI (ADC auth).

    image_parts: list of {"mimeType": "image/png", "data": "<base64>"}
    response_mime_type: e.g. "application/json" to force JSON output mode.
    Returns extracted text from the model.
    """
    mdl = model or get_deepseek_model()
    url = _VERTEX_BASE.format(
        project=_vertex_project(), location=_vertex_location(), model=mdl,
    )

    parts: list[dict] = [{"inlineData": p} for p in image_parts]
    parts.append({"text": prompt})

    gen_config: dict = {
        "temperature": temperature,
        "maxOutputTokens": max_tokens,
    }
    if response_mime_type:
        gen_config["responseMimeType"] = response_mime_type

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": gen_config,
    }

    bearer = _get_adc_token()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {bearer}",
    }

    limiter = _limiter_for(mdl)
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            limiter.acquire()
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code == 401 and attempt < max_retries - 1:
                log.warning("Gemini Vision 401 — refreshing ADC token (attempt %d)", attempt + 1)
                bearer = _get_adc_token()
                headers["Authorization"] = f"Bearer {bearer}"
                time.sleep(1)
                continue
            if resp.status_code in (429, 500, 502, 503, 504):
                if resp.status_code == 429 and skip_retry_on_429:
                    limiter.penalize(60)
                    raise QuotaExhaustedError("Vertex AI quota exhausted (429)")
                # Aggressive backoff for 429 (quota): 15s, 30s, 60s, 120s, ...
                if resp.status_code == 429:
                    wait = min(15 * (2 ** attempt), 240)
                    limiter.penalize(wait)
                else:
                    wait = 2 ** (attempt + 1)
                log.warning(
                    "Gemini Vision HTTP %s (attempt %d/%d), retry in %ds",
                    resp.status_code, attempt + 1, max_retries, wait,
                )
                time.sleep(wait)
                last_exc = requests.HTTPError(response=resp)
                continue

            resp.raise_for_status()
            data = resp.json()
            candidate = data["candidates"][0]
            parts_out = candidate["content"].get("parts", [])
            text = " ".join(p.get("text", "") for p in parts_out).strip()
            return text

        except requests.ConnectionError as exc:
            wait = 2 ** (attempt + 1)
            log.warning(
                "Gemini Vision connection error (attempt %d/%d), retry in %ds",
                attempt + 1, max_retries, wait,
            )
            time.sleep(wait)
            last_exc = exc

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Gemini Vision API: no response after all retries")
