r"""
Финальный маппинг навыков G7 + G8.

Критерий toc-пропаганды: skill_id есть, но tags.mapping_confidence нет
(оригинальный SkeletonTextbookMapper всегда пишет confidence в tags).

1. Сброс таких задач в NULL
2. SkeletonTextbookMapper: conf >= 0.70 → skill_id + tags, иначе NULL
"""
from __future__ import annotations

import json
import logging
import sys
import time

sys.path.insert(0, "/app")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("fix_skills")

from sqlalchemy import create_engine, text
from src.core.config import get_settings
from src.pipeline.classification import SkeletonTextbookMapper
from src.pipeline.models import ExtractedTask

engine = create_engine(get_settings().database_url)
DB_URL = get_settings().database_url
MIN_CONF = 0.70
GRADES = [7, 8]


def reset_toc_propagation(grade: int) -> int:
    """Сброс задач без mapping_confidence в tags — признак toc-пропаганды."""
    prefix = f"G{grade}_%"
    with engine.begin() as conn:
        result = conn.execute(text("""
            UPDATE tasks_master
            SET skill_id = NULL
            WHERE id LIKE :prefix
              AND skill_id IS NOT NULL
              AND (tags IS NULL OR tags->>'mapping_confidence' IS NULL)
        """), {"prefix": prefix})
        n = result.rowcount
    log.info("G%d: сброшено в NULL %d задач (нет mapping_confidence в tags)", grade, n)
    return n


def map_nulls(grade: int) -> tuple[int, int]:
    prefix = f"G{grade}_%"
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT tm.id, tm.question_text, tm.question_latex,
                   tm.correct_answer, tm.answer_type, tm.difficulty,
                   toc.number, toc.title, tm.tags
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            WHERE tm.id LIKE :prefix AND tm.skill_id IS NULL
            ORDER BY tm.id
        """), {"prefix": prefix}).fetchall()

    if not rows:
        log.info("G%d: нет задач с NULL skill_id", grade)
        return 0, 0

    log.info("G%d: %d задач → SkeletonTextbookMapper (conf >= %.2f)", grade, len(rows), MIN_CONF)

    mapper = SkeletonTextbookMapper()
    mapper.load_skills_from_db(DB_URL, class_level=grade)

    assigned = kept_null = 0
    for i, (tid, question, latex, answer, atype, diff, para_num, para_title, tags_raw) in enumerate(rows):
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
            log.debug("  %s: %s", tid, e)
            kept_null += 1
            continue

        conf = getattr(et, "mapping_confidence", 0.0) or 0.0
        if et.skill_id and conf >= MIN_CONF:
            tags = dict(tags_raw or {})
            if isinstance(tags, str):
                tags = json.loads(tags) if tags else {}
            tags["mapping_confidence"] = round(conf, 3)
            if et.tags.get("mapping_l3"):
                tags["mapping_l3"] = et.tags["mapping_l3"]
            if et.tags.get("mapping_reasoning"):
                tags["mapping_reasoning"] = et.tags["mapping_reasoning"]

            with engine.begin() as conn:
                conn.execute(text("""
                    UPDATE tasks_master SET skill_id=:s, tags=cast(:t as jsonb) WHERE id=:id
                """), {"s": et.skill_id, "t": json.dumps(tags, ensure_ascii=False), "id": tid})
            log.info("  ✓ %s → %s (conf=%.2f)", tid, et.skill_id, conf)
            assigned += 1
        else:
            kept_null += 1

        if (i + 1) % 20 == 0:
            log.info("  [G%d] %d/%d assigned=%d null=%d", grade, i + 1, len(rows), assigned, kept_null)
        time.sleep(0.05)

    log.info("G%d: assigned=%d | kept NULL=%d", grade, assigned, kept_null)
    return assigned, kept_null


def stats(grade: int):
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT COUNT(*) total,
                   COUNT(skill_id) with_skill,
                   COUNT(*) - COUNT(skill_id) null_skill,
                   COUNT(*) FILTER (WHERE skill_id IS NOT NULL AND tags->>'mapping_confidence' IS NULL) bad_skill
            FROM tasks_master WHERE id LIKE :p
        """), {"p": f"G{grade}_%"}).fetchone()
    log.info("G%d итог: %d задач | %d skill_id | %d только toc_id | %d skill без confidence",
             grade, row[0], row[1], row[2], row[3])


def main():
    log.info("=" * 55)
    log.info("Финальный маппинг G7+G8 (критерий: нет mapping_confidence)")
    log.info("=" * 55)

    for grade in GRADES:
        reset_toc_propagation(grade)
        map_nulls(grade)
        stats(grade)

    log.info("=" * 55)
    log.info("Готово")
    log.info("=" * 55)


if __name__ == "__main__":
    main()
