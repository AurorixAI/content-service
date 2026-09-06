"""
ALGO V2 — Azure DeepSeek Client
src/pipeline/deepseek_client.py

Единственная точка связи с Azure-hosted DeepSeek-V4-Pro.
Заменяет Gemini Flash/Pro для всей логики (extraction, enrichment, verify, distractors).

Ключевые функции:
  call_deepseek()            — базовый текстовый вызов
  call_deepseek_structured() — вызов с Pydantic-схемой на выходе (JSON mode)
  call_deepseek_code_execution() — DeepSeek генерирует Python/SymPy код,
                                   мы выполняем его ЛОКАЛЬНО через sandbox exec()
                                   (независимость от Google Vertex AI)
  parse_json_response()      — универсальный JSON-парсер LLM-ответов
"""
from __future__ import annotations

import json
import logging
import multiprocessing
import threading
import re
import textwrap
import time
import traceback
from typing import Any, Dict, Generic, Optional, Type, TypeVar

import requests
from pydantic import BaseModel

from src.core.config import get_settings

log = logging.getLogger(__name__)

TSchema = TypeVar("TSchema", bound=BaseModel)

# Максимальное время выполнения Python-кода локально (сек)
_LOCAL_EXEC_TIMEOUT_S = 15

# Retry-параметры для Azure DeepSeek
_MAX_RETRIES = 5
_RETRY_BACKOFF = [2, 5, 15, 30, 60]  # секунд между попытками

# Persistent HTTP sessions — one per worker thread (keep-alive).
# ``requests.Session`` is not thread-safe.  LaTeX backfill calls DeepSeek
# through ``asyncio.to_thread``, so a single process-wide session could mix
# concurrent connection-pool state and leave a worker waiting long past the
# intended request timeout.
_session_local = threading.local()


class _GlobalRequestLimiter:
    """One process-wide, retry-aware request pacer.

    Smart Verify uses one coordinator with many worker threads.  Reserving a
    slot immediately before every HTTP attempt means initial calls and all
    retries share exactly the same RPM budget; worker count cannot create a
    burst above the configured limit.
    """

    def __init__(self, requests_per_minute: int):
        if not 1 <= int(requests_per_minute) <= 250:
            raise ValueError("requests_per_minute must be between 1 and 250")
        self.requests_per_minute = int(requests_per_minute)
        self.interval = 60.0 / self.requests_per_minute
        self._lock = threading.Lock()
        self._next_slot = 0.0
        self._attempts = 0
        self._responses_429 = 0

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_slot)
            self._next_slot = slot + self.interval
            self._attempts += 1
        delay = slot - now
        if delay > 0:
            time.sleep(delay)

    def record_status(self, status_code: int) -> None:
        if status_code != 429:
            return
        with self._lock:
            self._responses_429 += 1

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "requests_per_minute": self.requests_per_minute,
                "request_attempts": self._attempts,
                "responses_429": self._responses_429,
            }


_global_request_limiter: Optional[_GlobalRequestLimiter] = None
_global_request_limiter_guard = threading.Lock()


def configure_global_request_limiter(requests_per_minute: int) -> None:
    """Configure the limiter once, before coordinator workers are started."""
    global _global_request_limiter
    limiter = _GlobalRequestLimiter(requests_per_minute)
    with _global_request_limiter_guard:
        _global_request_limiter = limiter


def global_request_limiter_stats() -> dict[str, int]:
    with _global_request_limiter_guard:
        limiter = _global_request_limiter
    if limiter is None:
        return {
            "requests_per_minute": 0,
            "request_attempts": 0,
            "responses_429": 0,
        }
    return limiter.stats()


def _acquire_global_request_slot() -> None:
    with _global_request_limiter_guard:
        limiter = _global_request_limiter
    if limiter is not None:
        limiter.acquire()


def _record_global_response(status_code: int) -> None:
    with _global_request_limiter_guard:
        limiter = _global_request_limiter
    if limiter is not None:
        limiter.record_status(status_code)


