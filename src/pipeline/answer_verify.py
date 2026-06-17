"""
Gemini + SymPy answer verification before distractor generation.

Policy (max accuracy):
  1. Gemini Flash re-solves; compare with stored (string + SymPy).
  2. On mismatch → Gemini Pro second opinion (dual consensus).
  3. Auto-correct ONLY when Flash ≈ Pro AND SymPy/question validation favours consensus.
  4. SymPy says stored ≈ consensus → never change.
  5. SymPy favours stored → verify_conflict (keep stored, human review).
  6. No SymPy confirmation for correction → verify_unresolved (no auto-fix).
  7. Flash matches but stored fails SymPy check → verify_unresolved.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Optional

from src.pipeline.answer_sympy import (
    monte_carlo_equivalent,
    sympy_equivalent,
    try_validate_answer_for_question,
)

log = logging.getLogger(__name__)

_VERIFIABLE_TYPES = frozenset({
    "exact_number", "decimal", "fraction", "expression",
    "equation_solution", "inequality", "set", "multiple_choice",
})

_SKIP_VERIFY_RE = re.compile(
    r"докажите|доказать|изобразите|постройте|построить|"
    r"чертёж|чертеж|график функции|заполните таблиц",
    re.I,
)

_INCOMPLETE_Q_RE = re.compile(
    r"^(упростите|вычислите|найдите|сократите|представьте|выполните|разложите)\s*(выражение|дробь)?\s*:?\s*$",
    re.I,
)


@dataclass
class AnswerVerifyResult:
    match: bool
    gemini_answer: str = ""
    gemini_answer_pro: str = ""
    stored_answer: str = ""
    final_answer: str = ""
    verified: bool = False
    corrected: bool = False
    skip_distractors: bool = False
    skip_reason: str = ""
    tags_patch: dict = field(default_factory=dict)


def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = s.replace("−", "-").replace("–", "-").replace("—", "-")
    s = s.replace("{", "").replace("}", "").replace("$", "")
    s = s.replace("\\sqrt", "sqrt").replace("\\frac", "")
    s = re.sub(r"\s+", "", s)
    s = s.replace(",", ".")
    s = re.sub(r"^\d+\)", "", s)
    s = re.sub(r"^[абвг]\)", "", s)
    s = re.sub(r"^x[_₀₁₂]?=", "x=", s)
    s = re.sub(r"^x=", "", s)
    s = re.sub(r"^y=", "", s)
    return s


def _extract_numbers(s: str) -> list[float]:
    s = _norm(s)
    nums: list[float] = []
    for m in re.finditer(r"-?\d+\.?\d*", s):
        try:
            nums.append(float(m.group()))
        except ValueError:
            pass
    return nums


def _try_fraction(s: str) -> Optional[float]:
    s = (s or "").strip().replace(",", ".")
    if "/" in s and "=" not in s:
        parts = s.split("/", 1)
        if len(parts) == 2:
            try:
                return float(Fraction(int(parts[0].strip()), int(parts[1].strip())))
            except (ValueError, ZeroDivisionError):
                pass
    try:
        return float(s)
    except ValueError:
        return None


def answers_equivalent(stored: str, candidate: str, answer_type: str = "") -> bool:
    """Format-tolerant + SymPy equivalence."""
    a, b = (stored or "").strip(), (candidate or "").strip()
    if not a or not b:
        return False
    if _norm(a) == _norm(b):
        return True
    if _norm(a) in _norm(b) or _norm(b) in _norm(a):
        return True

    fa, fb = _try_fraction(a), _try_fraction(b)
    if fa is not None and fb is not None and abs(fa - fb) < 1e-6:
        return True

    na, nb = sorted(_extract_numbers(a)), sorted(_extract_numbers(b))
    if na and nb and len(na) == len(nb) and all(abs(x - y) < 1e-4 for x, y in zip(na, nb)):
        return True
    if na and nb and set(round(x, 4) for x in na) == set(round(x, 4) for x in nb):
        return True

    sym = sympy_equivalent(a, b, answer_type)
    if sym is True:
        return True
    # algebraic rewrite: 2n+1 vs n+(n+1)
    if re.search(r"\bn\b", a, re.I) and re.search(r"\bn\b", b, re.I):
        mc = monte_carlo_equivalent(a.replace("n", "x"), b.replace("n", "x"))
        if mc is True:
            return True

    return False


def _gemini_solve(question: str, answer_type: str, *, use_pro: bool = False) -> str:
    from src.pipeline.gemini_client import (
        call_gemini,
        get_flash_model,
        get_pro_model,
        parse_json_response,
    )

    model = get_pro_model() if use_pro else get_flash_model()
    label = "Pro" if use_pro else "Flash"
    prompt = (
        f"Ты — математический педагог. Реши задачу ({label}) и верни только финальный ответ.\n\n"
        f"Текст: {question}\n"
        f"Тип ответа: {answer_type}\n\n"
        'Верни JSON: {"answer":"<окончательный ответ>"}\n'
        "answer — краткий точный ответ в привычной школьной записи. Только JSON."
    )
    raw = call_gemini(
        prompt,
        model=model,
        temperature=0.1,
        max_tokens=2048,
        thinking_budget=0,
    )
    data = parse_json_response(raw)
    if isinstance(data, dict):
        ans = data.get("answer", "")
        if isinstance(ans, (int, float)):
            return str(ans)
        return str(ans).strip()
    return ""


def gemini_solve(question: str, answer_type: str) -> str:
    return _gemini_solve(question, answer_type, use_pro=False)


def gemini_solve_pro(question: str, answer_type: str) -> str:
    return _gemini_solve(question, answer_type, use_pro=True)


def should_skip_verify(question: str, answer_type: str) -> Optional[str]:
    q = (question or "").strip()
    if _SKIP_VERIFY_RE.search(q[:200]):
        return "proof_or_drawing"
    if answer_type == "text" and len(q) > 300:
        return "long_text"
    if answer_type in ("coordinate", "open_text"):
        return f"type_{answer_type}"
    if _INCOMPLETE_Q_RE.match(q) or (len(q) < 25 and not re.search(r"[0-9=+\-*/^()\\$]", q)):
        return "incomplete_question"
    return None


def _dual_consensus(a: str, b: str, answer_type: str) -> bool:
    if answers_equivalent(a, b, answer_type):
        return True
    sym = sympy_equivalent(a, b, answer_type)
    return sym is True


def _decide_correction(
    question: str,
    stored: str,
    consensus: str,
    answer_type: str,
) -> AnswerVerifyResult:
    """Flash+Pro agree on consensus ≠ stored — SymPy gate before any change."""
    base_tags = {
        "answer_gemini_candidate": consensus[:500],
        "answer_gemini_flash": consensus[:500],
    }

    sym_stored_cons = sympy_equivalent(stored, consensus, answer_type)
    if sym_stored_cons is True:
        return AnswerVerifyResult(
            match=True,
            gemini_answer=consensus,
            stored_answer=stored,
            final_answer=stored,
            verified=True,
            tags_patch={
                **base_tags,
                "answer_gemini_verified": True,
                "answer_verify_mode": "sympy_match",
            },
        )

    stored_ok = try_validate_answer_for_question(question, stored, answer_type)
    consensus_ok = try_validate_answer_for_question(question, consensus, answer_type)

    if stored_ok is True and consensus_ok is not True:
        log.info(
            "Verify conflict — keep stored [%s]: stored=%r consensus=%r",
            answer_type, stored[:50], consensus[:50],
        )
        return AnswerVerifyResult(
            match=False,
            gemini_answer=consensus,
            stored_answer=stored,
            final_answer=stored,
            verified=True,
            skip_distractors=True,
            skip_reason="verify_conflict",
            tags_patch={
                **base_tags,
                "answer_gemini_verified": True,
                "verify_conflict": True,
                "answer_verify_mode": "conflict",
            },
        )

    if consensus_ok is True and stored_ok is not True:
        log.info(
            "SymPy-confirmed correction [%s]: stored=%r → consensus=%r",
            answer_type, stored[:50], consensus[:50],
        )
        return AnswerVerifyResult(
            match=False,
            gemini_answer=consensus,
            stored_answer=stored,
            final_answer=consensus,
            corrected=True,
            verified=True,
            tags_patch={
                **base_tags,
                "answer_gemini_verified": True,
                "answer_corrected_by_gemini": True,
                "answer_corrected_sympy_confirmed": True,
                "answer_previous": stored[:500],
                "answer_verify_mode": "corrected_sympy",
            },
        )

    log.warning(
        "Verify unresolved — no SymPy confirmation [%s]: stored=%r consensus=%r "
        "stored_ok=%s consensus_ok=%s sym_equiv=%s",
        answer_type, stored[:50], consensus[:50], stored_ok, consensus_ok, sym_stored_cons,
    )
    return AnswerVerifyResult(
        match=False,
        gemini_answer=consensus,
        stored_answer=stored,
        final_answer=stored,
        skip_distractors=True,
        skip_reason="verify_unresolved",
        tags_patch={
            **base_tags,
            "answer_gemini_verified": False,
            "verify_unresolved": True,
            "answer_verify_mode": "unresolved",
        },
    )


def verify_answer(
    question: str,
    stored_answer: str,
    answer_type: str,
    *,
    auto_fix: bool = True,
    call_gemini: bool = True,
    dual_consensus: bool = True,
) -> AnswerVerifyResult:
    """Re-solve with Gemini (+ Pro on mismatch), SymPy gate before any correction."""
    stored = (stored_answer or "").strip()
    if not stored or stored in ("—", "-", "?"):
        return AnswerVerifyResult(
            match=False,
            stored_answer=stored,
            final_answer=stored,
            skip_distractors=True,
            skip_reason="empty_answer",
        )

    skip = should_skip_verify(question, answer_type or "")
    if skip:
        return AnswerVerifyResult(
            match=True,
            stored_answer=stored,
            final_answer=stored,
            verified=True,
            skip_reason=skip,
            tags_patch={"answer_gemini_verified": True, "answer_verify_mode": "skipped"},
        )

    at = (answer_type or "").lower()
    if at not in _VERIFIABLE_TYPES:
        return AnswerVerifyResult(
            match=True,
            stored_answer=stored,
            final_answer=stored,
            verified=True,
            skip_reason=f"type_{at}",
            tags_patch={"answer_gemini_verified": True, "answer_verify_mode": "skipped_type"},
        )

    gemini_flash = ""
    gemini_pro = ""
    if call_gemini:
        try:
            gemini_flash = gemini_solve(question, at)
        except Exception as exc:
            log.warning("Gemini Flash verify failed: %s", exc)
            return AnswerVerifyResult(
                match=False,
                stored_answer=stored,
                final_answer=stored,
                skip_distractors=False,
                skip_reason="gemini_error",
                tags_patch={"answer_verify_error": str(exc)[:200]},
            )

    if not gemini_flash:
        return AnswerVerifyResult(
            match=False,
            stored_answer=stored,
            final_answer=stored,
            skip_distractors=False,
            skip_reason="gemini_empty",
        )

    if answers_equivalent(stored, gemini_flash, at):
        stored_ok = try_validate_answer_for_question(question, stored, at)
        if stored_ok is False:
            log.warning(
                "Verify unresolved — stored fails SymPy check [%s]: %r flash=%r",
                at, stored[:50], gemini_flash[:50],
            )
            return AnswerVerifyResult(
                match=False,
                gemini_answer=gemini_flash,
                stored_answer=stored,
                final_answer=stored,
                skip_distractors=True,
                skip_reason="stored_sympy_invalid",
                tags_patch={
                    "answer_gemini_verified": False,
                    "verify_unresolved": True,
                    "answer_gemini_candidate": gemini_flash[:500],
                    "answer_verify_mode": "stored_invalid",
                },
            )
        return AnswerVerifyResult(
            match=True,
            gemini_answer=gemini_flash,
            stored_answer=stored,
            final_answer=stored,
            verified=True,
            tags_patch={
                "answer_gemini_verified": True,
                "answer_verify_mode": "match",
            },
        )

    if not auto_fix:
        return AnswerVerifyResult(
            match=False,
            gemini_answer=gemini_flash,
            stored_answer=stored,
            final_answer=stored,
            skip_distractors=True,
            skip_reason="mismatch_no_autofix",
            tags_patch={
                "answer_gemini_verified": False,
                "answer_mismatch": True,
                "answer_gemini_candidate": gemini_flash[:500],
                "answer_verify_mode": "mismatch",
            },
        )

    consensus = gemini_flash
    if dual_consensus:
        try:
            gemini_pro = gemini_solve_pro(question, at)
        except Exception as exc:
            log.warning("Gemini Pro verify failed: %s", exc)
            gemini_pro = ""

        if gemini_pro and _dual_consensus(gemini_flash, gemini_pro, at):
            consensus = gemini_pro if len(gemini_pro) >= len(gemini_flash) else gemini_flash
        else:
            log.warning(
                "Dual consensus failed [%s]: flash=%r pro=%r",
                at, gemini_flash[:40], (gemini_pro or "")[:40],
            )
            return AnswerVerifyResult(
                match=False,
                gemini_answer=gemini_flash,
                gemini_answer_pro=gemini_pro,
                stored_answer=stored,
                final_answer=stored,
                skip_distractors=True,
                skip_reason="dual_consensus_failed",
                tags_patch={
                    "answer_gemini_verified": False,
                    "verify_unresolved": True,
                    "answer_gemini_candidate": gemini_flash[:500],
                    "answer_gemini_pro_candidate": (gemini_pro or "")[:500],
                    "answer_verify_mode": "dual_failed",
                },
            )

    result = _decide_correction(question, stored, consensus, at)
    result.gemini_answer = gemini_flash
    result.gemini_answer_pro = gemini_pro
    return result


def apply_verify_to_task(task, result: AnswerVerifyResult) -> None:
    """Mutate ExtractedTask: answer_raw + tags from verify result."""
    task.answer_raw = result.final_answer
    if not task.tags:
        task.tags = {}
    task.tags.update(result.tags_patch)
    # Stale flags cleared on next persist via verify_distractor_pass
