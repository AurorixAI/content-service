"""Content Service — Distractor Generation

All answer types → Gemini generates context-aware student mistakes.
Smart Verify calls generate_distractors(verify_answer=False) — isolated teacher step.
Post-generation: distractor_gate L1–L4 validation with retry.
"""
from __future__ import annotations

import logging
import re

from src.core.config import get_settings
from src.pipeline.answer_verify import _normalize_ineq_symbols
from src.pipeline.distractor_gate import (
    _extract_relation_core,
    effective_distractor_answer_type,
    validate_distractor_set,
)
from src.pipeline.answer_sympy_gate import _comparison_answer_key
from src.pipeline.models import ExtractedTask

log = logging.getLogger(__name__)

_NUMERIC_TYPES = {"exact_number", "decimal"}
_TEXT_TYPES = {"text", "open_text", "coordinate"}



# Short single-word answers that are physically binary (only 1 wrong answer possible)
_BINARY_ANSWER_PATTERNS = {
    "рациональным", "иррациональным", "рациональное", "иррациональное",
    "да", "нет", "верно", "неверно", "true", "false",
}
_COMPARISON_SIGN_QUESTION_RE = re.compile(
    r"(?:знак\s+сравнен|сравните|поставьте\s+знак|"
    r"какой\s+знак|[A-Za-zА-Яа-я]\s*\.\.\.\s*[A-Za-zА-Яа-я0-9])",
    re.I,
)


def _is_comparison_sign_task(question: str, answer: str, atype: str) -> bool:
    if (atype or "").lower() != "exact_number":
        return False
    return bool(_COMPARISON_SIGN_QUESTION_RE.search(question or "")) and bool(
        _comparison_answer_key(answer, question)
    )


def _is_binary_answer(answer: str, atype: str) -> bool:
    """Returns True if this answer is binary (yes/no, rational/irrational).
    For these, minimum 1 distractor is acceptable."""
    if atype not in ("multiple_choice", "text"):
        return False
    a = (answer or "").strip().lower()
    if a in _BINARY_ANSWER_PATTERNS:
        return True
    # Short single-word answers ≤ 15 chars with no spaces
    if len(a) <= 15 and " " not in a and re.match(r"^[а-яёa-z]+$", a):
        return True
    return False


def _required_distractor_count(
    answer: str = "",
    atype: str = "",
    question: str = "",
) -> int:
    """Target distractor count (ideal)."""
    if _is_comparison_sign_task(question, answer, atype):
        return 2
    return get_settings().distractor_gate_min_count


def _minimum_distractor_count(
    answer: str = "",
    atype: str = "",
    question: str = "",
) -> int:
    """Minimum acceptable distractors. Binary answers (да/нет etc.) need only 1."""
    if _is_comparison_sign_task(question, answer, atype):
        return 2
    if _is_binary_answer(answer, atype):
        return 1
    return get_settings().distractor_gate_min_acceptable


def _has_distractors(task: ExtractedTask) -> bool:
    meta = task.distractor_meta
    return isinstance(meta, list) and len(meta) > 0


def _has_complete_distractors(task: ExtractedTask) -> bool:
    meta = task.distractor_meta
    answer = getattr(task, "answer_raw", "") or ""
    atype = getattr(task, "answer_type", "") or ""
    need = _minimum_distractor_count(answer, atype, task.question_text or "")
    return isinstance(meta, list) and len(meta) >= need


def _clear_distractors(task: ExtractedTask) -> None:
    task.distractor_meta = []
    task.distractors = []



