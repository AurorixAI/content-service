r"""
G8 полная добивка (fallback после Smart Verify v2).

Шаги:
  1. Skill auto-mapping по toc_id (мгновенно)
  2. AIAnswerSolver для text задач без ответа
  3–6. Дистракторы — только если Smart Verify не завершил задачу

Smart Verify v2 (run_smart_verify.py) — основной путь для verify + distractors.
finish_g8 пропускает задачи со smart_verify_status in
(verified_match, verified_corrected, generated_from_scratch).
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
log = logging.getLogger("finish_g8")

from sqlalchemy import create_engine, text
from src.core.config import get_settings

engine = create_engine(get_settings().database_url)

GRADE = 8
PREFIX = f"G{GRADE}_"


def _save_dist(task_id: str, dmeta: list):
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE tasks_master
            SET distractor_meta = cast(:dmeta as jsonb)
            WHERE id = :id
        """), {"dmeta": json.dumps(dmeta, ensure_ascii=False), "id": task_id})


def _run_distractor_pass(rows, label: str) -> int:
    from src.pipeline.verify_distractor_pass import run_verify_distractor_pass

    stats = run_verify_distractor_pass(engine, rows, label=label)
    return stats.get("new_dist", 0)


def _fetch(where_extra: str = "", params: dict | None = None) -> list:
    sql = f"""
        SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type,
               tm.distractor_meta
        FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE tb.class_level = {GRADE}
          AND tm.correct_answer IS NOT NULL AND tm.correct_answer != ''
          AND COALESCE(tm.tags->>'answer_mismatch', 'false') != 'true'
          AND COALESCE(tm.tags->>'verify_unresolved', 'false') != 'true'
          AND COALESCE(tm.tags->>'verify_conflict', 'false') != 'true'
          AND COALESCE(tm.tags->>'smart_verify_status', '') NOT IN (
            'verified_match', 'verified_corrected', 'generated_from_scratch'
          )
          AND (
            COALESCE(tm.tags->>'answer_gemini_verified', 'false') = 'false'
            OR COALESCE(tm.tags->>'distractor_regen_pending', 'false') = 'true'
            OR (tm.distractor_meta IS NULL OR tm.distractor_meta::text IN ('null','[]'))
          )
          {where_extra}
        ORDER BY tm.answer_type, tm.id
    """
    with engine.connect() as conn:
        return conn.execute(text(sql), params or {}).fetchall()


# ══════════════════════════════════════════════════════════════════════════════
# 1. Skill auto-mapping (by toc_id neighbours)
# ══════════════════════════════════════════════════════════════════════════════

def step1_skills():
    """
    SkeletonTextbookMapper на задачах без skill_id.
    Принцип: conf >= 0.70 → skill_id, иначе NULL (toc_id достаточно).
    """
    log.info("=== Step 1: Skill mapping via SkeletonTextbookMapper ===")
    MIN_CONF = 0.70

    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT tm.id, tm.question_text, tm.question_latex,
                   tm.correct_answer, tm.answer_type, tm.difficulty,
                   toc.number, toc.title
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            WHERE tm.id LIKE :prefix AND tm.skill_id IS NULL
            ORDER BY tm.id
        """), {"prefix": f"{PREFIX}%"}).fetchall()

    if not rows:
        log.info("  Нет задач без skill_id")
        return 0

    log.info("  %d задач без skill_id → SkeletonTextbookMapper (conf >= %.2f)", len(rows), MIN_CONF)

    from src.pipeline.classification import SkeletonTextbookMapper
    from src.pipeline.models import ExtractedTask

    mapper = SkeletonTextbookMapper()
    mapper.load_skills_from_db(get_settings().database_url, class_level=GRADE)

    assigned = kept_null = 0
    for tid, question, latex, answer, atype, diff, para_num, para_title in rows:
        et = ExtractedTask(
            temp_id=tid,
            question_text=question or "",
            question_latex=latex or "",
            answer_raw=answer or "",
            answer_type=atype or "exact_number",
            difficulty=diff or "B",
            paragraph_number=str(para_num or ""),
            paragraph_title=para_title or "",
        )
        try:
            mapper.map_task(et)
        except Exception as e:
            log.debug("  %s error: %s", tid, e)
            kept_null += 1
            continue

        conf = getattr(et, "mapping_confidence", 0.0) or 0.0
        if et.skill_id and conf >= MIN_CONF:
            with engine.begin() as conn:
                conn.execute(text("UPDATE tasks_master SET skill_id=:s WHERE id=:id"),
                             {"s": et.skill_id, "id": tid})
            log.info("  ✓ %s → %s (conf=%.2f)", tid, et.skill_id, conf)
            assigned += 1
        else:
            kept_null += 1  # NULL — нормально, toc_id есть

    log.info("Step 1 done: %d skill_id assigned | %d kept NULL", assigned, kept_null)
    return assigned


# ══════════════════════════════════════════════════════════════════════════════
# 2. AI answers for text tasks without answer
# ══════════════════════════════════════════════════════════════════════════════

def step2_ai_answers():
    log.info("=== Step 2: AI answers (text tasks) ===")
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT tm.id, tm.question_text, tm.answer_type
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
            WHERE tb.class_level = {GRADE}
              AND (tm.correct_answer = '' OR tm.correct_answer IS NULL)
        """)).fetchall()

    if not rows:
        log.info("  No missing answers")
        return 0

    log.info("  %d tasks to solve", len(rows))
    try:
        from src.pipeline.models import ExtractedTask
        try:
            from src.pipeline.enrichment import AIAnswerSolver as _Solver; _m = "solve"
        except ImportError:
            from src.pipeline.enrichment import AIEnricher as _Solver; _m = "enrich"
        solver = _Solver()
    except Exception as e:
        log.error("  Solver unavailable: %s", e); return 0

    solved = 0
    for task_id, question, atype in rows:
        et = ExtractedTask(temp_id=task_id, question_text=question or "", answer_type=atype or "text")
        result = getattr(solver, _m)(et)
        ans = (result.answer_raw or "").strip()
        if ans and ans not in ("", "—", "-", "?"):
            with engine.begin() as conn:
                conn.execute(text("UPDATE tasks_master SET correct_answer=:a WHERE id=:id"),
                             {"a": ans, "id": task_id})
            log.info("  %s → %s", task_id, ans[:60])
            solved += 1

    log.info("Step 2 done: %d solved", solved)
    return solved


