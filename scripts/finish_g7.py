r"""
Добивка G7 — максимальная заполненность.

Шаги:
  1. Исправить ответы для exact_number/expression задач (прямой расчёт)
  2. Запустить AIAnswerSolver для оставшихся text/set без ответов
  3. Сгенерировать дистракторы для всех задач с ответом но без дистракторов
  4. Автомаппинг skill_id для задач без навыка (поиск по toc_id)
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
log = logging.getLogger("finish_g7")

from sqlalchemy import create_engine, text
from src.core.config import get_settings

engine = create_engine(get_settings().database_url)


# ══════════════════════════════════════════════════════════════════════════════
# Шаг 1 — прямые исправления
# ══════════════════════════════════════════════════════════════════════════════

def step1_direct_fixes():
    log.info("=== Step 1: Direct answer fixes ===")
    fixes = [
        # (task_id, correct_answer, answer_type_override_or_None)
        ("G7_TB_39_8.1", "3a - 4b",  "expression"),   # "Покажите выражение 3a-4b"
        ("G7_TB_39_8.2", "23",        None),            # 6*3+1*5 = 18+5 = 23
        ("G7_TB_39_8.3", "16384",     None),            # 2^14
        ("G7_TB_39_8.4", "-225",      None),            # (-12-3)*(6*2+3)=-15*15
    ]
    updated = 0
    for task_id, answer, atype in fixes:
        with engine.begin() as conn:
            if atype:
                conn.execute(text("""
                    UPDATE tasks_master
                    SET correct_answer = :ans, answer_type = :atype
                    WHERE id = :id
                """), {"ans": answer, "atype": atype, "id": task_id})
            else:
                conn.execute(text("""
                    UPDATE tasks_master SET correct_answer = :ans WHERE id = :id
                """), {"ans": answer, "id": task_id})
        log.info("  Fixed %s → %s", task_id, answer)
        updated += 1
    log.info("Step 1 done: %d fixes", updated)
    return updated


# ══════════════════════════════════════════════════════════════════════════════
# Шаг 2 — AIAnswerSolver для оставшихся без ответов
# ══════════════════════════════════════════════════════════════════════════════

def step2_ai_answers():
    log.info("=== Step 2: AI answers for text/set tasks ===")
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT tm.id, tm.question_text, tm.answer_type
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
            WHERE tb.class_level = 7
              AND (tm.correct_answer = '' OR tm.correct_answer IS NULL)
              AND tm.answer_type IN ('text', 'set', 'exact_number')
            ORDER BY tm.answer_type, tm.id
        """)).fetchall()

    if not rows:
        log.info("  No tasks needing AI answers")
        return 0

    log.info("  %d tasks to solve with AI", len(rows))

    try:
        from src.pipeline.models import ExtractedTask
        try:
            from src.pipeline.enrichment import AIAnswerSolver as _Solver
            _method = "solve"
        except ImportError:
            from src.pipeline.enrichment import AIEnricher as _Solver
            _method = "enrich"
        solver = _Solver()
    except Exception as e:
        log.error("  Solver unavailable: %s", e)
        return 0

    solved = 0
    for task_id, question, atype in rows:
        et = ExtractedTask(
            temp_id=task_id,
            question_text=question or "",
            answer_type=atype or "text",
        )
        result = getattr(solver, _method)(et)
        if result.answer_raw and result.answer_raw.strip() not in ("", "—", "-", "?"):
            with engine.begin() as conn:
                conn.execute(text("""
                    UPDATE tasks_master SET correct_answer = :ans WHERE id = :id
                """), {"ans": result.answer_raw.strip(), "id": task_id})
            log.info("  %s [%s] → %s", task_id, atype, result.answer_raw.strip()[:50])
            solved += 1
        else:
            log.debug("  SKIP %s — no answer from AI", task_id)

    log.info("Step 2 done: %d solved by AI", solved)
    return solved