def _build_distractor_prompt(
    task: ExtractedTask,
    answer: str,
    *,
    rejected: list[dict] | None = None,
) -> str:
    declared_type = (task.answer_type or "exact_number").lower()
    atype = effective_distractor_answer_type(
        task.question_text or "", answer, declared_type
    )
    reject_block = ""
    if rejected:
        lines = [
            f"- {r.get('value', '?')}: {r.get('gate_reason', 'invalid')}"
            for r in rejected[:8]
        ]
        reject_block = (
            "\nРанее отклонённые варианты (не повторяй):\n"
            + "\n".join(lines)
            + "\n"
        )

    numeric_hint = ""
    if atype in _NUMERIC_TYPES:
        numeric_hint = "- Каждый дистрактор — конкретное число\n"

    comparison_sign_task = _is_comparison_sign_task(
        task.question_text or "",
        answer,
        declared_type,
    )
    if comparison_sign_task:
        numeric_hint = (
            "- Ответом является только знак сравнения. Создай ровно два "
            "уникальных неверных знака из набора <, >, =; никаких слов или "
            "выражений в value.\n"
        )

    type_hint = ""
    if atype in _TEXT_TYPES:
        type_hint = (
            "- Тип text: каждый дистрактор — другое неверное обоснование "
            "(разный шаг/ошибка), не перефраз одной и той же фразы\n"
            "- Если ответ да/нет или доказано/не доказано: варианты должны опираться "
            "на разные математические заблуждения\n"
        )
    elif atype == "inequality":
        type_hint = (
            "- Тип inequality: ядро — другое неверное неравенство (другой знак, граница "
            "или переменная), а не то же неравенство с иным «потому что»\n"
        )

    settings = get_settings()
    min_count = _required_distractor_count(answer, atype, task.question_text or "")
    batch_size = max(min_count, settings.distractor_gate_llm_batch_size)
    if comparison_sign_task:
        batch_size = min_count

    return (
        "Ты — опытный учитель математики. "
        f"Придумай ровно {batch_size} правдоподобных НЕВЕРНЫХ ответа — типичные ошибки ученика.\n\n"
        f"Задача: {task.question_text}\n"
        f"Правильный ответ: {(_comparison_answer_key(answer, task.question_text or '') if comparison_sign_task else answer)}\n"
        f"{reject_block}\n"
        "Требования:\n"
        f"{numeric_hint}"
        f"{type_hint}"
        "- Каждый дистрактор математически НЕВЕРЕН для этой задачи\n"
        "- Ошибка должна быть реалистичной (типичная ошибка на шаге решения)\n"
        f"{_ERROR_LOGIC_REQUIREMENTS}"
        "- Ни один дистрактор не равен правильному ответу\n"
        "- Дистракторы должны отличаться друг от друга\n"
    )


_DET_ERR = "Типичная ошибка при сравнении или неверный знак неравенства"

# Shared with LLM distractor prompts — pedagogy-quality error_logic (gate L4 still min 10).
_ERROR_LOGIC_REQUIREMENTS = (
    "- error_logic: конкретная школьная ошибка на КОНКРЕТНОМ шаге решения "
    "(минимум 25 символов)\n"
    "- error_logic должен объяснять, как ученик получил ИМЕННО это value, "
    "а не другое число или формулировку\n"
    "- Пересчитай всю указанную в error_logic арифметику: ошибочное правило может "
    "быть неверным, но каждое последующее вычисление обязано действительно привести "
    "к указанному value\n"
    "- Нельзя сначала получить одно число, а затем без точного действия объявить "
    "другое; нельзя добавлять произвольную вторую ошибку только ради нужного value\n"
    "- Если для value нет короткой правдоподобной цепочки ошибки, выбери другой value\n"
    "- Укажи шаг: что перепутал, не довёл, пропустил, неверно преобразовал\n"
    "- ЗАПРЕЩЕНО: «типичная ошибка», «ошибка при вычислении», «неправильно решил», "
    "«ученик ошибся», «ошибка в задаче» без конкретики\n"
    "- Разные дистракторы — разные ошибки на разных шагах, не перефраз одной фразы\n"
)


_REL_RE = re.compile(
    r"^([+-]?[\d.,/()\s√+\-]+)\s*(<=|>=|<|>|!=|≠|≤|≥)\s*([+-]?[\d.,/()\s√+\-x^a-zA-Z0-9]+)",
    re.I,
)


def _relation_flip_candidates(answer: str) -> list[str]:
    core = _extract_relation_core(answer) or _normalize_ineq_symbols((answer or "").strip())
    m = _REL_RE.match(core)
    if not m:
        return []
    a, op, b = m.group(1).strip(), m.group(2), m.group(3).strip()
    flips = {"<": ">", ">": "<", "<=": ">=", ">=": "<=", "≤": "≥", "≥": "≤"}
    out: list[str] = []
    if op in flips:
        out.append(f"{a} {flips[op]} {b}")
    out.append(f"{a} = {b}")
    # Skip b op a — usually peer-equivalent to flipped a op b for numeric relations.
    if op in ("<", ">", "≤", "≥"):
        weak = {"<": "≤", ">": "≥", "≤": "<", "≥": ">"}.get(op)
        if weak:
            out.append(f"{a} {weak} {b}")
    return out


