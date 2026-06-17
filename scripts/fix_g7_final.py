r"""
G7 финальные исправления — без AI, чистая логика.

1. set-задачи "найди алгебраическую дробь" → правильные ответы + MCQ диcтракторы
2. "Проверьте верность равенства" → дистрактор "Равенство неверно"
3. "Замените знак ? знаком + или -" → дистрактор противоположный знак
4. exact_number без дистракторов → числовые дистракторы (±небольшое отклонение)
"""
from __future__ import annotations

import json
import logging
import sys

sys.path.insert(0, "/app")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("fix_g7_final")

from sqlalchemy import create_engine, text
from src.core.config import get_settings

engine = create_engine(get_settings().database_url)


def _save(task_id: str, answer: str | None, dmeta: list, atype: str | None = None):
    params: dict = {"id": task_id, "dmeta": json.dumps(dmeta, ensure_ascii=False)}
    parts = ["distractor_meta = cast(:dmeta as jsonb)"]
    if answer is not None:
        params["ans"] = answer
        parts.append("correct_answer = :ans")
    if atype is not None:
        params["atype"] = atype
        parts.append("answer_type = :atype")
    sql = f"UPDATE tasks_master SET {', '.join(parts)} WHERE id = :id"
    with engine.begin() as conn:
        conn.execute(text(sql), params)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Алгебраические дроби (set → multiple_choice)
# ══════════════════════════════════════════════════════════════════════════════

# Manually verified answers based on definition:
# Algebraic fraction = fraction with variable in DENOMINATOR
_YES = "Является алгебраической дробью"
_NO  = "Не является алгебраической дробью"

_ALGEBRAIC_FRACTION_TASKS = {
    # task_id: (expression_in_question, is_algebraic_fraction)
    "G7_TB_22_1.1": ("4a/7 + 1/2",           False),  # denominators 7, 2 = constants
    "G7_TB_22_1.2": ("(7a + 5)/11",           False),  # denominator 11 = constant
    "G7_TB_22_1.3": ("1/a + 1/2",             True),   # 1/a → denominator a is variable
    "G7_TB_22_1.4": ("(2x - b)/(2x + b)",     True),   # variable in denominator
    "G7_TB_22_1.5": ("4/(5a + 1)",            True),   # variable in denominator
    "G7_TB_22_1.6": ("1/a + 1/b",             True),   # variables in denominators
    "G7_TB_22_1.7": ("(2a - 1)/(a + 1)",      True),   # variable in denominator
    "G7_TB_22_1.8": ("7c/(4.5 + 2/3)",        False),  # denominator = constant ≈4.83
}

_YES_META = [{"value": _NO,  "error_type": "conceptual_error",
              "explanation": "Ученик ошибочно принял выражение за алгебраическую дробь, "
                             "не проверив наличие переменной в знаменателе.",
              "plausibility": 0.75}]
_NO_META  = [{"value": _YES, "error_type": "conceptual_error",
              "explanation": "Ученик не заметил, что знаменатель содержит только числа "
                             "(без переменных), и ошибочно назвал выражение алгебраической дробью.",
              "plausibility": 0.75}]


def fix_algebraic_fractions():
    log.info("=== Fix 1: Алгебраические дроби ===")
    fixed = 0
    for task_id, (expr, is_alg) in _ALGEBRAIC_FRACTION_TASKS.items():
        answer = _YES if is_alg else _NO
        dmeta  = _NO_META if is_alg else _YES_META
        _save(task_id, answer, dmeta, atype="multiple_choice")
        log.info("  %s → %s", task_id, answer)
        fixed += 1
    log.info("Fix 1 done: %d tasks", fixed)
    return fixed


# ══════════════════════════════════════════════════════════════════════════════
# 2. "Проверьте верность равенства" → дистрактор "Равенство неверно"
# ══════════════════════════════════════════════════════════════════════════════

_VERNOST_META = [{"value": "Равенство неверно", "error_type": "conceptual_error",
                  "explanation": "Ученик не раскрыл скобки полностью или допустил "
                                 "арифметическую ошибку при проверке.",
                  "plausibility": 0.70}]


def fix_equality_checks():
    log.info("=== Fix 2: Проверь верность равенства ===")
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, correct_answer FROM tasks_master
            WHERE id LIKE 'G7_%'
              AND question_text ILIKE '%проверьте верность равенства%'
              AND correct_answer = 'Равенство верно'
              AND (distractor_meta IS NULL OR distractor_meta::text IN ('null', '[]'))
        """)).fetchall()

    fixed = 0
    for task_id, _ in rows:
        _save(task_id, None, _VERNOST_META)
        log.info("  %s → дистрактор добавлен", task_id)
        fixed += 1
    log.info("Fix 2 done: %d tasks", fixed)
    return fixed


# ══════════════════════════════════════════════════════════════════════════════
# 3. "Замените знак ?" — ответ "+" или "-"
# ══════════════════════════════════════════════════════════════════════════════

def fix_sign_replacement():
    log.info("=== Fix 3: Замените знак ===")
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, correct_answer FROM tasks_master
            WHERE id LIKE 'G7_%'
              AND question_text ILIKE '%замените%знак%'
              AND correct_answer IN ('+', '-')
              AND (distractor_meta IS NULL OR distractor_meta::text IN ('null', '[]'))
        """)).fetchall()

    fixed = 0
    for task_id, answer in rows:
        opposite = "-" if answer == "+" else "+"
        explanation = (
            "Ученик не учёл правило раскрытия скобок: перед скобкой стоит минус, "
            "поэтому все знаки внутри меняются на противоположные."
            if answer == "-"
            else
            "Ученик перепутал знак при раскрытии скобок."
        )
        dmeta = [{"value": opposite, "error_type": "sign_error",
                  "explanation": explanation, "plausibility": 0.80}]
        _save(task_id, None, dmeta)
        log.info("  %s (ответ='%s') → дистрактор '%s'", task_id, answer, opposite)
        fixed += 1
    log.info("Fix 3 done: %d tasks", fixed)
    return fixed