# ══════════════════════════════════════════════════════════════════════════════
# 3. Expression → Gemini Pro (context-aware student mistakes)
#    SymPy используется ТОЛЬКО для валидации в generate_distractors()
# ══════════════════════════════════════════════════════════════════════════════

def step3_expression_gemini():
    log.info("=== Step 3: Expression distractors via Gemini Flash ===")
    rows = _fetch("AND tm.answer_type = 'expression'")
    log.info("  %d expression tasks", len(rows))
    n = _run_distractor_pass(rows, "expression")
    log.info("Step 3 done: %d expression distractors (new/corrected only)", n)
    return n


# ══════════════════════════════════════════════════════════════════════════════
# 4. Equation/inequality/fraction/set/MC → Gemini
# ══════════════════════════════════════════════════════════════════════════════

def step4_gemini_algebraic():
    log.info("=== Step 4: Algebraic distractors via Gemini ===")
    types = "('equation_solution', 'inequality', 'fraction', 'set', 'multiple_choice')"
    rows = _fetch(f"AND tm.answer_type IN {types}")
    log.info("  %d algebraic tasks (equation/ineq/frac/set/mc)", len(rows))
    n = _run_distractor_pass(rows, "algebraic")
    log.info("Step 4 done: %d algebraic distractors", n)
    return n


# ══════════════════════════════════════════════════════════════════════════════
# 5. exact_number → numeric perturbation
# ══════════════════════════════════════════════════════════════════════════════

def step5_exact_number():
    log.info("=== Step 5: Exact number distractors (Gemini + SymPy validate) ===")
    rows = _fetch("AND tm.answer_type = 'exact_number'")
    log.info("  %d exact_number tasks", len(rows))
    n = _run_distractor_pass(rows, "exact_number")
    log.info("Step 5 done: %d number distractors", n)
    return n


# ══════════════════════════════════════════════════════════════════════════════
# 6. Text tasks → Gemini (only those with non-trivial computable answers)
# ══════════════════════════════════════════════════════════════════════════════

def step6_text_gemini():
    log.info("=== Step 6: Text distractors via Gemini ===")
    rows = _fetch("""
        AND tm.answer_type = 'text'
        AND LENGTH(tm.correct_answer) < 80
        AND tm.correct_answer NOT ILIKE '%таблиц%'
        AND tm.correct_answer NOT ILIKE '%заполн%'
    """)
    log.info("  %d text tasks (short answers only)", len(rows))
    n = _run_distractor_pass(rows, "text")
    log.info("Step 6 done: %d text distractors", n)
    return n


# ══════════════════════════════════════════════════════════════════════════════
# Stats
# ══════════════════════════════════════════════════════════════════════════════

def print_stats():
    with engine.connect() as conn:
        row = conn.execute(text(f"""
            SELECT
              COUNT(DISTINCT tm.id) as total,
              ROUND(COUNT(DISTINCT CASE WHEN tm.correct_answer != '' AND tm.correct_answer IS NOT NULL
                THEN tm.id END)::numeric / COUNT(DISTINCT tm.id) * 100, 1) as ans_pct,
              ROUND(COUNT(DISTINCT CASE WHEN tm.distractor_meta IS NOT NULL
                AND jsonb_array_length(tm.distractor_meta) > 0 THEN tm.id END)::numeric
                / COUNT(DISTINCT tm.id) * 100, 1) as dist_pct,
              ROUND(COUNT(DISTINCT CASE WHEN tm.skill_id IS NOT NULL THEN tm.id END)::numeric
                / COUNT(DISTINCT tm.id) * 100, 1) as skill_pct
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
            WHERE tb.class_level = {GRADE}
        """)).fetchone()
    log.info("G%d: %d задач | ответы=%s%% | дист=%s%% | навыки=%s%%",
             GRADE, row[0], row[1], row[2], row[3])


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    log.info("=" * 60)
    log.info("G8 Максимальная добивка")
    log.info("=" * 60)

    s1 = step1_skills()
    s2 = step2_ai_answers()
    s3 = step3_expression_gemini()
    s4 = step4_gemini_algebraic()
    s5 = step5_exact_number()
    s6 = step6_text_gemini()

    log.info("=" * 60)
    log.info("ИТОГО: навыки=%d | AI-ответы=%d | expr=%d | алг=%d | числа=%d | текст=%d",
             s1, s2, s3, s4, s5, s6)
    log.info("=" * 60)
    print_stats()


if __name__ == "__main__":
    main()