def _chain_inequality_candidates(answer: str) -> list[str]:
    s = _normalize_ineq_symbols((answer or "").strip())
    m = re.match(
        r"^([+-]?[\d.,/()\s√+\-]+)\s*(<|>|≤|≥)\s*(.+?)\s*(<|>|≤|≥)\s*([+-]?[\d.,/()\s√+\-]+)$",
        s,
    )
    if not m:
        return []
    a, op1, mid, op2, c = m.groups()
    flips = {"<": ">", ">": "<", "≤": "≥", "≥": "≤"}
    return [
        f"{a} {flips.get(op1, op1)} {mid.strip()} {op2} {c.strip()}",
        f"{a.strip()} {op1} {mid.strip()} {flips.get(op2, op2)} {c.strip()}",
        f"{c.strip()} {flips.get(op2, op2)} {mid.strip()} {flips.get(op1, op1)} {a.strip()}",
    ]


def _numeric_offset_candidates(answer: str) -> list[str]:
    s = (answer or "").strip().replace(" ", "")
    dec = "," if "," in s and "." not in s else "."
    try:
        v = float(s.replace(",", "."))
    except ValueError:
        return []
    offsets = [v * 10, v / 10 if v else 0.1, v * 2, v + 1, v - 1]
    out: list[str] = []
    for x in offsets:
        if abs(x) >= 1000 or (0 < abs(x) < 1e-9 and x != 0):
            continue
        txt = f"{x:.6f}".rstrip("0").rstrip(".")
        if dec == ",":
            txt = txt.replace(".", ",")
        if txt and txt not in out:
            out.append(txt)
    return out


def _prose_template_candidates(answer: str, question: str) -> list[str]:
    a = (answer or "").strip()
    al = a.lower()
    qlow = (question or "").lower()
    if a in ("Доказано",) or al.startswith("доказано"):
        return ["Не доказано", "Верно только при положительных значениях", "Неверно"]
    if re.match(r"^(да|нет)\b", al):
        verdict = "да" if al.startswith("да") else "нет"
        opp = "нет" if verdict == "да" else "да"
        reason = a.split(",", 1)[1].strip() if "," in a else "неверное преобразование"
        return [
            f"{opp.capitalize()}, так как {reason}",
            f"{opp.capitalize()}, так как применена неверная формула",
            "Нельзя однозначно ответить",
        ]
    if al.startswith("тождество доказано"):
        return ["Тождество не доказано", "Верно только при a > 0", "Неверно"]
    if al.startswith("неравенство доказано") or al.startswith("неравенство верно"):
        return [
            "Неравенство не доказано",
            "Верно только при положительных значениях",
            "Неверное преобразование",
        ]
    if a in ("C", "D"):
        return ["D" if a == "C" else "C", "Одинаково удалены", "M"]
    if re.fullmatch(r"-?\d+([.,]\d+)?", a.replace(" ", "")):
        return _numeric_offset_candidates(a)
    if len(a) <= 50 and ("докаж" in qlow or "неравенств" in qlow) and not _relation_flip_candidates(a):
        return [
            "Неравенство не доказано",
            "Верно не для всех значений переменной",
            a.replace("> 0", "< 0") if "> 0" in a else "Неверное преобразование",
        ]
    return []