def _get_session() -> requests.Session:
    """Return this worker thread's persistent, isolated HTTP session."""
    session = getattr(_session_local, "session", None)
    if session is None:
        session = requests.Session()
        # Keep-alive + pool_connections=50, pool_maxsize=100
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=50,
            pool_maxsize=100,
            max_retries=0,  # retries управляем сами
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        _session_local.session = session
    return session


def _reset_session() -> None:
    """Discard only the calling worker's failed keep-alive connection."""
    session = getattr(_session_local, "session", None)
    if session is not None:
        session.close()
    _session_local.session = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_azure_url_and_headers() -> tuple[str, dict]:
    settings = get_settings()
    api_key = settings.azure_deepseek_api_key.strip()
    endpoint = settings.azure_deepseek_endpoint.strip()
    if not api_key or not endpoint:
        raise ValueError(
            "AZURE_DEEPSEEK_API_KEY или AZURE_DEEPSEEK_ENDPOINT не заданы в .env"
        )
    url = endpoint
    headers = {
        "api-key": api_key,
        "Authorization": f"Bearer {api_key}",  # некоторые эндпоинты требуют Bearer
        "Content-Type": "application/json",
    }
    return url, headers


def _post_with_retry(
    url: str, headers: dict, payload: dict, timeout: int = 180, max_retries: Optional[int] = None,
) -> dict:
    """POST к Azure DeepSeek с авто-retry на 429/5xx. Использует persistent Session."""
    last_exc: Exception = RuntimeError("No attempts made")
    session = _get_session()
    retry_count = max_retries if max_retries is not None else _MAX_RETRIES
    for attempt in range(retry_count):
        try:
            # This is intentionally inside the retry loop: every real HTTP
            # attempt consumes one shared coordinator slot.
            _acquire_global_request_slot()
            resp = session.post(url, headers=headers, json=payload, timeout=timeout)
            _record_global_response(resp.status_code)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                wait = _RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)] * 2
                last_exc = RuntimeError(f"HTTP 429 rate-limit")
                if attempt < retry_count - 1:
                    log.warning(
                        "DeepSeek rate-limit 429 — ожидание %ds перед попыткой %d/%d",
                        wait, attempt + 2, retry_count,
                    )
                    time.sleep(wait)
                else:
                    log.warning("DeepSeek rate-limit 429 — последняя попытка %d/%d", attempt + 1, retry_count)
                continue
            elif resp.status_code >= 500:
                wait = _RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)]
                last_exc = RuntimeError(f"HTTP {resp.status_code}")
                if attempt < retry_count - 1:
                    log.warning(
                        "DeepSeek server error %s — ожидание %ds перед попыткой %d/%d",
                        resp.status_code, wait, attempt + 2, retry_count,
                    )
                    time.sleep(wait)
                else:
                    log.warning(
                        "DeepSeek server error %s — последняя попытка %d/%d",
                        resp.status_code, attempt + 1, retry_count,
                    )
                continue
            else:
                log.error("DeepSeek API Error %s: %s", resp.status_code, resp.text[:1000])
                raise RuntimeError(f"DeepSeek API Error: {resp.status_code} — {resp.text[:300]}")
        except requests.Timeout:
            wait = _RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)]
            last_exc = TimeoutError("Request timeout")
            if attempt < retry_count - 1:
                log.warning(
                    "DeepSeek timeout — ожидание %ds перед попыткой %d/%d",
                    wait, attempt + 2, retry_count,
                )
                time.sleep(wait)
            else:
                log.warning("DeepSeek timeout — последняя попытка %d/%d", attempt + 1, retry_count)
        except requests.RequestException as e:
            wait = _RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)]
            last_exc = e
            if attempt < retry_count - 1:
                log.warning(
                    "DeepSeek connection error: %s — ожидание %ds перед попыткой %d/%d",
                    e, wait, attempt + 2, retry_count,
                )
                # Reset only this worker's failed connection. Other concurrent
                # requests keep their own independent sessions.
                _reset_session()
                session = _get_session()
                time.sleep(wait)
            else:
                log.warning(
                    "DeepSeek connection error: %s — последняя попытка %d/%d",
                    e, attempt + 1, retry_count,
                )
        except RuntimeError:
            raise
        except Exception as exc:
            log.error("DeepSeek unexpected error: %s", exc)
            raise
    raise last_exc


