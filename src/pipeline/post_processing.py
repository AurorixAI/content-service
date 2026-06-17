"""
Post-processing pipeline: запускается автоматически после каждого джоба оцифровки.

Шаги:
1. generate_missing_skills      — генерирует задачи для навыков без ни одной задачи
2. generate_missing_difficulties — заполняет A/B/C для навыков где не хватает уровней
3. fill_missing_distractors     — дистракторы для задач у которых answer_options пустой

Все шаги идемпотентны (ON CONFLICT DO NOTHING / пропуск если уже есть).

solution_steps и hints намеренно не генерируются в пайплайне — статика из БД
хуже real-time AI-тьютора, который объясняет конкретную ошибку ученика.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.pipeline.distractors import generate_distractors
from src.pipeline.models import ExtractedTask

log = logging.getLogger(__name__)

IRT_DIFF = {"A": -1.0, "B": 0.5, "C": 1.5}

DIFF_LABELS = {
    "A": "лёгкая (одно простое действие, очевидный ответ)",
    "B": "средняя (2-3 действия, требует понимания темы)",
    "C": "сложная (многошаговая, нестандартная, составная задача)",
}

PROMPT_TASKS = """\
Ты — учитель математики {grade} класса. Создай ровно {n} задач уровня {diff_label} по теме:
«{skill_name}»

Уровень: {diff_desc}

Правила:
- На русском языке, реалистичные числа для {grade} класса
- Ответ — одно число или краткое выражение
- Каждая задача уникальна

Формат JSON (только массив):
[
  {{
    "question": "Текст задачи...",
    "answer": "42"
  }}
]
"""


def _call_gemini(prompt: str) -> str:
    from src.pipeline.gemini_client import call_gemini, get_flash_model
    return call_gemini(
        prompt, model=get_flash_model(),
        temperature=0.7, max_tokens=4096,
        thinking_budget=0, json_mode=False,
    )


def _parse_tasks(raw: str) -> list[dict]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    s, e = raw.find("["), raw.rfind("]")
    if s == -1 or e == -1:
        return []
    try:
        return json.loads(raw[s:e + 1])
    except Exception:
        return []


def _generate_tasks(skill_name: str, diff: str, grade: int, n: int = 3) -> list[dict]:
    diff_label = {"A": "A (лёгкий)", "B": "B (средний)", "C": "C (сложный)"}[diff]
    prompt = PROMPT_TASKS.format(
        grade=grade, n=n, diff=diff, diff_label=diff_label,
        diff_desc=DIFF_LABELS[diff], skill_name=skill_name,
    )
    for attempt in range(3):
        try:
            raw = _call_gemini(prompt)
            tasks = _parse_tasks(raw)
            if tasks:
                return tasks
        except Exception as exc:
            log.warning("Attempt %d failed for '%s' %s: %s", attempt + 1, skill_name, diff, exc)
    return []


def _make_distractors(task_id: str, question: str, answer: str, answer_type: str = "exact_number") -> tuple[list, list]:
    et = ExtractedTask(temp_id=task_id, question_text=question, answer_raw=answer, answer_type=answer_type)
    generate_distractors(et)
    return et.distractors or [], et.distractor_meta or []


def _write_task(conn, task_id: str, skill_id: str, diff: str, t: dict) -> bool:
    question = str(t.get("question", "")).strip()
    answer = str(t.get("answer", "")).strip()
    if not question or not answer:
        return False

    distractors, distractor_meta = _make_distractors(task_id, question, answer)
    answer_options = [answer] + distractors

    try:
        conn.execute(text("""
            INSERT INTO tasks_master
              (id, skill_id, question_text, answer_type, correct_answer,
               difficulty, irt_discrimination, irt_difficulty, irt_guessing,
               source_type, verification_status, cognitive_load,
               answer_options, distractor_meta)
            VALUES
              (:id, :skill_id, :question, 'exact_number', :answer,
               :diff, 1.0, :irt_diff, 0.0,
               'ai_generated', 'pending', 'apply',
               cast(:options as jsonb), cast(:dmeta as jsonb))
            ON CONFLICT (id) DO NOTHING
        """), {
            "id": task_id, "skill_id": skill_id, "question": question,
            "answer": answer, "diff": diff, "irt_diff": IRT_DIFF[diff],
            "options": json.dumps(answer_options, ensure_ascii=False),
            "dmeta": json.dumps(distractor_meta, ensure_ascii=False),
        })
        return True
    except Exception as exc:
        log.error("Write error %s: %s", task_id, exc)
        return False


# ── Step 1: навыки без единой задачи ────────────────────────────────────────

def generate_missing_skills(engine: Engine, class_level: int) -> int:
    """Генерирует 10 задач (A/B/C) для навыков без ни одной задачи."""
    grade_prefix = f"G{class_level}_"
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT kh.id, kh.name_ru FROM knowledge_hierarchy kh
            WHERE kh.level='L4' AND kh.id LIKE :prefix
              AND NOT EXISTS (SELECT 1 FROM tasks_master tm WHERE tm.skill_id = kh.id)
            ORDER BY kh.id
        """), {"prefix": f"{grade_prefix}%"}).fetchall()

    if not rows:
        log.info("No uncovered skills for G%d", class_level)
        return 0

    log.info("Uncovered skills: %d", len(rows))
    total = 0
    with engine.begin() as conn:
        for skill_id, skill_name in rows:
            # 4A + 3B + 3C = 10 задач
            for diff, n in [("A", 4), ("B", 3), ("C", 3)]:
                tasks = _generate_tasks(skill_name, diff, class_level, n)
                for i, t in enumerate(tasks):
                    if _write_task(conn, f"GEN_{skill_id}_{diff}_{i+1:02d}", skill_id, diff, t):
                        total += 1
            log.info("  %s — done", skill_id)
    return total


