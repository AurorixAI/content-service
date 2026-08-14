"""Distractor validation gate — L1 parseable, L2 collision, L3 not-a-solution, L4 plausible."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from src.pipeline.answer_sympy import parse_expr, try_validate_answer_for_question
from src.pipeline.answer_sympy_gate import (
    _comparison_answer_key,
    _try_validate_equation_answer,
)
from src.pipeline.answer_verify import (
    _norm,
    _normalize_ineq_symbols,
    _split_compound_parts,
)
from src.pipeline.distractor_collision import (
    _looks_numeric_school_answer,
    values_collide_for_distractor,
)

log = logging.getLogger(__name__)

_GARBAGE_RE = re.compile(
    r"^(не\s*знаю|неизвестно|\?+|—+|-+|n/?a)$",
    re.I,
)

_NUMERIC_TYPES = frozenset({"exact_number", "decimal", "fraction"})
_COMPUTABLE_TYPES = frozenset({
    "exact_number", "decimal", "fraction", "expression",
    "equation_solution", "inequality", "set", "multiple_choice",
})

_LABELED_PREFIX_RE = re.compile(r"^[а-г]\)\s*|^\d+\)\s*", re.I)
_INEQ_RE = re.compile(r"(?:<=|>=|≤|≥|!=|≠|<|>)")
_TRAILING_REASON_RE = re.compile(
    r",\s*(?:так как|потому что|так что|поскольку|значит|т\.?\s*к\.?).*$",
    re.I,
)
_NUMERIC_TEXT_RE = re.compile(
    r"^[\d\s.,+\-]+(?:/\d+)?(?:\s+\d+/\d+)?$",
)
_MIXED_FRAC_RE = re.compile(r"^\d+\s+\d+/\d+$")
_FRAC_RE = re.compile(r"^\d+/\d+$")


def effective_distractor_answer_type(
    question: str,
    correct_answer: str,
    answer_type: str,
) -> str:
    """Return the validation domain for a distractor.

    ``answer_type`` is historical source metadata and a non-trivial number of
    imported tasks are labelled ``exact_number`` even though their answer is a
    coordinate pair, a system of roots, an interval, or a formula.  The
    metadata must stay unchanged, but the gate must validate the *actual*
    answer format rather than attempting to parse every such value as one
    number.
    """
    declared = (answer_type or "").lower()
    if declared not in _NUMERIC_TYPES:
        return declared

    raw = (correct_answer or "").replace("$", "").strip()
    if not raw:
        return declared

    # A comparison task is handled by its dedicated exact-number/sign gate.
    if _comparison_answer_key(raw, question):
        return declared

    # Intervals and systems of inequalities have their own equivalence logic.
    # Check the question as well: legacy imports often wrap the answer in
    # LaTeX and use ``\cup`` / ``\infty`` instead of Unicode characters.
    # A coordinate pair remains an equation solution unless the task itself
    # explicitly asks for a domain, interval, or solution set.
    interval_context = f"{question or ''} {raw}"
    has_interval_delimiter = bool(
        re.search(r"[∪∞∈]|\\(?:cup|infty|in)\b", interval_context)
    )
    if not has_interval_delimiter:
        # Parenthesized semicolon pairs are coordinates unless the question or
        # answer explicitly identifies an interval/domain/solution set.  The
        # endpoint may itself be a LaTeX fraction, so inspect the full context
        # instead of using a character-only pair heuristic.
        has_interval_delimiter = bool(
            re.search(r"[\[(].*;.*[\])]", raw, re.S)
            and re.search(
                r"(?:промежут|множество\s+решен|област[ьи]\s+определ|x\s*[∈<>≤≥])",
                interval_context,
                re.I,
            )
        )
    if not has_interval_delimiter:
        # A bounded interval can have no union/infinity token at all.  Allow
        # it only when the question asks to solve an inequality/system or
        # explicitly requests an interval; ordinary coordinate pairs remain
        # equation solutions.
        has_interval_delimiter = bool(
            re.search(r"[\[(].*;.*[\])]", raw, re.S)
            and re.search(
                r"(?:неравенств|двойн\w*\s+неравен|промежут|множество\s+решен|"
                r"област[ьи]\s+определ|x\s*[∈<>≤≥])",
                interval_context,
                re.I,
            )
        )
    if has_interval_delimiter:
        return "inequality"

    # Coordinates, variable assignments, and multiple roots are solution sets.
    if re.search(r"\b[a-zA-Zа-яА-Я][\w₀-₉]*\s*=", raw):
        return "equation_solution"
    if re.search(r"\([^()]*;[^()]*\)", raw) or raw.count(";") >= 2:
        return "equation_solution"

    # Ratios and symbolic formulae are valid expressions, not malformed numbers.
    if ":" in raw or re.search(r"[A-Za-zА-Яа-я]|[=+*/^]", raw):
        return "expression"
    return declared

_DIGIT_SWAP_LOGIC_RE = re.compile(
    r"получил(?:а)?(?:\s+число)?\s*\$?(-?\d{2,})\$?"
    r"[\s\S]{0,180}?(?:перестав\w*\s+цифр|перепутал\w*\s+(?:порядок\s+)?цифр)"
    r"[\s\S]{0,140}?(?:запис\w*|получ\w*)\s*\$?(-?\d{2,})\$?",
    re.I,
)
_PLACE_VALUE_EQ_RE = re.compile(
    r"(\d+)\s*(?:[·*]\s*)?a\s*\+\s*b\s*=\s*(-?\d+)",
    re.I,
)
_AB_ASSIGN_RE = re.compile(
    r"a\s*=\s*(-?\d+)\s*[,;]\s*b\s*=\s*(-?\d+)",
    re.I,
)


def _standalone_comparison_sign(value: str) -> Optional[str]:
    raw = (value or "").replace("$", "").strip()
    raw = (
        raw.replace("≤", "<=").replace("≥", ">=")
        .replace("\\leqslant", "<=").replace("\\leq", "<=")
        .replace("\\geqslant", ">=").replace("\\geq", ">=")
    )
    return raw if raw in {"<", ">", "="} else None


def _error_logic_has_obvious_contradiction(error_logic: str) -> bool:
    """Reject explicit transformations whose own numbers cannot be true.

    A distractor may contain an incorrect student operation, but a named
    deterministic transformation must actually yield the claimed value.
    """
    text = (error_logic or "").replace("−", "-")

    for match in _DIGIT_SWAP_LOGIC_RE.finditer(text):
        before = match.group(1)
        after = match.group(2)
        sign = "-" if before.startswith("-") else ""
        digits = before.lstrip("-")
        expected = sign + digits[::-1]
        if int(expected) != int(after):
            return True

    equations = list(_PLACE_VALUE_EQ_RE.finditer(text))
    for assignment in _AB_ASSIGN_RE.finditer(text):
        prior = [eq for eq in equations if eq.end() <= assignment.start()]
        if not prior:
            continue
        eq = prior[-1]
        if assignment.start() - eq.end() > 220:
            continue
        coefficient = int(eq.group(1))
        claimed = int(eq.group(2))
        a_value = int(assignment.group(1))
        b_value = int(assignment.group(2))
        if coefficient * a_value + b_value != claimed:
            return True

    return False


def _strip_trailing_reasoning(val: str) -> str:
    s = (val or "").strip()
    return _TRAILING_REASON_RE.sub("", s).strip()


def _extract_relation_core(val: str) -> Optional[str]:
    """Leading numeric inequality before optional «, потому что …» prose."""
    s = _normalize_ineq_symbols(_strip_trailing_reasoning(val))
    m = re.match(
        r"^([+-]?[\d.,/()\s]+)\s*(<=|>=|<|>|!=|≠)\s*([+-]?[\d.,/()\s]+)",
        s,
    )
    if not m:
        return None
    return f"{m.group(1).strip()} {m.group(2)} {m.group(3).strip()}"


def _looks_numeric_school_answer(s: str) -> bool:
    s = (s or "").strip()
    if not s:
        return False
    if _NUMERIC_TEXT_RE.match(s):
        return True
    if _MIXED_FRAC_RE.match(s) or _FRAC_RE.match(s):
        return True
    if _extract_relation_core(s):
        return True
    return False


def _looks_multipart(value: str) -> bool:
    val = (value or "").strip()
    if ";" in val:
        return True
    return bool(_LABELED_PREFIX_RE.search(val))


def _is_parseable_single(value: str, answer_type: str) -> bool:
    val = (value or "").strip()
    if ";" in val:
        return True
    return bool(_LABELED_PREFIX_RE.search(val))


def _is_parseable_single(value: str, answer_type: str) -> bool:
    val = (value or "").strip()
    if not val or _GARBAGE_RE.match(val):
        return False

    at = (answer_type or "").lower()
    if at in ("text", "open_text"):
        # Compound text answers may contain single-digit numeric parts (e.g. "1; 3; 2.25").
        return len(val) >= 1

    def safe_parse(candidate: str) -> bool:
        try:
            return parse_expr(candidate) is not None
        except (SyntaxError, TypeError, ValueError):
            return False

    if at in _NUMERIC_TYPES:
        # Some historical tasks are typed as exact_number although their
        # actual answer is a comparison sign or a decimal place name.
        comparison = val.replace("$", "").strip()
        comparison = (
            comparison.replace("≤", "<=").replace("≥", ">=")
            .replace("\\leq", "<=").replace("\\geq", ">=")
        )
        if _extract_relation_core(val) or re.fullmatch(
            r"(?:[A-Za-zА-Яа-я0-9_]+\s*)?(?:<=|>=|<|>|=)"
            r"(?:\s*[A-Za-zА-Яа-я0-9_]+)?",
            comparison,
        ):
            return True
        if re.fullmatch(
            r"(?:до\s+)?(?:единиц(?:ы|а)?|десятк(?:ов|и|а)?|"
            r"сот(?:ен|ни|ня)?|тысяч(?:и)?|миллион(?:ов|а)?)"
            r"(?:\s+(?:тысяч|миллион(?:ов|а)?))?",
            val,
            re.I,
        ):
            return True
        try:
            float(val.replace(",", ".").replace(" ", ""))
            return True
        except ValueError:
            return safe_parse(val)

    if at == "equation_solution":
        if re.search(r"=\s*", val):
            return True
        return safe_parse(val) or bool(re.search(r"-?\d", val))

    if at in ("expression", "fraction", "inequality", "set"):
        if re.fullmatch(r"-?\d+(?:[.,]\d+)?", val.replace(" ", "")):
            return True
        if "/" in val:
            return True
        return safe_parse(val) or len(val) >= 2

    if at == "multiple_choice":
        return bool(re.fullmatch(r"[A-F]", val, re.I)) or len(val) >= 2

    return len(val) >= 2


def _is_parseable(value: str, answer_type: str) -> bool:
    val = (value or "").strip()
    if not val:
        return False
    at = (answer_type or "").lower()
    if _looks_multipart(val):
        parts = _split_compound_parts(val)
        if len(parts) >= 2:
            return all(_is_parseable_single(p, at) for p in parts)
    return _is_parseable_single(val, at)


def _is_implausible(value: str, correct_answer: str, answer_type: str, error_logic: str) -> bool:
    el = (error_logic or "").strip()
    if len(el) < 10:
        return True  # every distractor needs a concrete school-level mistake description
    if _error_logic_has_obvious_contradiction(el):
        return True
    if _GARBAGE_RE.match((value or "").strip()):
        return True

    at = (answer_type or "").lower()
    if at not in _NUMERIC_TYPES:
        return False

    if _looks_multipart(value) or _looks_multipart(correct_answer):
        return False

    try:
        c = float(str(correct_answer).replace(",", "."))
        d = float(str(value).replace(",", "."))
        denom = max(abs(c), 1.0)
        if abs(d - c) / denom > 100:
            return True
    except ValueError:
        pass
    return False


def _solves_question(value: str, question: str, answer_type: str) -> Optional[bool]:
    """True if distractor satisfies the question (must reject). None = unknown."""
    at = (answer_type or "").lower()
    core = _extract_relation_core(value) or value

    if at in ("text", "open_text", "coordinate"):
        if _looks_numeric_school_answer(value) or _INEQ_RE.search(value):
            from src.pipeline.answer_sympy import try_validate_expression_answer

            if re.search(r"сравните", question or "", re.I) and _INEQ_RE.search(core):
                return try_validate_expression_answer(question, core)
            if _looks_numeric_school_answer(core):
                return try_validate_answer_for_question(question, core, "fraction")
        return None

    if _looks_multipart(value):
        return None

    if _INEQ_RE.search(value) or (
        at == "expression" and re.search(r"сравните", question or "", re.I)
    ):
        from src.pipeline.answer_sympy import try_validate_expression_answer

        result = try_validate_expression_answer(question, core)
        if result is not None:
            return result

    if at in ("expression", "fraction", "exact_number", "decimal"):
        return try_validate_answer_for_question(question, core, at)

    if at == "equation_solution":
        return _try_validate_equation_answer(question, core)

    if at == "inequality":
        from src.pipeline.answer_sympy import try_validate_expression_answer

        return try_validate_expression_answer(question, core)

    return None


def _collision_with_correct(val: str, correct_answer: str, answer_type: str) -> bool:
    return values_collide_for_distractor(val, correct_answer, answer_type)


@dataclass
class DistractorCheck:
    ok: bool
    reason: str = "ok"


def _peer_collision(val: str, prev: str, answer_type: str) -> bool:
    """Distractors must be distinct wrong options — not sympy-loose equivalent."""
    if _norm(val) == _norm(prev):
        return True
    at = (answer_type or "").lower()
    # Prose text: «нет, так как …» vs «нет, потому что …» share a verdict prefix only.
    # values_collide_for_distractor strips after «, так как» — false peer hits on text.
    if at in ("text", "open_text"):
        if _looks_numeric_school_answer(val) or _looks_numeric_school_answer(prev):
            return values_collide_for_distractor(val, prev, answer_type)
        return False
    return values_collide_for_distractor(val, prev, answer_type)


def validate_distractor(
    *,
    question: str,
    value: str,
    correct_answer: str,
    answer_type: str,
    error_logic: str = "",
    accepted: Optional[list[str]] = None,
    skip_l3: bool = False,
) -> DistractorCheck:
    """Validate one distractor candidate."""
    val = (value or "").strip()
    accepted = accepted or []
    at = effective_distractor_answer_type(question, correct_answer, answer_type)

    if at == "exact_number" and _comparison_answer_key(correct_answer, question):
        if _standalone_comparison_sign(val) is None:
            return DistractorCheck(ok=False, reason="invalid_comparison_choice")

    if not _is_parseable(val, at):
        return DistractorCheck(ok=False, reason="parse_failed")

    if _collision_with_correct(val, correct_answer, at):
        return DistractorCheck(ok=False, reason="collision_correct")

    for prev in accepted:
        if _peer_collision(val, prev, at):
            return DistractorCheck(ok=False, reason="collision_peer")

    if not skip_l3:
        solves = _solves_question(val, question, at)
        if solves is True:
            return DistractorCheck(ok=False, reason="solves_question")

    if _is_implausible(val, correct_answer, at, error_logic):
        return DistractorCheck(ok=False, reason="implausible")

    return DistractorCheck(ok=True, reason="ok")


def validate_distractor_set(
    items: list[dict],
    *,
    question: str,
    correct_answer: str,
    answer_type: str,
    max_count: int = 3,
    skip_l3: bool = False,
) -> tuple[list[dict], list[dict]]:
    """
    Filter distractor dicts through L1–L4 gate.
    Returns (accepted, rejected) where rejected items have gate_reason.
    """
    accepted: list[dict] = []
    rejected: list[dict] = []
    accepted_vals: list[str] = []

    for d in items:
        val = str(d.get("value", d.get("error_logic", ""))).strip()
        el = str(d.get("error_logic", d.get("explanation", ""))).strip()
        check = validate_distractor(
            question=question,
            value=val,
            correct_answer=correct_answer,
            answer_type=answer_type,
            error_logic=el,
            accepted=accepted_vals,
            skip_l3=skip_l3,
        )
        if check.ok:
            accepted.append(d)
            accepted_vals.append(val)
            if len(accepted) >= max_count:
                break
        else:
            rejected.append({**d, "gate_reason": check.reason})

    return accepted, rejected


def stored_distractors_valid(
    dmeta: list | None,
    *,
    question: str,
    correct_answer: str,
    answer_type: str,
    min_count: int = 3,
) -> bool:
    """True if stored distractor_meta passes L1–L4 (exactly min_count items)."""
    if not isinstance(dmeta, list) or len(dmeta) < min_count:
        return False
    items = [
        {
            "value": d.get("value", ""),
            "error_logic": d.get("error_logic", d.get("explanation", "")),
        }
        for d in dmeta
        if isinstance(d, dict) and str(d.get("value", "")).strip()
    ][:6]
    if len(items) < min_count:
        return False
    accepted, rejected = validate_distractor_set(
        items,
        question=question,
        correct_answer=correct_answer,
        answer_type=answer_type,
        max_count=len(items),
    )
    return len(accepted) >= min_count and not rejected


def gate_clean_distractor_meta(
    dmeta: list | None,
    *,
    question: str,
    correct_answer: str,
    answer_type: str,
    min_count: int = 2,
    max_count: int = 3,
) -> list[dict] | None:
    """Subset of stored distractor_meta that passes L1–L4 (drops peer-colliding extras)."""
    if not isinstance(dmeta, list):
        return None
    items = [
        {
            "value": d.get("value", ""),
            "error_logic": d.get("error_logic", d.get("explanation", "")),
            "explanation": d.get("explanation", d.get("error_logic", "")),
            "_src": d,
        }
        for d in dmeta
        if isinstance(d, dict) and str(d.get("value", "")).strip()
    ]
    if len(items) < min_count:
        return None
    accepted, _ = validate_distractor_set(
        items,
        question=question,
        correct_answer=correct_answer,
        answer_type=answer_type,
        max_count=max_count,
    )
    if len(accepted) < min_count:
        return None
    out: list[dict] = []
    for a in accepted[:max_count]:
        src = a.get("_src") if isinstance(a.get("_src"), dict) else {}
        out.append(
            {
                **src,
                "value": a.get("value", src.get("value", "")),
                "error_logic": a.get("error_logic", src.get("error_logic", "")),
                "explanation": a.get("explanation", src.get("explanation", "")),
            }
        )
    return out