def _try_deterministic_distractors(
    task: ExtractedTask,
    answer: str,
    *,
    accepted: list[dict],
    all_rejected: list[dict],
) -> list[dict]:
    """Rule-based distractors when LLM cannot pass gate (comparisons, tiny decimals)."""
    declared_type = (task.answer_type or "exact_number").lower()
    atype = effective_distractor_answer_type(
        task.question_text or "", answer, declared_type
    )
    skip_l3 = atype in _TEXT_TYPES or atype in ("inequality", "set")
    target = _required_distractor_count(
        answer, declared_type, task.question_text or ""
    )
    question = task.question_text or ""

    candidates: list[str] = []
    if atype in _TEXT_TYPES or atype in ("inequality", "multiple_choice"):
        candidates.extend(_chain_inequality_candidates(answer))
        candidates.extend(_relation_flip_candidates(answer))
        candidates.extend(_prose_template_candidates(answer, question))
    if atype in _NUMERIC_TYPES:
        candidates.extend(_numeric_offset_candidates(answer))

    seen = {str(d.get("value", "")).strip().casefold() for d in accepted}
    seen.add(answer.strip().casefold())
    raw_items = [
        {
            "value": v.strip(),
            "error_logic": _DET_ERR,
            "explanation": _DET_ERR,
        }
        for v in candidates
        if v.strip() and v.strip().casefold() not in seen
    ]
    if not raw_items:
        return accepted

    batch_accepted, batch_rejected = validate_distractor_set(
        raw_items,
        question=question,
        correct_answer=answer,
        answer_type=atype,
        max_count=target - len(accepted),
        skip_l3=skip_l3,
    )
    all_rejected.extend(batch_rejected)
    merged = list(accepted)
    for d in batch_accepted:
        val = str(d.get("value", "")).strip()
        if val.casefold() in {str(x.get("value", "")).strip().casefold() for x in merged}:
            continue
        merged.append(d)
        if len(merged) >= target:
            break
    return merged


def _items_to_meta(items: list[dict], error_type: str) -> tuple[list[str], list[dict]]:
    distractors = [str(d.get("value", "")) for d in items]
    meta = [
        {
            "value": d.get("value", ""),
            "error_type": error_type,
            "explanation": d.get("explanation", d.get("error_logic", "")),
            "error_logic": d.get("error_logic", d.get("explanation", "")),
            "plausibility": 0.75,
        }
        for d in items
    ]
    return distractors, meta


def _top_up_distractors(
    task: ExtractedTask,
    answer: str,
    accepted: list[dict],
    all_rejected: list[dict],
) -> list[dict]:
    """One focused LLM call to fill missing distractors (need exactly 3 total)."""
    from src.pipeline.deepseek_client import call_deepseek_structured, get_deepseek_model
    from src.schemas.smart_verify import DistractorGenerationResponse

    need = _required_distractor_count(
        answer,
        task.answer_type or "exact_number",
        task.question_text or "",
    ) - len(accepted)
    if need <= 0:
        return accepted

    declared_type = (task.answer_type or "exact_number").lower()
    atype = effective_distractor_answer_type(
        task.question_text or "", answer, declared_type
    )
    skip_l3 = atype in _TEXT_TYPES or atype in ("inequality", "set")
    min_count = _required_distractor_count(
        answer,
        declared_type,
        task.question_text or "",
    )
    existing = [str(d.get("value", "")) for d in accepted]
    reject_lines = [
        f"- {r.get('value', '?')}: {r.get('gate_reason', 'invalid')}"
        for r in all_rejected[:10]
    ]
    prompt = (
        f"Задача: {task.question_text}\n"
        f"Правильный ответ: {answer}\n"
        f"Уже есть дистракторы (не повторяй): {existing}\n"
        + ("\nОтклонённые:\n" + "\n".join(reject_lines) + "\n" if reject_lines else "")
        + f"\nПридумай ещё ровно {need} НЕВЕРНЫХ ответа — типичные ошибки ученика.\n"
        f"{_ERROR_LOGIC_REQUIREMENTS}"
        f'Верни JSON: {{"distractors":[{{"value":"...","error_logic":"..."}}]}}\n'
    )
    try:
        response = call_deepseek_structured(
            prompt,
            DistractorGenerationResponse,
            model=get_deepseek_model(),
            temperature=0.4,
            max_tokens=1024,
            timeout=90,
            # Retry at the candidate-set level below, where rejected values
            # are carried into the next prompt.  Retrying the same transport
            # request five times only blocks the worker and burns rate budget.
            max_retries=1,
        )
        items = [item.model_dump() for item in response.distractors]
        raw_items = [
            {
                "value": d.get("value", ""),
                "error_logic": d.get("error_logic", d.get("explanation", "")),
                "explanation": d.get("error_logic", d.get("explanation", "")),
            }
            for d in items
            if isinstance(d, dict)
        ]
        batch_accepted, batch_rejected = validate_distractor_set(
            raw_items,
            question=task.question_text or "",
            correct_answer=answer,
            answer_type=atype,
            max_count=need,
            skip_l3=skip_l3,
        )
        all_rejected.extend(batch_rejected)
        from src.pipeline.answer_verify import answers_equivalent

        for d in batch_accepted:
            val = str(d.get("value", "")).strip()
            if any(answers_equivalent(val, s, atype) for s in existing):
                continue
            if any(answers_equivalent(val, str(x.get("value", "")), atype) for x in accepted):
                continue
            accepted.append(d)
            existing.append(val)
            if len(accepted) >= min_count:
                break
    except Exception as exc:
        log.warning("Distractor top-up failed (%s): %s", task.temp_id, exc)
    return accepted


