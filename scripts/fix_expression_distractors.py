r"""
Перезаписывает дистракторы для expression задач G8 через Gemini Pro.
Заменяет SymPy-механику (sign_error / calculation_error) на реальные
педагогические ошибки учеников.
Заодно закрывает оставшиеся 14 задач (text + exact_number) без дистракторов.
"""
from __future__ import annotations
import json, logging, sys
sys.path.insert(0, "/app")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("fix_expr_dist")

from sqlalchemy import create_engine, text
from src.core.config import get_settings
from src.pipeline.distractors import generate_distractors
from src.pipeline.models import ExtractedTask

engine = create_engine(get_settings().database_url)

def _save(task_id, dmeta):
    with engine.begin() as conn:
        conn.execute(text("UPDATE tasks_master SET distractor_meta=cast(:d as jsonb) WHERE id=:id"),
                     {"d": json.dumps(dmeta, ensure_ascii=False), "id": task_id})

def run():
    # Все expression задачи G8 (перезаписываем SymPy + заполняем пустые)
    with engine.connect() as conn:
        expr_rows = conn.execute(text("""
            SELECT tm.id, tm.question_text, tm.correct_answer
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
            WHERE tb.class_level = 8 AND tm.answer_type = 'expression'
              AND tm.correct_answer IS NOT NULL AND tm.correct_answer != ''
            ORDER BY tm.id
        """)).fetchall()

        # Остатки: text и exact_number без дистракторов
        other_rows = conn.execute(text("""
            SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
            WHERE tb.class_level = 8
              AND tm.answer_type IN ('text', 'exact_number')
              AND (tm.distractor_meta IS NULL OR jsonb_array_length(tm.distractor_meta) = 0)
              AND tm.correct_answer IS NOT NULL AND tm.correct_answer != ''
            ORDER BY tm.id
        """)).fetchall()

    log.info("Expression задачи для переделки: %d", len(expr_rows))
    log.info("Остатки без дистракторов: %d", len(other_rows))

    filled = 0
    # Expression — перезаписываем всё через Gemini
    for i, (task_id, question, answer) in enumerate(expr_rows):
        et = ExtractedTask(temp_id=task_id, question_text=question or "",
                           answer_raw=answer, answer_type="expression")
        try:
            result = generate_distractors(et)
        except Exception as e:
            log.debug("  %s: %s", task_id, e); continue

        if result.distractor_meta:
            _save(task_id, result.distractor_meta)
            filled += 1
        if (i + 1) % 50 == 0:
            log.info("  expression: %d/%d заполнено=%d", i+1, len(expr_rows), filled)

    log.info("Expression готово: %d/%d", filled, len(expr_rows))

    # Остатки
    other_filled = 0
    for task_id, question, answer, atype in other_rows:
        et = ExtractedTask(temp_id=task_id, question_text=question or "",
                           answer_raw=answer, answer_type=atype)
        try:
            result = generate_distractors(et)
        except Exception as e:
            log.debug("  %s: %s", task_id, e); continue
        if result.distractor_meta:
            _save(task_id, result.distractor_meta)
            other_filled += 1

    log.info("Остатки готово: %d/%d", other_filled, len(other_rows))

    # Итог
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT
              COUNT(*) as total,
              ROUND(COUNT(CASE WHEN distractor_meta IS NOT NULL AND jsonb_array_length(distractor_meta) > 0
                THEN 1 END)::numeric / COUNT(*) * 100, 1) as dist_pct,
              COUNT(CASE WHEN dm->>'error_type' = 'ai_generated' THEN 1 END) as gemini_dist,
              COUNT(CASE WHEN dm->>'error_type' IN ('sign_error','calculation_error','formula_error','algebraic_variant')
                THEN 1 END) as sympy_dist
            FROM tasks_master tm
            LEFT JOIN LATERAL jsonb_array_elements(
              CASE WHEN jsonb_array_length(distractor_meta) > 0 THEN distractor_meta ELSE '[]'::jsonb END
            ) dm ON true
            WHERE id LIKE 'G8_%' AND answer_type = 'expression'
        """)).fetchone()
        log.info("G8 expression итог: %d задач | дист=%s%% | Gemini=%d | SymPy остаток=%d",
                 row[0], row[1], row[2] or 0, row[3] or 0)

if __name__ == "__main__":
    run()
