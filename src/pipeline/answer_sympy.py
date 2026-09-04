"""SymPy-backed answer comparison for verify pipeline."""
from __future__ import annotations

import logging
import random
import re
from typing import Optional

log = logging.getLogger(__name__)

_SYMBOL_NAMES = "abcdefghijklmnopqrsuvwxyz"


def _latexish_to_sympy(s: str) -> str:
    s = (s or "").strip()
    sci_tokens: list[str] = []

    def _stash_sci(m: re.Match) -> str:
        sci_tokens.append(m.group(0))
        return f"__SCI{len(sci_tokens) - 1}__"

    s = re.sub(r"\d+\.?\d*[eE][+-]?\d+", _stash_sci, s)
    s = s.replace("−", "-").replace("–", "-").replace("—", "-")
    s = s.replace("√", "sqrt").replace("×", "*").replace("·", "*")
    s = s.replace("^", "**")
    s = re.sub(r"\\sqrt\{([^}]+)\}", r"sqrt(\1)", s)
    s = re.sub(r"\\sqrt\[3\]\{([^}]+)\}", r"(\1)**(1/3)", s)
    s = re.sub(r"\\frac\{([^}]+)\}\{([^}]+)\}", r"((\1)/(\2))", s)
    s = re.sub(r"\$", "", s)
    s = re.sub(r"\\left|\\right", "", s)
    s = re.sub(r"\\cdot", "*", s)
    s = re.sub(r"\\times", "*", s)
    s = re.sub(r",(\d)", r".\1", s)
    # LaTeX / school exponents: a^{-10}, a**{-10}, ^{12}
    s = re.sub(r"\*\*\{([^}]+)\}", r"**(\1)", s)
    s = re.sub(r"\^\{([^}]+)\}", r"**(\1)", s)
    s = re.sub(r"([a-zA-Z0-9\)])\{(-?[^}]+)\}", r"\1**(\2)", s)
    # implicit multiplication: 2n, 4a, 1/7 a, )b, **(-10)b
    s = re.sub(r"(\d)([a-zA-Z])", r"\1*\2", s)
    s = re.sub(r"(\d)\s+([a-zA-Z(])", r"\1*\2", s)
    s = re.sub(r"\)\s*([a-zA-Z])", r")*\1", s)
    s = re.sub(r"(\*\*\([^)]+\))([a-zA-Z])", r"\1*\2", s)
    s = re.sub(r"([a-zA-Z0-9\)])(\s+)([a-zA-Z(])", r"\1*\3", s)
    s = re.sub(r"\)\s*\(", r")*(", s)
    s = re.sub(r"sqrt\*\(", "sqrt(", s)
    for i, tok in enumerate(sci_tokens):
        s = s.replace(f"__SCI{i}__", tok)
    return s


def _normalize_school_expression(s: str) -> str:
    """School LaTeX/unicode → SymPy-parseable (incl. a√a ↔ a**(3/2))."""
    s = (s or "").strip()
    # a\sqrt{b} → a*sqrt(b) before generic sqrt pass
    s = re.sub(r"([a-zA-Z0-9\)])\\sqrt\{([^}]+)\}", r"\1*sqrt(\2)", s)
    s = re.sub(r"([a-zA-Z])√\s*([a-zA-Z])", r"\1*sqrt(\2)", s)
    s = re.sub(r"(\d+)√\s*(\d+)", r"\1*sqrt(\2)", s)
    s = _latexish_to_sympy(s)
    # var*sqrt(var) or sqrt(var)*var → var**(3/2)
    for _ in range(2):
        s = re.sub(r"([a-zA-Z])\*sqrt\(\1\)", r"\1**(3/2)", s, flags=re.I)
        s = re.sub(r"sqrt\(([a-zA-Z])\)\*\1", r"\1**(3/2)", s, flags=re.I)
    return s


def _strip_units(s: str) -> str:
    return re.sub(r"\s*(г|кг|м/с|ч|сек|с)\s*$", "", (s or "").strip(), flags=re.I)