def _apply_pedagogy_inline(
    accepted: list[dict],
    task: ExtractedTask,
    answer: str,
    all_rejected: list[dict],
) -> tuple[list[dict], bool]:
    """
    Запускает LLM-ревью педагогического качества error_logic ВНУТРИ пайплайна.
    - ok → без изменений
    - rewrite → DeepSeek переписывает error_logic более конкретно
    - reject_value → дистрактор убирается и добавляется в all_rejected для retry
    Повторяется, если состав набора изменился после reject/regeneration.
    """
    from src.pipeline.distractor_pedagogy import (
        apply_pedagogy_review,
        audit_distractor_pedagogy,
    )
    atype = (task.answer_type or "exact_number").lower()

    try:
        review = audit_distractor_pedagogy(
            question=task.question_text or "",
            correct_answer=answer,
            answer_type=atype,
            distractors=accepted,
        )
        updated, outcome = apply_pedagogy_review(accepted, review)

        if outcome == "pass":
            log.info(
                "Pedagogy review PASS (%s): %d distractors OK", task.temp_id, len(updated)
            )
            return updated, True
        elif outcome == "needs_regen":
            # Добавляем reject_value в all_rejected для следующего retry
            for item in review.items:
                if (item.status or "").lower() == "reject_value" and item.index < len(accepted):
                    rej = dict(accepted[item.index])
                    rej["gate_reason"] = f"pedagogy_reject: {item.issue or 'poor quality'}"
                    all_rejected.append(rej)
            log.info(
                "Pedagogy review NEEDS_REGEN (%s): %d rejected",
                task.temp_id,
                sum(1 for r in review.items if (r.status or "").lower() == "reject_value"),
            )
            # Возвращаем только не-отклонённые (updated содержит оригинал при needs_regen)
            kept_indices = {
                i for i, item in enumerate(review.items)
                if (item.status or "").lower() != "reject_value"
            }
            return [d for i, d in enumerate(accepted) if i in kept_indices], False
        else:
            log.warning("Pedagogy review invalid_review for %s", task.temp_id)
            return accepted, False
    except Exception as exc:
        log.warning("Pedagogy review failed for %s: %s", task.temp_id, exc)
        return accepted, False