def _repair_json(text: str) -> str:
    """Multi-stage JSON repair for LLM output that has common formatting issues."""
    # 1. Strip trailing commas before ] or }
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    # 2. Replace literal newlines inside JSON strings with \\n
    # This regex finds strings and replaces raw newlines within them
    def _fix_string_newlines(m):
        return m.group(0).replace("\n", "\\n").replace("\r", "")
    text = re.sub(r'"(?:[^"\\]|\\.)*"', _fix_string_newlines, text)
    # 3. Fix unescaped quotes inside string values like: "value": "he said "hi""
    # Strategy: find string values with inner unescaped quotes and escape them
    text = re.sub(
        r'("(?:value|error_logic|explanation|error_type)"\s*:\s*")(.+?)("(?:\s*[,}\]]))',
        lambda m: m.group(1) + m.group(2).replace('"', '\\"') + m.group(3),
        text, flags=re.DOTALL
    )
    # 4. Fix invalid LaTeX backslash escapes inside JSON strings.
    # LaTeX uses \frac, \sqrt, \infty etc — these are not valid JSON escape sequences
    # and cause json.loads to raise "Invalid \escape". We double the backslash.
    # Only fix backslashes that are NOT already valid JSON escapes: \", \\, \/, \b, \f, \n, \r, \t, \uXXXX
    def _fix_latex_escapes(m):
        s = m.group(0)
        # Replace invalid escapes: \ followed by anything not in valid JSON escape chars
        return re.sub(r'\\(?!["\\bfnrtu/])', r'\\\\', s)
    text = re.sub(r'"(?:[^"\\]|\\.)*"', _fix_latex_escapes, text)
    return text


def _recover_truncated_array(text: str) -> Optional[str]:
    """Recover a valid JSON array from a truncated LLM response.

    Keeps only fully-closed top-level objects, which is enough for extraction
    chunks that cut off mid-item with an unterminated string.
    """
    stripped = text.lstrip()
    if not stripped.startswith("["):
        return None

    in_str = False
    esc = False
    depth = 0
    array_started = False
    last_good = -1

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
            continue
        if ch in "[{":
            depth += 1
            continue
        if ch in "]}":
            if depth > 0:
                depth -= 1
            if ch == "}" and depth == 0:
                last_good = i
            continue

    if last_good == -1:
        return None

    recovered = text[: last_good + 1].rstrip()
    if not recovered.endswith("]"):
        recovered += "]"
    return recovered


def parse_json_response(text: str) -> Any:
    """Парсит JSON из LLM-ответа, терпя markdown-обёртки и trailing-символы."""
    text = text.strip()
    # Убираем ```json...``` или ```...```
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    # Fallback: ищем первый { или [
    if not text.startswith(("{", "[")):
        start_brace = text.find("{")
        start_bracket = text.find("[")
        starts = [s for s in (start_brace, start_bracket) if s >= 0]
        if starts:
            text = text[min(starts):]

    is_array = text.startswith("[")

    # Обрезаем до последней } или ]
    end_brace = text.rfind("}")
    end_bracket = text.rfind("]")
    end = max(end_brace, end_bracket)
    if end >= 0:
        text = text[:end + 1]

    if is_array and not text.endswith("]"):
        text += "]"

    # Stage 1: Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Stage 2: Apply multi-stage repair and retry
    try:
        repaired = _repair_json(text)
        return json.loads(repaired)
    except json.JSONDecodeError as e:
        if text.startswith("["):
            recovered = _recover_truncated_array(text)
            if recovered is not None:
                try:
                    return json.loads(recovered)
                except json.JSONDecodeError:
                    pass
        raise e



# ── Core API ──────────────────────────────────────────────────────────────────