# ── Step 2: навыки без какого-либо уровня A/B/C ─────────────────────────────

def generate_missing_difficulties(engine: Engine, class_level: int) -> int:
    """Добавляет 3 задачи для каждого отсутствующего уровня A/B/C."""
    grade_prefix = f"G{class_level}_"
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT kh.id, kh.name_ru,
                   COUNT(CASE WHEN tm.difficulty='A' THEN 1 END) AS cnt_a,
                   COUNT(CASE WHEN tm.difficulty='B' THEN 1 END) AS cnt_b,
                   COUNT(CASE WHEN tm.difficulty='C' THEN 1 END) AS cnt_c
            FROM knowledge_hierarchy kh
            LEFT JOIN tasks_master tm ON tm.skill_id = kh.id
            WHERE kh.level='L4' AND kh.id LIKE :prefix
            GROUP BY kh.id, kh.name_ru
            HAVING COUNT(CASE WHEN tm.difficulty='A' THEN 1 END)=0
                OR COUNT(CASE WHEN tm.difficulty='B' THEN 1 END)=0
                OR COUNT(CASE WHEN tm.difficulty='C' THEN 1 END)=0
            ORDER BY kh.id
        """), {"prefix": f"{grade_prefix}%"}).fetchall()

    if not rows:
        log.info("All skills have A/B/C for G%d", class_level)
        return 0

    log.info("Skills missing difficulty levels: %d", len(rows))
    total = 0
    with engine.begin() as conn:
        for skill_id, skill_name, cnt_a, cnt_b, cnt_c in rows:
            missing = [d for d, cnt in [("A", cnt_a), ("B", cnt_b), ("C", cnt_c)] if cnt == 0]
            for diff in missing:
                tasks = _generate_tasks(skill_name, diff, class_level, n=3)
                for i, t in enumerate(tasks):
                    if _write_task(conn, f"DIFF_{skill_id}_{diff}_{i+1:02d}", skill_id, diff, t):
                        total += 1
            log.info("  %s — filled: %s", skill_id, missing)
    return total


# ── Step 3: задачи без дистракторов ─────────────────────────────────────────

def fill_missing_distractors(engine: Engine, class_level: int) -> int:
    """Дополняет distractor_meta для задач без дистракторов.

    - ai_generated: заполняет answer_options + distractor_meta
    - textbook: только distractor_meta (MC собирается в UI из correct_answer + dmeta)
    """
    grade_prefix = f"G{class_level}_"
    with engine.connect() as conn:
        ai_rows = conn.execute(text("""
            SELECT id, question_text, correct_answer, answer_type
            FROM tasks_master
            WHERE source_type='ai_generated'
              AND skill_id LIKE :prefix
              AND (answer_options IS NULL OR answer_options='[]'::jsonb)
            ORDER BY id
        """), {"prefix": f"{grade_prefix}%"}).fetchall()

        tb_rows = conn.execute(text("""
            SELECT id, question_text, correct_answer, answer_type
            FROM tasks_master
            WHERE source_type='textbook'
              AND id LIKE :prefix
              AND (
                distractor_meta IS NULL
                OR distractor_meta::text IN ('null', '[]')
              )
            ORDER BY id
        """), {"prefix": f"{grade_prefix}%"}).fetchall()

    if not ai_rows and not tb_rows:
        return 0

    log.info(
        "Tasks without distractors: ai=%d textbook=%d",
        len(ai_rows), len(tb_rows),
    )
    updated = 0

    def _update(task_id, question, answer, atype, fill_options: bool):
        nonlocal updated
        if not answer or not question or str(answer).strip() in ("—", "-", ""):
            return
        distractors, distractor_meta = _make_distractors(task_id, question, answer, atype)
        if not distractor_meta:
            return
        params = {
            "id": task_id,
            "dmeta": json.dumps(distractor_meta, ensure_ascii=False),
        }
        if fill_options and distractors:
            params["options"] = json.dumps([answer] + distractors, ensure_ascii=False)
            sql = """
                UPDATE tasks_master
                SET answer_options  = cast(:options as jsonb),
                    distractor_meta = cast(:dmeta as jsonb)
                WHERE id = :id
            """
        else:
            sql = """
                UPDATE tasks_master
                SET distractor_meta = cast(:dmeta as jsonb)
                WHERE id = :id
            """
        with engine.begin() as conn:
            conn.execute(text(sql), params)
        updated += 1
        if updated % 100 == 0:
            log.info("  distractors filled: %d", updated)

    for row in ai_rows:
        _update(*row, fill_options=True)
    for row in tb_rows:
        _update(*row, fill_options=False)

    return updated


# ── Entry point ──────────────────────────────────────────────────────────────

def run_post_processing(db_url: str, class_level: int) -> dict:
    """
    Запускает три шага пост-обработки для указанного класса.
    Вызывается из worker/tasks.py после завершения джоба.
    """
    engine = create_engine(db_url)
    log.info("=== Post-processing G%d ===", class_level)

    s1 = generate_missing_skills(engine, class_level)
    log.info("Step 1 (missing skills): +%d tasks", s1)

    s2 = generate_missing_difficulties(engine, class_level)
    log.info("Step 2 (missing A/B/C): +%d tasks", s2)

    s3 = fill_missing_distractors(engine, class_level)
    log.info("Step 3 (fill distractors): %d updated", s3)

    log.info(
        "=== Post-processing done: +%d new, %d distractors ===",
        s1 + s2, s3,
    )
    return {"new_tasks": s1 + s2, "distractors_filled": s3}