# ══════════════════════════════════════════════════════════════════════════════
# 4. exact_number с числовым ответом без дистракторов
# ══════════════════════════════════════════════════════════════════════════════

def fix_exact_number():
    log.info("=== Fix 4: exact_number без дистракторов ===")
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, correct_answer, question_text FROM tasks_master
            WHERE id LIKE 'G7_%'
              AND answer_type = 'exact_number'
              AND correct_answer IS NOT NULL
              AND correct_answer NOT IN ('', '-', '—')
              AND (distractor_meta IS NULL OR distractor_meta::text IN ('null', '[]'))
        """)).fetchall()

    fixed = 0
    for task_id, answer, question in rows:
        # Try to generate numeric distractors via small perturbations
        try:
            # Handle comma decimal separator
            clean = answer.replace(",", ".").strip()
            # Handle "216, 7776" (sequence answer) → skip
            if "," in answer and len(answer.split(",")) > 1:
                try:
                    vals = [float(v.strip()) for v in clean.split(",")]
                    # Too complex for simple distractors
                    log.debug("  SKIP %s — multi-value answer: %s", task_id, answer)
                    continue
                except Exception:
                    pass

            val = float(clean)
        except (ValueError, TypeError):
            log.debug("  SKIP %s — non-numeric: %s", task_id, answer)
            continue

        # Generate 3 plausible wrong answers
        import random
        distractors = []
        seen = {val}

        # Strategy: ±small%, sign flip, off-by-one
        candidates = []
        if val != 0:
            candidates.extend([val * 1.1, val * 0.9, -val])
        candidates.extend([val + 1, val - 1, val * 2, val // 2 if val != 0 else 1])

        error_meta = [
            ("calculation_error",   "Ученик допустил арифметическую ошибку при вычислении."),
            ("sign_error",          "Ученик перепутал знак при раскрытии скобок."),
            ("calculation_error",   "Ученик ошибся при умножении или сложении в промежуточном шаге."),
        ]

        for i, cand in enumerate(candidates):
            cand = round(cand, 6)
            if cand not in seen and cand != val:
                # Format similarly to the original
                if float(cand) == int(cand):
                    cand_str = str(int(cand))
                else:
                    cand_str = str(cand)
                etype, expl = error_meta[len(distractors) % len(error_meta)]
                distractors.append({"value": cand_str, "error_type": etype,
                                    "explanation": expl, "plausibility": 0.70})
                seen.add(cand)
                if len(distractors) >= 3:
                    break

        if distractors:
            _save(task_id, None, distractors)
            log.info("  %s (ans=%s) → %d distractors", task_id, answer, len(distractors))
            fixed += 1

    log.info("Fix 4 done: %d tasks", fixed)
    return fixed


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    log.info("=" * 60)
    log.info("G7 Финальные исправления (без AI)")
    log.info("=" * 60)

    s1 = fix_algebraic_fractions()
    s2 = fix_equality_checks()
    s3 = fix_sign_replacement()
    s4 = fix_exact_number()

    log.info("=" * 60)
    log.info("ИТОГО: дроби=%d | равенства=%d | знаки=%d | числа=%d", s1, s2, s3, s4)
    log.info("=" * 60)

    # Final stats
    import sqlalchemy as sa
    with engine.connect() as conn:
        row = conn.execute(sa.text("""
            SELECT
              COUNT(DISTINCT tm.id) as total,
              ROUND(COUNT(DISTINCT CASE WHEN tm.correct_answer != '' AND tm.correct_answer IS NOT NULL THEN tm.id END)::numeric / COUNT(DISTINCT tm.id) * 100, 1) as ans_pct,
              ROUND(COUNT(DISTINCT CASE WHEN tm.distractor_meta IS NOT NULL AND jsonb_array_length(tm.distractor_meta) > 0 THEN tm.id END)::numeric / COUNT(DISTINCT tm.id) * 100, 1) as dist_pct,
              ROUND(COUNT(DISTINCT CASE WHEN tm.skill_id IS NOT NULL THEN tm.id END)::numeric / COUNT(DISTINCT tm.id) * 100, 1) as skill_pct
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
            WHERE tb.class_level = 7
        """)).fetchone()
    log.info("G7 финал: %d задач | ответы=%s%% | дист=%s%% | навыки=%s%%",
             row[0], row[1], row[2], row[3])


if __name__ == "__main__":
    main()