def call_deepseek(
    prompt: str,
    system_prompt: str = "You are a helpful AI assistant.",
    temperature: float = 0.1,
    max_tokens: int = 8192,
    response_format: Optional[dict[str, str]] = None,
    timeout: int = 180,
    model: Optional[str] = None,
    thinking_budget: Optional[int] = None,  # ignored
    **kwargs,  # поглощаем legacy Gemini kwargs (model=, api_key=, thinking_budget=)
) -> str:
    """Базовый вызов Azure DeepSeek-V4-Pro. Возвращает текст ответа."""
    url, headers = _get_azure_url_and_headers()
    payload: Dict[str, Any] = {
        # Honour the explicit model passed by a caller.  The previous
        # implementation silently ignored this parameter and only happened to
        # use the desired model because the environment default matched it.
        "model": model or kwargs.get("model") or get_deepseek_model(),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        payload["response_format"] = response_format

    result = _post_with_retry(
        url,
        headers,
        payload,
        timeout=timeout,
        max_retries=kwargs.get("max_retries"),
    )
    return result["choices"][0]["message"]["content"]


def call_deepseek_structured(
    prompt: str,
    schema: Type[TSchema],
    *,
    system_prompt: str = "You are a precise mathematical solver. Return ONLY valid JSON.",
    model: Optional[str] = None,  # ignored, kept for API compat
    temperature: float = 0.0,
    max_tokens: int = 8192,
    timeout: int = 180,
    max_retries: int = 3,
    thinking_budget: Optional[int] = None,  # ignored for DeepSeek, kept for compat
    **kwargs,
) -> TSchema:
    """
    Вызов DeepSeek с обязательным JSON-ответом, валидируется через Pydantic.
    Заменяет Gemini call_deepseek_structured (был на Vertex AI).
    """
    url, headers = _get_azure_url_and_headers()

    # Встраиваем JSON Schema в системный промпт для принудительного формата
    json_schema = schema.model_json_schema()
    schema_str = json.dumps(json_schema, ensure_ascii=False, indent=2)
    system_with_schema = (
        f"{system_prompt}\n\n"
        f"Ответ СТРОГО в формате JSON по этой схеме:\n```json\n{schema_str}\n```\n"
        "Только JSON, без markdown-обёртки."
    )

    payload: Dict[str, Any] = {
        "model": model or get_deepseek_model(),
        "messages": [
            {"role": "system", "content": system_with_schema},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }

    last_exc: Exception = RuntimeError("No attempts")
    for attempt in range(max_retries):
        try:
            result = _post_with_retry(
                url, headers, payload, timeout=timeout, max_retries=1,
            )
            text = result["choices"][0]["message"]["content"]
            parsed = parse_json_response(text)
            if isinstance(parsed, dict):
                return schema.model_validate(parsed)
            raise ValueError(f"Ожидался JSON-объект, получен: {type(parsed)}")
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                wait = _RETRY_BACKOFF[attempt]
                log.warning(
                    "call_deepseek_structured attempt %d/%d failed: %s — retry in %ds",
                    attempt + 1, max_retries, exc, wait,
                )
                time.sleep(wait)
            else:
                log.error("call_deepseek_structured exhausted retries: %s", exc)
    raise last_exc


# ── Code Execution (локальный sandbox) ────────────────────────────────────────

_SYMPY_SANDBOX_IMPORTS = textwrap.dedent("""\
    import sympy
    from sympy import (
        symbols, solve, simplify, expand, factor, sqrt, Rational, pi, E, oo,
        Eq, Ne, Lt, Le, Gt, Ge, Abs, And, Or, Not, Interval, Union, FiniteSet,
        latex, Symbol, Integer, Float, sin, cos, tan, log, exp,
        Piecewise, ceiling, floor, Mod, factorial, binomial,
        Matrix, Poly, Derivative, Integral, limit, diff, integrate,
    )
    x, y, z, n, a, b, c, t, k, m = symbols('x y z n a b c t k m', real=True)
    result = {}
""")

_CODE_BLOCK_RE = re.compile(
    r"```(?:python|py)?\s*([\s\S]*?)```",
    re.IGNORECASE,
)


def _extract_python_code(llm_text: str) -> str:
    """Извлекает первый Python-блок из ответа LLM."""
    m = _CODE_BLOCK_RE.search(llm_text)
    if m:
        return m.group(1).strip()
    # Нет блока — весь текст (если похоже на Python)
    if "import sympy" in llm_text or "from sympy" in llm_text or "solve(" in llm_text:
        return llm_text.strip()
    return ""


def _sandbox_child(full_code: str, result_queue) -> None:
    """Execute untrusted generated math code in a disposable process."""
    namespace: dict = {}
    try:
        exec(full_code, namespace)  # noqa: S102
        result_queue.put(("ok", namespace.get("result")))
    except Exception as exc:
        result_queue.put(("error", f"{type(exc).__name__}: {exc}"))


def _run_code_in_sandbox(code: str) -> dict:
    """
    Выполняет Python-код в изолированном namespace с SymPy.
    Возвращает namespace после выполнения (для чтения result).
    Timeout реализован отдельным процессом: зависший SymPy вызов нельзя
    надёжно прервать из Python-thread, а coordinator не должен оставаться
    живым после истечения лимита.

    БЕЗОПАСНОСТЬ: код генерирован DeepSeek на основе математической задачи.
    Импорты ограничены предустановленным _SYMPY_SANDBOX_IMPORTS.
    """
    full_code = _SYMPY_SANDBOX_IMPORTS + "\n" + code
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue(maxsize=1)
    process = context.Process(target=_sandbox_child, args=(full_code, result_queue))
    process.start()
    process.join(timeout=_LOCAL_EXEC_TIMEOUT_S)

    if process.is_alive():
        process.terminate()
        process.join(timeout=2)
        raise TimeoutError(f"Код не выполнился за {_LOCAL_EXEC_TIMEOUT_S}с (бесконечный цикл?)")
    if result_queue.empty():
        raise RuntimeError(f"Sandbox завершился без result (exit={process.exitcode})")
    status, payload = result_queue.get_nowait()
    if status != "ok":
        raise RuntimeError(payload)
    return {"result": payload}


def _prompt_for_code_generation(task_prompt: str) -> str:
    """Системный промпт для DeepSeek: сгенерировать Python/SymPy-код решения."""
    return textwrap.dedent(f"""\
        Ты — точный математический решатель. Напиши Python-код с SymPy для решения задачи.

        ТРЕБОВАНИЯ К КОДУ:
        1. Используй только стандартный Python + SymPy (уже импортированы: symbols, solve, simplify и др.)
        2. Последние строки кода должны присвоить результат переменной `result`:
           result = {{
               "sympy_compatible_string": "...",  # SymPy-выражение для проверки
               "absolute_correct_answer": "..."   # финальный ответ в школьной записи
           }}
        3. Для `absolute_correct_answer` — школьная запись (не LaTeX \\frac, а 3/4)
        4. Для нескольких корней — разделяй через '; ' (пример: 'x = 2; x = -3')
        5. Для неравенств — запись типа 'x > 3' или 'x ∈ (3; +∞)'

        ЗАПРЕЩЕНО:
        - Выводить через print() — только присвоение result
        - Бесконечные циклы
        - Сторонние импорты (requests, os, sys и т.п.)

        Задача:
        {task_prompt}

        Верни ТОЛЬКО блок Python-кода в ```python ... ```.
    """)


def call_deepseek_code_execution(
    prompt: str,
    *,
    schema: Type[TSchema],
    model: Optional[str] = None,  # ignored, kept for API compat
    temperature: float = 0.0,
    max_tokens: int = 8192,
    timeout: int = 300,
    max_retries: int = 3,
) -> TSchema:
    """
    DeepSeek генерирует Python/SymPy код → выполняем ЛОКАЛЬНО → парсим результат.

    Это полная замена Gemini Vertex AI code_execution tool.
    Архитектура:
      1. DeepSeek получает задачу и возвращает Python-код (SymPy)
      2. Код выполняется локально в sandbox с SymPy
      3. Переменная `result` в namespace парсится в Pydantic schema

    Преимущества перед Gemini code_execution:
      - Нет зависимости от Google Vertex AI / ADC credentials
      - Детерминированное математическое выполнение через SymPy
      - Полный контроль над sandbox (timeout, allowed imports)
    """
    code_gen_prompt = _prompt_for_code_generation(prompt)
    url, headers = _get_azure_url_and_headers()

    payload: Dict[str, Any] = {
        "model": model or get_deepseek_model(),
        "messages": [
            {
                "role": "system",
                "content": (
                    "Ты — математический программист. "
                    "Пиши только корректный Python/SymPy код, решающий задачу. "
                    "Строго следуй инструкции по формату result = {{...}}."
                ),
            },
            {"role": "user", "content": code_gen_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    last_exc: Exception = RuntimeError("No attempts")

    for attempt in range(max_retries):
        try:
            # Шаг 1: Получаем Python-код от DeepSeek
            resp_data = _post_with_retry(
                url, headers, payload, timeout=timeout, max_retries=1,
            )
            llm_text = resp_data["choices"][0]["message"]["content"]
            python_code = _extract_python_code(llm_text)

            if not python_code:
                raise ValueError(
                    f"DeepSeek не вернул Python-блок (attempt {attempt + 1}). "
                    f"Ответ: {llm_text[:300]}"
                )

            log.debug("DeepSeek code (attempt %d):\n%s", attempt + 1, python_code[:800])

            # Шаг 2: Выполняем код локально
            namespace = _run_code_in_sandbox(python_code)
            result = namespace.get("result")

            if not isinstance(result, dict):
                raise ValueError(
                    f"После выполнения кода `result` не dict: {type(result)} = {result}"
                )

            # Шаг 3: Валидируем через Pydantic
            return schema.model_validate(result)

        except TimeoutError as exc:
            log.warning(
                "Code execution timeout (attempt %d/%d): %s",
                attempt + 1, max_retries, exc,
            )
            last_exc = exc
            # При timeout просим DeepSeek упростить код
            payload["messages"].append({
                "role": "assistant",
                "content": llm_text if "llm_text" in dir() else "",
            })
            payload["messages"].append({
                "role": "user",
                "content": "Код завис. Перепиши проще, избегай тяжёлых вычислений.",
            })
            time.sleep(_RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)])

        except Exception as exc:
            log.warning(
                "code_execution attempt %d/%d failed: %s\n%s",
                attempt + 1, max_retries, exc,
                traceback.format_exc(limit=5),
            )
            last_exc = exc
            if attempt < max_retries - 1:
                # Сообщаем DeepSeek об ошибке для следующей попытки
                err_msg = f"Ошибка выполнения кода: {type(exc).__name__}: {exc}"
                if len(payload["messages"]) < 8:  # не раздуваем диалог
                    payload["messages"].append({
                        "role": "assistant",
                        "content": llm_text if "llm_text" in dir() else "",
                    })
                    payload["messages"].append({
                        "role": "user",
                        "content": f"{err_msg}\nИсправь код и попробуй снова.",
                    })
                time.sleep(_RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)])
            else:
                log.error("call_deepseek_code_execution exhausted %d retries", max_retries)

    raise last_exc


# ── Legacy stubs ──────────────────────────────────────────────────────────────

def get_deepseek_key() -> str:
    return get_settings().azure_deepseek_api_key.strip()


def get_deepseek_model() -> str:
    """Возвращает имя модели DeepSeek."""
    return get_settings().azure_deepseek_model or "deepseek-v4-flash"


def call_deepseek_vision(*args, **kwargs):
    raise NotImplementedError(
        "Vision задачи решает Mistral Document AI (AzureMistralOCR). "
        "Не используй call_deepseek_vision напрямую."
    )