# ══════════════════════════════════════════════════════════════════════════════
# Шаг 3 — дистракторы для задач с ответом
# ══════════════════════════════════════════════════════════════════════════════

def step3_distractors():
    log.info("=== Step 3: Distractor generation ===")
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
            WHERE tb.class_level = 7
              AND tm.correct_answer IS NOT NULL
              AND tm.correct_answer NOT IN ('', '-', '—', '?')
              AND (tm.distractor_meta IS NULL OR tm.distractor_meta::text IN ('null', '[]'))
            ORDER BY tm.answer_type, tm.id
        """)).fetchall()

    if not rows:
        log.info("  No tasks needing distractors")
        return 0

    log.info("  %d tasks need distractors", len(rows))

    try:
        from src.pipeline.distractors import generate_distractors
        from src.pipeline.models import ExtractedTask
    except Exception as e:
        log.error("  Distractor module unavailable: %s", e)
        return 0

    filled = 0
    for task_id, question, answer, atype in rows:
        if not question or not answer:
            continue
        et = ExtractedTask(
            temp_id=task_id,
            question_text=question,
            answer_raw=answer,
            answer_type=atype or "exact_number",
        )
        try:
            result = generate_distractors(et)
        except Exception as e:
            log.debug("  Distractor error %s: %s", task_id, e)
            continue

        if not result.distractor_meta:
            log.debug("  No distractors for %s (type=%s)", task_id, atype)
            continue

        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE tasks_master
                SET distractor_meta = cast(:dmeta as jsonb)
                WHERE id = :id
            """), {
                "dmeta": json.dumps(result.distractor_meta, ensure_ascii=False),
                "id": task_id,
            })
        log.info("  %s [%s] → %d distractors", task_id, atype, len(result.distractor_meta))
        filled += 1

    log.info("Step 3 done: %d filled", filled)
    return filled


# ══════════════════════════════════════════════════════════════════════════════
# Шаг 4 — автомаппинг skill_id по toc_id
# ══════════════════════════════════════════════════════════════════════════════

def step4_skill_mapping():
    """
    SkeletonTextbookMapper на задачах без skill_id.
    Принцип: conf >= 0.70 → skill_id, иначе NULL (toc_id достаточно).
    """
    log.info("=== Step 4: Skill mapping via SkeletonTextbookMapper ===")
    MIN_CONF = 0.70

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT tm.id, tm.question_text, tm.question_latex,
                   tm.correct_answer, tm.answer_type, tm.difficulty,
                   toc.number, toc.title
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            WHERE tm.id LIKE 'G7_%' AND tm.skill_id IS NULL
            ORDER BY tm.id
        """)).fetchall()

    if not rows:
        log.info("  Нет задач без skill_id")
        return 0

    log.info("  %d задач без skill_id → SkeletonTextbookMapper (conf >= %.2f)", len(rows), MIN_CONF)

    from src.pipeline.classification import SkeletonTextbookMapper
    from src.pipeline.models import ExtractedTask

    mapper = SkeletonTextbookMapper()
    mapper.load_skills_from_db(get_settings().database_url, class_level=7)

    assigned = kept_null = 0
    rows_list = list(rows)  # for len()

    if not rows_list:
        log.info("  No unmapped tasks")
        return 0

    for i, (tid, question, latex, answer, atype, diff, para_num, para_title) in enumerate(rows_list):
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

    log.info("Step 4 done: %d assigned | %d kept NULL (toc_id достаточно)", assigned, kept_null)
    return assigned


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    log.info("=" * 60)
    log.info("G7 Максимальная добивка")
    log.info("=" * 60)

    s1 = step1_direct_fixes()
    s2 = step2_ai_answers()
    s3 = step3_distractors()
    s4 = step4_skill_mapping()

    log.info("=" * 60)
    log.info("ИТОГО: +%d fixes | +%d AI answers | +%d distractors | +%d skills", s1, s2, s3, s4)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