def _ai_generate_distractors(task: ExtractedTask, answer: str) -> None:
    from src.pipeline.deepseek_client import get_deepseek_model

    settings = get_settings()
    atype = effective_distractor_answer_type(
        task.question_text or "", answer, task.answer_type or "exact_number"
    )
    skip_l3 = atype in _TEXT_TYPES or atype in ("inequality", "set")
    target = _required_distractor_count(
        answer, task.answer_type or "exact_number", task.question_text or ""
    )
    minimum = _minimum_distractor_count(
        answer, task.answer_type or "exact_number", task.question_text or ""
    )
    max_retries = settings.distractor_gate_max_retries

    all_rejected: list[dict] = []
    accepted: list[dict] = []

    for attempt in range(max_retries + 1):
        prompt = _build_distractor_prompt(task, answer, rejected=all_rejected or None)
        from src.pipeline.deepseek_client import call_deepseek_structured
        from src.schemas.smart_verify import DistractorGenerationResponse

        try:
            response = call_deepseek_structured(
                prompt + '\nВерни JSON: {"distractors":[{"value":"...","error_logic":"..."}]}\n',
                DistractorGenerationResponse,
                model=get_deepseek_model(),
                temperature=0.3,
                max_tokens=4096,
                timeout=90,
                max_retries=1,
            )
            items = [item.model_dump() for item in response.distractors]
            raw_items = [
                {
                    "value": d.get("value", ""),
                    "error_logic": d.get("error_logic", d.get("explanation", "")),
                    "explanation": d.get("error_logic", d.get("explanation", "")),
                }
                for d in items
                if isinstance(d, dict)
            ]
        except Exception as exc:
            log.warning("Distractor LLM failed (%s) attempt %d: %s", task.temp_id, attempt, exc)
            continue

        batch_accepted, batch_rejected = validate_distractor_set(
            raw_items,
            question=task.question_text or "",
            correct_answer=answer,
            answer_type=atype,
            max_count=target,
            skip_l3=skip_l3,
        )
        accepted.extend(batch_accepted)
        all_rejected.extend(batch_rejected)

        # Deduplicate accepted across retries
        unique: list[dict] = []
        seen_vals: list[str] = []
        for d in accepted:
            val = str(d.get("value", "")).strip()
            from src.pipeline.answer_verify import answers_equivalent
            if any(answers_equivalent(val, s, atype) for s in seen_vals):
                continue
            unique.append(d)
            seen_vals.append(val)
            if len(unique) >= target:
                break
        accepted = unique

        if len(accepted) >= target:
            break

    while len(accepted) < target:
        before = len(accepted)
        accepted = _top_up_distractors(task, answer, accepted, all_rejected)
        if len(accepted) >= target or len(accepted) == before:
            break

    min_count = _minimum_distractor_count(
        answer, task.answer_type or "exact_number", task.question_text or ""
    )

    if len(accepted) < min_count:
        accepted = _try_deterministic_distractors(
            task, answer, accepted=accepted, all_rejected=all_rejected
        )

    if not task.tags:
        task.tags = {}
    task.tags["distractor_gate_passed"] = len(accepted)
    if all_rejected:
        task.tags["distractor_gate_rejected"] = [
            {"value": r.get("value"), "reason": r.get("gate_reason")}
            for r in all_rejected[:12]
        ]

    if len(accepted) < min_count:
        raise ValueError(
            f"only {len(accepted)} distractors passed gate (need at least {min_count})"
        )

    take = min(len(accepted), target)
    error_type = "ai_numeric" if atype in _NUMERIC_TYPES else "ai_generated"
    task.distractors, task.distractor_meta = _items_to_meta(accepted[:take], error_type)
    if not task.tags:
        task.tags = {}
    tags_n = len(task.distractor_meta or [])
    task.tags["choices_complete"] = tags_n >= min_count
    if tags_n < target:
        task.tags["distractor_count_partial"] = tags_n


def generate_distractors(
    task: ExtractedTask,
    *,
    verify_answer: bool = True,
    force_distractors: bool = False,
) -> ExtractedTask:
    """Generate distractors; optionally run legacy verify first."""
    answer = (task.answer_raw or "").strip()
    if not answer or answer == "\u2014":
        log.info(
            "Distractors skipped (%s): answer_raw empty or dash — solver did not produce answer",
            task.temp_id,
        )
        return task

    answer_corrected = False
    if verify_answer:
        from src.pipeline.answer_verify import apply_verify_to_task, verify_answer as _verify

        vr = _verify(
            task.question_text or "",
            answer,
            task.answer_type or "exact_number",
        )
        apply_verify_to_task(task, vr)
        answer_corrected = vr.corrected
        if vr.skip_distractors:
            log.info("Distractors skipped (%s): %s", task.temp_id, vr.skip_reason)
            return task
        answer = (task.answer_raw or "").strip()
        if not answer:
            return task

        if not answer_corrected and _has_complete_distractors(task) and not force_distractors:
            log.debug("Distractors kept (verified answer): %s", task.temp_id)
            return task

    elif not force_distractors and _has_complete_distractors(task):
        log.debug("Distractors kept (no regen requested): %s", task.temp_id)
        return task

    had_complete_before = _has_complete_distractors(task)

    if answer_corrected or (not verify_answer and force_distractors and not _has_complete_distractors(task)):
        if verify_answer and answer_corrected:
            _clear_distractors(task)
            if not task.tags:
                task.tags = {}
            task.tags["distractors_cleared_for_correction"] = True

    try:
        _ai_generate_distractors(task, answer)
    except Exception as exc:
        log.warning("Distractor generation failed (%s): %s", task.temp_id, exc)

    need_complete = answer_corrected or (
        not verify_answer and force_distractors and not _has_complete_distractors(task)
    )
    if need_complete and not _has_complete_distractors(task):
        if not task.tags:
            task.tags = {}
        task.tags["distractor_regen_pending"] = True
        # Never wipe a previously complete set when regen fails.
        if not had_complete_before:
            _clear_distractors(task)

    return task
