"""Compute school answers from question text — no textbook / OCR trust."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from src.pipeline.answer_sympy import parse_expr
from src.pipeline.answer_sympy_gate import _expr_to_school_notation
from src.pipeline.answer_verify import answers_equivalent

# Pure arithmetic / fraction line (school notation).
_MIXED_FRAC = re.compile(r"(\d+)\s+(\d+)/(\d+)")
_UNDERSCORE_MIXED = re.compile(r"(\d+)_(\d+)/(\d+)")
_SCHOOL_DIV_FRAC = re.compile(r"(\([^)]+\)|\d+(?:\.\d+)?)\s*:\s*(\d+/\d+)")
_SCHOOL_DIV = re.compile(r"(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)")
_DECIMAL_COMMA = re.compile(r"(\d),(\d)")
_DECIMAL_EXPR = re.compile(r"^[\d\.\+\-\*/\(\)]+$")
_NUMERIC_ANSWER = re.compile(
    r"^[\d\s,\.\+\-\*/\(\)=]+$|^\d+\s+\d+/\d+$|^\d+/\d+$",
    re.I,
)


def _is_pure_numeric_expression(line: str) -> bool:
    s = _normalize_school_arith_line(line)
    if re.search(r"[a-zA-Zа-яё]", s, re.I):
        return False
    if not re.search(r"\d", s):
        return False
    if not re.search(r"[\+\-\*/:]", s):
        return False
    return True


def _is_final_numeric_value(s: str) -> bool:
    """Answer looks like a evaluated number/fraction, not an expression or list."""
    s = (s or "").strip()
    if not s:
        return False
    if re.search(r"[a-zA-Z\\{}²³]", s):
        return False
    if re.search(r"[а-яё]{2,}", s, re.I):
        return False
    if "*" in s:
        return False
    if re.search(r",\s*\d", s) and s.count(",") >= 2:
        return False
    if re.search(r"[\+\-\*/]", s):
        if re.fullmatch(r"-[\d,\./ ]+", s):
            return True
        return False
    return bool(re.search(r"\d", s))


def _is_numeric_computed_result(value: str) -> bool:
    return _is_final_numeric_value(value)


def _collapse_digit_thousands(s: str) -> str:
    """66 161 → 66161; keep mixed fractions 6 2/3."""
    placeholders: list[str] = []

    def _stash(m: re.Match) -> str:
        placeholders.append(m.group(0))
        return f"__M{len(placeholders) - 1}__"

    s = _MIXED_FRAC.sub(_stash, s)
    while re.search(r"(\d) (\d)", s):
        s = re.sub(r"(\d) (\d)", r"\1\2", s)
    for i, p in enumerate(placeholders):
        s = s.replace(f"__M{i}__", p)
    return s


def _decimal_commas_to_dots(s: str) -> str:
    return _DECIMAL_COMMA.sub(r"\1.\2", s)


def _normalize_stored_numeric_answer(stored: str) -> str:
    s = (stored or "").strip()
    if re.search(r"[a-zA-Zа-яё]", s, re.I):
        return s
    if "=" in s:
        rhs = s.rsplit("=", 1)[-1].strip()
        if not re.search(r"[a-zA-Zа-яё]", rhs, re.I):
            return rhs
    return s


def _looks_numeric_answer(stored: str) -> bool:
    s = _normalize_stored_numeric_answer(stored)
    if re.match(r"^(да|нет)\b", s, re.I):
        return False
    if re.search(r"[абвгде]\)", s, re.I):
        return False
    if re.search(r"\by\s*=", s, re.I):
        return False
    if re.search(r"\bx\s*[=+\-]", s, re.I) and "=" in s:
        return False
    if len(re.findall(r"\bx\s*=", s, re.I)) >= 2:
        return False
    if re.match(r"^[<>≤≥]", s):
        return False
    if re.search(r"\bx\s*[=+\-]", s, re.I):
        return False
    if re.search(r"[<>]\s*\d", s):
        return False
    if "," in s and re.search(r"x\s*=", s, re.I):
        return False
    if re.match(r"^—\s*\d+\)", s):
        return False
    if re.fullmatch(r"[\d\s]+:[\d\s:]+", s.replace(" ", "")):
        return False
    if re.search(r"[а-яё]{4,}", s, re.I):
        return False
    if not _is_final_numeric_value(s):
        return False
    return True


def _strip_subitem_prefix(line: str) -> str:
    return re.sub(r"^[абвгдежзийклмнопрстуфхцчшщъыьэюя]\)\s*", "", (line or "").strip(), flags=re.I)


def _mixed_fractions_to_sympy(line: str) -> str:
    line = _UNDERSCORE_MIXED.sub(r"(\1+\2/\3)", line)
    return _MIXED_FRAC.sub(r"(\1+\2/\3)", line)


def _normalize_school_arith_line(line: str) -> str:
    s = (line or "").strip()
    s = s.replace("×", "*").replace("÷", "/").replace("−", "-").replace("–", "-")
    s = s.replace("^", "**")
    s = _decimal_commas_to_dots(s)
    s = _collapse_digit_thousands(s)
    s = _mixed_fractions_to_sympy(s)
    s = _SCHOOL_DIV_FRAC.sub(r"\1/(\2)", s)
    s = _SCHOOL_DIV.sub(r"\1/\2", s)
    s = re.sub(r"\)\s*:\s*(\d+(?:\.\d+)?)", r")/\1", s)
    return s


def _format_decimal_school(val: Decimal, *, template: str = "") -> str:
    if val == val.to_integral_value():
        return str(int(val))
    s = format(val.normalize(), "f").rstrip("0").rstrip(".")
    if "," in template and "." not in template.split(",")[-1][:4]:
        s = s.replace(".", ",")
    return s


def _decimal_eval_fallback(line: str) -> Optional[str]:
    norm = _normalize_school_arith_line(line)
    compact = re.sub(r"\s+", "", norm)
    if not re.fullmatch(r"[\d\.\+\-\*/\(\)]+", compact):
        return None
    try:
        val = Decimal(str(eval(compact, {"__builtins__": {}})))  # noqa: S307
    except (SyntaxError, TypeError, InvalidOperation, ZeroDivisionError):
        return None
    return _format_decimal_school(val, template=line)


def extract_computable_expr_line(question: str) -> Optional[str]:
    """Last question line that looks like a computable arithmetic expression."""
    lines = [ln.strip() for ln in (question or "").splitlines() if ln.strip()]
    for ln in reversed(lines):
        cand = _strip_subitem_prefix(ln).rstrip(";").strip()
        cand = cand.replace("×", "*").replace("÷", "/").replace("−", "-").replace("–", "-")
        if not re.search(r"[0-9]", cand):
            continue
        if not re.search(r"[\+\-\*/]", cand):
            continue
        # Skip prose / geometry / MCQ stems.
        if re.search(r"[а-яё]{4,}", cand, re.I):
            continue
        if re.search(r"[a-zA-Z]{2,}", cand):
            continue
        if not _is_pure_numeric_expression(cand):
            continue
        if re.search(r"[=?]", cand):
            continue
        if "..." in cand or "…" in cand:
            continue
        compact = re.sub(r"\s+", "", cand)
        if len(compact) > 120:
            continue
        return cand
    return None


def compute_answer_from_question(question: str) -> Optional[str]:
    """
    SymPy-evaluate the last arithmetic line in *question*.
    Returns school-formatted answer string, or None if not computable.
    """
    line = extract_computable_expr_line(question)
    if not line or not _is_pure_numeric_expression(line):
        return None
    if line.count(":") >= 2:
        return None

    sympy_line = _normalize_school_arith_line(line)
    target = parse_expr(sympy_line)
    if target is not None:
        try:
            import sympy

            simplified = sympy.simplify(target)
            if simplified is not None:
                out = _expr_to_school_notation(simplified)
                final = _finalize_computed((out or "").strip())
                if final:
                    return final
        except Exception:
            pass

    return _finalize_computed(_decimal_eval_fallback(line))


def _finalize_computed(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    out = raw.strip()
    if not _is_numeric_computed_result(out):
        return None
    return out


def _repeating_decimal_float(s: str) -> Optional[float]:
    s = (s or "").strip().replace(" ", "")
    m = re.fullmatch(r"(\d+),\((\d+)\)", s)
    if m:
        head, rep = m.group(1), m.group(2)
        return float(f"{head}.{rep}" + rep * 8)
    m = re.fullmatch(r"(\d+),(\d+)\((\d+)\)", s)
    if m:
        head, pre, rep = m.group(1), m.group(2), m.group(3)
        return float(f"{head}.{pre}" + rep * 8)
    return None


def is_high_confidence_arithmetic(question: str) -> bool:
    """Single-expression compute tasks (not algebra / multi-part prose)."""
    q = (question or "").lower()
    if "..." in question or "…" in question:
        return False
    skip_phrases = (
        "можно ли",
        "сколько знаков",
        "почему?",
        "проверьте сложением",
        "с помощью микрокалькулятора",
        "придумайте способ",
        "выразите дробь",
        "представьте обыкновенную дробь",
        "запишите отношение",
        "отношение дробей",
        "замените звездочки",
        "выполните деление",
        "решите уравнение",
    )
    if any(p in q for p in skip_phrases):
        return False
    if len(re.findall(r"[абвгде]\)", question, re.I)) > 1:
        return False
    if "выполните действ" in q or "найдите значение выраж" in q:
        return True
    lines = [ln.strip() for ln in (question or "").splitlines() if ln.strip()]
    hits = 0
    for ln in lines:
        cand = _strip_subitem_prefix(ln).rstrip(";").strip()
        if _is_pure_numeric_expression(cand) and not re.search(r"[=?]", cand):
            hits += 1
    return hits == 1


def stored_matches_computed(
    question: str,
    stored: str,
    *,
    answer_type: str = "text",
) -> Optional[bool]:
    """
    True  — stored matches local SymPy result.
    False — computable but stored differs.
    None  — cannot compute locally.
    """
    computed = compute_answer_from_question(question)
    if not computed:
        return None
    if not _looks_numeric_answer(stored):
        return None
    stored_norm = _normalize_stored_numeric_answer(stored)
    at = (answer_type or "text").lower().strip()
    if answers_equivalent(stored_norm, computed, at, question=question):
        return True
    if answers_equivalent(stored, computed, at, question=question):
        return True
    try:
        cf = float(computed.replace(",", ".").replace(" ", ""))
        for cand in (stored_norm, stored):
            rf = _repeating_decimal_float(cand)
            if rf is not None and abs(rf - cf) < 1e-4:
                return True
            try:
                sf = float(cand.replace(",", ".").replace(" ", ""))
                if abs(sf - cf) < 1e-4:
                    return True
                if sf != 0 and abs(sf - cf) / max(abs(sf), 1) < 0.001:
                    return True
            except ValueError:
                pass
    except ValueError:
        pass
    return False


def safe_autofix_candidate(
    question: str,
    stored: str,
    computed: str,
    *,
    split_from: str | None = None,
) -> bool:
    """Conservative gate before overwriting DB answer with local compute."""
    if not computed or not stored:
        return False
    if not is_high_confidence_arithmetic(question):
        return False
    if not _looks_numeric_answer(stored) or not _is_final_numeric_value(computed):
        return False
    st = stored.strip()
    if st.startswith(("<", ">", "—", "да", "нет")):
        return False
    if re.search(r"[абвгде]\)", st, re.I):
        return False
    if re.search(r"\bx\s*=", st, re.I):
        return False
    if re.search(r"[a-zA-Z=]", st):
        return False
    if re.search(r"\(\d\)", st):
        return False
    try:
        c_num = float(computed.replace(",", ".").replace(" ", ""))
        s_num = float(_normalize_stored_numeric_answer(st).replace(",", ".").replace(" ", ""))
        if abs(c_num) > 1e12:
            return False
        if s_num >= 0 and c_num < -1e6:
            return False
        if s_num != 0 and abs(c_num - s_num) / max(abs(s_num), 1) > 1000:
            return False
    except ValueError:
        pass
    if split_from:
        return True
    qlow = (question or "").lower()
    if "выполните действ" not in qlow:
        return False
    # Non-split «выполните действие» only when mismatch is modest (OCR typo), not shuffle.
    try:
        c_num = float(computed.replace(",", ".").replace(" ", ""))
        s_num = float(_normalize_stored_numeric_answer(st).replace(",", ".").replace(" ", ""))
        if s_num == 0:
            return abs(c_num) < 1e6
        rel = abs(c_num - s_num) / max(abs(s_num), 1)
        return rel < 0.05
    except ValueError:
        return False