def _normalize_decimal_commas(s: str) -> str:
    """0,15 → 0.15; keep 10^-23 intact."""
    s = (s or "").strip()
    s = re.sub(r"(\d),(\d)", r"\1.\2", s)
    return s


def _extract_assignments(question: str) -> dict[str, str]:
    """x = -0,37, y = -0,42 or v = 15 from question tail."""
    assigns: dict[str, str] = {}
    for line in (question or "").splitlines():
        if not re.search(r"=\s*[-\d]", line):
            continue
        chunks = re.split(r",\s*(?=[a-zA-Z]\s*=)", line)
        for chunk in chunks:
            m = re.match(r"([a-zA-Z])\s*=\s*(.+)$", chunk.strip().rstrip(";"))
            if m:
                val = _normalize_decimal_commas(m.group(2).strip())
                if val and re.search(r"\d", val):
                    assigns[m.group(1)] = val
        for m in re.finditer(r"[а-я]\)\s*([a-zA-Z])\s*=\s*([^;]+)", line, re.I):
            val = _normalize_decimal_commas(m.group(2).strip())
            if val and re.search(r"\d", val):
                assigns[m.group(1)] = val
    return assigns


def _eval_expr_numeric(expr_str: str, assigns: dict[str, str]) -> Optional[float]:
    """Substitute assignments and evaluate to float."""
    try:
        import sympy
        from sympy import N, Rational

        expr = parse_expr(expr_str)
        if expr is None:
            return None
        subs: dict = {}
        for var, val_s in assigns.items():
            sym = sympy.Symbol(var)
            inner = parse_expr(_normalize_school_expression(val_s))
            if inner is not None:
                subs[sym] = inner
            else:
                try:
                    subs[sym] = float(val_s)
                except ValueError:
                    return None
        val = N(expr.subs(subs))
        if val.is_real:
            return float(val)
    except Exception:
        pass
    return None


def _parse_scientific_value(s: str) -> Optional[float]:
    s = _normalize_school_expression(_strip_units(_normalize_decimal_commas(s)))
    m = re.match(
        r"^([\d.]+)\s*(?:\*|×|·)?\s*10\s*\*\*\s*\(?(-?\d+)\)?$",
        s,
        re.I,
    )
    if not m:
        m = re.match(r"^([\d.]+)\s*(?:\*|×)?\s*10\^\{?(-?\d+)\}?$", s, re.I)
    if m:
        return float(m.group(1)) * (10 ** int(m.group(2)))
    try:
        return float(s)
    except ValueError:
        return None


def _extract_comparison_exprs(question: str) -> tuple[str, str] | None:
    """Two expressions from 'Сравните ... A и B'."""
    q = (question or "").replace("$", "")
    if not re.search(r"сравните", q, re.I):
        return None
    # last line often: expr1 и expr2
    for line in reversed(q.splitlines()):
        line = line.strip().rstrip(";")
        if re.search(r"\sи\s", line, re.I) and re.search(r"[\d\\sqrt]", line, re.I):
            parts = re.split(r"\s+и\s+", line, maxsplit=1, flags=re.I)
            if len(parts) == 2:
                return parts[0].strip(), parts[1].strip()
    return None


def _parse_relation(answer: str) -> tuple[str, str, str] | None:
    """lhs rel rhs from answer like 'a > b' or 'a = b'."""
    s = _normalize_school_expression(_strip_units(answer))
    m = re.match(r"^(.+?)\s*(=|<|>|≤|>=|<=|≥)\s*(.+)$", s)
    if not m:
        return None
    rel = m.group(2).replace("≤", "<=").replace("≥", ">=")
    return m.group(1).strip(), rel, m.group(3).strip()


def _relation_holds(lhs: float, rel: str, rhs: float) -> bool:
    if rel == "=":
        return abs(lhs - rhs) < 1e-4
    if rel == "<":
        return lhs < rhs - 1e-9
    if rel == ">":
        return lhs > rhs + 1e-9
    if rel == "<=":
        return lhs <= rhs + 1e-9
    if rel == ">=":
        return lhs >= rhs - 1e-9
    return False


def _fraction_list_parts(s: str) -> list[str]:
    s = (s or "").strip()
    s = re.sub(r"^[:\s]+", "", s)
    parts = re.split(r"\s+и\s+", s, flags=re.I)
    if len(parts) < 2:
        parts = [p.strip() for p in s.split(",") if p.strip()]
    out: list[str] = []
    for p in parts:
        p = re.sub(r"^\d+\)\s*", "", p).strip()
        if p:
            out.append(p)
    return out


def eval_computed_for_question(question: str, computed: str) -> Optional[str]:
    """Numeric value when question gives variable assignments."""
    assigns = _extract_assignments(question)
    if not assigns:
        return None
    if len(re.findall(r"[а-я]\)\s*[a-zA-Z]\s*=", question or "", re.I)) >= 2:
        return None
    val = _eval_expr_numeric(computed, assigns)
    if val is None:
        return None
    if abs(val - round(val)) < 1e-6:
        return str(int(round(val)))
    return str(round(val, 6)).rstrip("0").rstrip(".")


def _parse_mixed_number(s: str) -> Optional[float]:
    s = (s or "").strip()
    m = re.match(r"^(\d+)\s+(\d+)/(\d+)$", s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / int(m.group(3))
    try:
        from fractions import Fraction

        return float(Fraction(_normalize_school_expression(s)))
    except Exception:
        return None


def _validate_formula_with_cases(question: str, answer: str, formula_expr: str) -> bool:
    """Formula + а) v=… numeric parts — e.g. t = 30/v + 17/(v+2); а) 3; б) 2 31/60."""
    parts = split_answer_parts(answer)
    if len(parts) < 2:
        return False
    formula_part = parts[0].strip()
    fm = re.match(r"^([a-zA-Z])\s*=\s*(.+)$", formula_part)
    rhs = fm.group(2).strip() if fm else formula_part
    if sympy_equivalent(rhs, formula_expr, "expression") is not True:
        if sympy_equivalent(formula_expr, rhs, "expression") is not True:
            return False
    case_parts = parts[1:]
    case_specs = re.findall(r"[а-я]\)\s*([a-zA-Z])\s*=\s*([^;]+)", question, re.I)
    if len(case_specs) != len(case_parts):
        return False
    for (var, val_s), part in zip(case_specs, case_parts):
        assigns = {var: _normalize_decimal_commas(val_s.strip())}
        got = _eval_expr_numeric(formula_expr, assigns)
        if got is None:
            return False
        part_clean = re.sub(r"\s*ч\s*$", "", part.strip(), flags=re.I)
        exp = _parse_mixed_number(part_clean) or _parse_mixed_number(
            _normalize_decimal_commas(part_clean)
        )
        if exp is None:
            try:
                exp = float(_normalize_decimal_commas(part_clean))
            except ValueError:
                return False
        if abs(got - exp) > 0.02:
            return False
    return True


def try_validate_expression_answer(question: str, answer: str) -> Optional[bool]:
    """Validate expression answer against question (substitution, compare, numeric)."""
    q = (question or "").strip()
    ans = _normalize_decimal_commas(_strip_units((answer or "").strip()))
    if not q or not ans:
        return None

    # Constraint n < 0: |n| vs -n
    if re.search(r"n\s*<\s*0", q, re.I):
        ea, eb = parse_expr(ans), parse_expr("Abs(n)")
        if ea is not None and eb is not None:
            try:
                import sympy
                from sympy import N

                n = sympy.Symbol("n")
                if abs(float(N(ea.subs(n, -3))) - float(N(eb.subs(n, -3)))) < 1e-6:
                    return True
            except Exception:
                pass

    # Comparison: sqrt(24) = 1/3*sqrt(216)
    pair = _extract_comparison_exprs(q)
    rel = _parse_relation(ans)
    if pair and rel:
        lhs_a, op, rhs_a = rel
        v1 = _eval_expr_numeric(lhs_a, {}) if not _extract_assignments(q) else None
        # numeric eval both sides of relation
        try:
            import sympy
            from sympy import N

            e1, e2 = parse_expr(lhs_a), parse_expr(rhs_a)
            if e1 is not None and e2 is not None:
                f1, f2 = float(N(e1)), float(N(e2))
                return _relation_holds(f1, op, f2)
        except Exception:
            pass

    # Scientific notation
    sci = _parse_scientific_value(ans)
    if sci is not None and re.search(r"10\s*\^", q):
        m_mol = re.search(r"([\d.,]+)\s*\*\s*10\s*\^?\s*(\d+)", q.replace(" ", ""))
        m_g = re.search(r"(\d+)\s*г", q)
        if m_mol and m_g:
            molecules = float(m_mol.group(1).replace(",", ".")) * (10 ** int(m_mol.group(2)))
            mass = float(m_g.group(1))
            expected = mass / molecules
            if abs(sci - expected) / max(abs(expected), 1e-30) < 0.02:
                return True

    # Substitution numeric answer — validated via eval_computed_for_question in gate
    assigns = _extract_assignments(q)
    if assigns and re.search(r"^[-\d.]", ans):
        return None

    # Formula + labeled numeric cases: t = …; а) 3; б) 2 31/60
    if re.search(r"[а-я]\)\s*[a-zA-Z]\s*=", q, re.I) and ";" in ans:
        parts = split_answer_parts(ans)
        if len(parts) >= 2:
            fm = re.match(r"^([a-zA-Z])\s*=\s*(.+)$", parts[0].strip())
            if fm and _validate_formula_with_cases(q, ans, fm.group(2)):
                return True

    # Fraction list: 10/14 и 3/14
    fracs = _fraction_list_parts(ans)
    if len(fracs) >= 2 and re.search(r"знаменател", q, re.I):
        try:
            from fractions import Fraction

            got = [Fraction(_normalize_school_expression(f)) for f in fracs]
            # from question line 5/7 и 3/14
            for line in q.splitlines():
                if " и " in line and "/" in line:
                    src = _fraction_list_parts(line)
                    if len(src) == len(got):
                        exp = [Fraction(_normalize_school_expression(f)) for f in src]
                        # allow non-reduced vs reduced
                        if len(got) == len(exp) and all(
                            a == b or float(a) == float(b) for a, b in zip(sorted(got, key=float), sorted(exp, key=float))
                        ):
                            return True
        except Exception:
            pass

    return try_validate_answer_for_question(q, ans, "expression")


def split_answer_parts(answer: str) -> list[str]:
    """Split multi-part answers (а) б) в); ...; or comma-separated fractions)."""
    s = (answer or "").strip()
    if not s:
        return []

    def _clean(parts: list[str]) -> list[str]:
        cleaned: list[str] = []
        for p in parts:
            p = re.sub(r"^[абвгдежзийклмнопрстуфхцчшщъыьэюя]\)\s*", "", p, flags=re.I)
            p = re.sub(r"^\d+\)\s*", "", p)
            p = p.strip()
            if p:
                cleaned.append(p)
        return cleaned

    if ";" in s:
        parts = _clean(re.split(r"\s*;\s*", s))
        if parts:
            return parts

    if "," in s:
        cand = _clean(re.split(r",\s+", s))
        if len(cand) >= 2 and all(
            re.search(r"[=/^()]|[a-zA-Z]", p) for p in cand
        ):
            return cand

    parts = _clean([s])
    return parts if parts else [s]


def parse_expr(expr_str: str):
    """Parse math string to SymPy expression, or None."""
    try:
        import sympy
        from sympy.parsing.sympy_parser import (
            implicit_multiplication_application,
            parse_expr,
            standard_transformations,
        )
    except ImportError:
        return None

    raw = _normalize_school_expression(expr_str)
    if not raw:
        return None

    transformations = standard_transformations + (implicit_multiplication_application,)
    try:
        from sympy import sqrt

        local_dict = {"sqrt": sqrt}
        return parse_expr(
            raw,
            transformations=transformations,
            evaluate=True,
            local_dict=local_dict,
        )
    except Exception:
        pass
    try:
        from sympy.parsing.latex import parse_latex

        return parse_latex(expr_str)
    except Exception:
        pass
    try:
        return sympy.sympify(raw.replace("**", "^"))
    except Exception:
        return None


#: Показатель степени выше этого раскрывать бессмысленно: школьный ответ таких
#: не содержит, а `simplify` на них уходит в перебор.
_MAX_EXPONENT = 64

#: Порог размера дерева выражения. Школьный ответ до него не дотягивает.
_MAX_OPS = 200


def _too_hard_for_simplify(expr) -> bool:
    """Выражение, на котором `sympy.simplify` может не вернуться.

    Найдено живым замером по выгрузке прода (2026-09-02). Задача
    `G7_ALG_18_13.4` содержит ответ `a^{36} - 3a^{24b}^{13} + …` — испорченный
    распознаванием `a^{24}b^{13}`, где показателем степени стала **переменная**.
    KaTeX такую формулу компилирует молча, разбор проходит, а `simplify`
    на ней не возвращается: замер показал больше двух минут без признаков
    завершения.

    Прервать это извне нельзя. `signal.alarm` не помогает: SymPy в этот момент
    внутри C-кода, и питоновский обработчик сигнала не выполняется, пока
    управление не вернётся в интерпретатор — проверено, будильник на 5 секунд
    не сработал за 120. Значит, единственная защита — не звать `simplify`
    вовсе. Проверка дерева стоит микросекунды, в отличие от самого вызова.

    Возврат `True` означает «не берусь», а не «выражения разные»: вызывающий
    падает на численную проверку и Монте-Карло, которые ограничены по времени
    по самой своей природе.
    """
    try:
        import sympy
    except ImportError:  # pragma: no cover — sympy в requirements
        return False

    try:
        for power in expr.atoms(sympy.Pow):
            exponent = power.exp
            # Переменная в показателе — тот самый случай G7_ALG_18_13.4.
            if exponent.free_symbols:
                return True
            if exponent.is_Integer and abs(int(exponent)) > _MAX_EXPONENT:
                return True
        if sympy.count_ops(expr) > _MAX_OPS:
            return True
    except Exception:  # noqa: BLE001 — любой сбой обхода означает «не берусь»
        return True
    return False


def _exprs_equivalent(a, b) -> bool:
    import sympy

    if _too_hard_for_simplify(a) or _too_hard_for_simplify(b):
        log.debug("simplify пропущен: выражение вне границ (%.60s / %.60s)", a, b)
        return False

    try:
        if sympy.simplify(a - b) == 0:
            return True
    except Exception:
        pass
    try:
        if sympy.Eq(sympy.simplify(a), sympy.simplify(b)):
            return True
    except Exception:
        pass
    return False


def monte_carlo_equivalent(a_str: str, b_str: str, *, trials: int = 6) -> Optional[bool]:
    """
    True/False if expressions likely equivalent/different via random substitution.
    None if cannot parse or compare.
    """
    a = parse_expr(a_str)
    b = parse_expr(b_str)
    if a is None or b is None:
        return None

    try:
        from sympy.core.expr import Expr
    except ImportError:
        Expr = object  # type: ignore

    if not isinstance(a, Expr) or not isinstance(b, Expr):
        return None

    # Подстановка чисел в выражение с переменной в показателе — не быстрее
    # `simplify`, а медленнее: `a**(876488338465357824*b**13)` при `a=3, b=5`
    # заставляет Python считать целое число с квинтиллионом цифр. Именно здесь
    # вешалась задача `G7_ALG_18_13.4`, а не в `simplify`, как показалось
    # сначала. Тот же заслон, что и там: не берёмся — значит `None`.
    if _too_hard_for_simplify(a) or _too_hard_for_simplify(b):
        log.debug("Монте-Карло пропущено: выражение вне границ")
        return None

    if _exprs_equivalent(a, b):
        return True

    try:
        import sympy
        from sympy import N
    except ImportError:
        return None

    syms = list(a.free_symbols | b.free_symbols)
    if not syms:
        try:
            return abs(float(N(a)) - float(N(b))) < 1e-6
        except Exception:
            return None

    rng = random.Random(42)
    for _ in range(trials):
        subs = {s: rng.randint(2, 11) for s in syms}
        try:
            va = complex(N(a.subs(subs)))
            vb = complex(N(b.subs(subs)))
            if abs(va - vb) > 1e-5:
                return False
        except Exception:
            return None
    return True


def _is_boolean_atom(expr) -> bool:
    """Свернулось ли выражение в булеву константу (`BooleanTrue`/`BooleanFalse`).

    Так выглядит закрытое сравнение без свободных переменных: `21 > 2` → True.
    """
    try:
        from sympy.logic.boolalg import BooleanAtom

        return isinstance(expr, BooleanAtom)
    except ImportError:  # pragma: no cover — sympy в requirements
        return isinstance(expr, bool)


def sympy_equivalent(a: str, b: str, answer_type: str = "") -> Optional[bool]:
    """
    True = mathematically same, False = different, None = cannot decide.
    """
    a = (a or "").strip()
    b = (b or "").strip()
    if not a or not b:
        return None
    if a == b:
        return True

    pa, pb = split_answer_parts(a), split_answer_parts(b)
    if len(pa) == len(pb) and len(pa) > 1:
        results = [sympy_equivalent(x, y, answer_type) for x, y in zip(pa, pb)]
        if any(r is False for r in results):
            return False
        if all(r is True for r in results):
            return True
        return None

    ea, eb = parse_expr(a), parse_expr(b)
    if ea is not None and eb is not None:
        # Закрытое числовое сравнение SymPy сворачивает в булево:
        # `21 > 2` → True и `21 > -12` → True. Сравнивать эти булевы между
        # собой нельзя — иначе ЛЮБЫЕ два истинных (или два ложных) неравенства
        # объявляются одним ответом. Истинность высказывания ≠ равенство
        # ответов, решить этот случай SymPy не может → None, пусть решают
        # структурные проверки выше (`_numeric_inequality_equivalent` и др.).
        if _is_boolean_atom(ea) and _is_boolean_atom(eb):
            return None
        if _exprs_equivalent(ea, eb):
            return True
        mc = monte_carlo_equivalent(a, b)
        if mc is not None:
            return mc
        return False

    mc = monte_carlo_equivalent(a, b)
    if mc is not None:
        return mc
    return None


def sympy_numeric_equal(a: str, b: str) -> Optional[bool]:
    ea, eb = parse_expr(a), parse_expr(b)
    if ea is None or eb is None:
        return None
    try:
        from sympy import N

        return abs(float(N(ea)) - float(N(eb))) < 1e-6
    except Exception:
        return None


def try_validate_answer_for_question(question: str, answer: str, answer_type: str) -> Optional[bool]:
    """
    When possible, check answer against expression extracted from question.
    True = answer matches simplified target, False = mismatch, None = unknown.
    """
    q = (question or "").strip()
    ans = (answer or "").strip()
    if not q or not ans:
        return None

    at = (answer_type or "").lower()
    if at not in ("expression", "fraction", "exact_number", "decimal"):
        return None

    # Last math-heavy line in question (after split_compound often the sub-expression)
    lines = [ln.strip() for ln in q.splitlines() if ln.strip()]
    expr_line = ""
    for ln in reversed(lines):
        if re.search(r"[0-9a-z\\$+\-*/^()=]", ln, re.I):
            expr_line = ln
            break
    if not expr_line:
        expr_line = lines[-1] if lines else q

    expr_line = re.sub(r"^[абвгдежзийклмнопрстуфхцчшщъыьэюя]\)\s*", "", expr_line, flags=re.I)
    expr_line = expr_line.rstrip(";").strip()

    target = parse_expr(expr_line)
    if target is None:
        return None

    try:
        import sympy
        from sympy import N

        if _too_hard_for_simplify(target):
            return None
        simplified = sympy.simplify(target)
        answer_expr = parse_expr(ans)
        if answer_expr is None:
            return None
        if _exprs_equivalent(simplified, answer_expr):
            return True
        mc = monte_carlo_equivalent(str(simplified), ans)
        if mc is True:
            return True
        if mc is False:
            return False
        try:
            return abs(float(N(simplified)) - float(N(answer_expr))) < 1e-5
        except Exception:
            return None
    except Exception:
        return None
