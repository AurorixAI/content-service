"""
Step 2 — L3 Subtopic Prerequisites Graph
==========================================
Строит граф зависимостей на уровне L3 подтем (а не L4 навыков).

Один Gemini-вызов на весь класс: все L3 подтемы текущего класса + L3 подтемы
предыдущего класса (cross-grade пул). ~70 узлов максимум → высокое качество.

Диагностика использует L3→L3 граф для навигации (какие подтемы проверять).
Внутри каждой L3 подтемы — бинарный поиск по L4 навыкам.

Запуск:
  python3 -m src.pipeline.step2_prerequisites --class 5 --out data/curriculum/prerequisites_class5.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.deepseek_client import call_deepseek, get_deepseek_model, parse_json_response
from src.pipeline.curriculum_analyzer import SkillNode

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


# ── Prompt ────────────────────────────────────────────────────────────────────

def _build_prompt(
    class_level: int,
    current_l3: list,        # L3 nodes of current grade, grouped by L2
    prev_l3: list,           # L3 nodes of prev grade
    l2_map: dict,            # {l2_id: l2_name} for context
) -> str:
    """Single prompt for all L3→L3 prerequisites for a grade."""

    # Group current L3 by parent L2
    by_l2: dict[str, list] = {}
    for n in current_l3:
        by_l2.setdefault(n.parent_id, []).append(n)

    current_block_parts = []
    for l2_id, subtopics in by_l2.items():
        l2_name = l2_map.get(l2_id, l2_id)
        current_block_parts.append(f"  ТЕМА [{l2_id}] {l2_name}:")
        for n in subtopics:
            current_block_parts.append(f"    [{n.id}] {n.name_ru}")
    current_block = "\n".join(current_block_parts)

    prev_block = ""
    if prev_l3:
        # Group prev L3 by parent
        prev_by_l2: dict[str, list] = {}
        for n in prev_l3:
            prev_by_l2.setdefault(n.parent_id, []).append(n)
        prev_parts = [f"\nПОДТЕМЫ ПРЕДЫДУЩЕГО КЛАССА ({class_level - 1}) — только для cross-grade зависимостей:"]
        for l2_id, subtopics in prev_by_l2.items():
            prev_parts.append(f"  [{l2_id}]:")
            for n in subtopics:
                prev_parts.append(f"    [{n.id}] {n.name_ru}")
        prev_block = "\n".join(prev_parts)

    current_ids = [n.id for n in current_l3]

    return f"""Ты — старший методист математического образования (PhD, 15+ лет практики).
Задача: построить граф зависимостей между подтемами (L3) для адаптивной диагностики {class_level} класса.

<context>
ПОДТЕМЫ {class_level} КЛАССА (skill_id должен быть из этого списка):
{current_block}
{prev_block}
</context>

<task>
Найди все пары подтем (A → B), где подтема A НЕ МОЖЕТ быть нормально освоена без подтемы B.

  skill_id = подтема A (зависимая, из {class_level} класса ТОЛЬКО)
  prerequisite_id = подтема B (предпосылка, из {class_level} ИЛИ предыдущего класса)

КЛАССИФИКАЦИЯ dependency_type:

  "hard" — ТОЛЬКО если:
    1. Без освоения B студент физически не сможет освоить A
    2. Любой типичный студент провалит A без знания B
    3. Нет обходного пути вообще
    Пример: "Алгебраические дроби" → "Обыкновенные дроби" (hard: нельзя работать с алг. дробями без дробей)

  "soft" — B помогает, но A можно освоить через другой путь:
    Пример: "Системы уравнений" → "Рациональные числа" (soft: помогает, но не блокирует полностью)

  ⚠ НЕ добавляй ребро если:
    - Это просто "предыдущая тема по учебнику" без реальной блокировки
    - Зависимость транзитивная (A→C→B уже есть)
    - Создаётся цикл
    - skill_id не из текущего класса {class_level}

WEIGHT (0.0–1.0):
  1.0 = полная блокировка | 0.8–0.9 = сильная | 0.6–0.7 = умеренная | 0.3–0.5 = слабая

CRITICALITY (1–10):
  Насколько полезно знать эту зависимость для диагностики. 10 = незнание B точно объясняет провал в A.

is_cross_grade = true если prerequisite_id из предыдущего класса.

Текущие L3 IDs (skill_id только отсюда):
{json.dumps(current_ids, ensure_ascii=False)}
</task>

<thinking_instructions>
1. Для каждой подтемы A: какие подтемы B реально блокируют её освоение?
2. hard vs soft: можно ли хоть как-то освоить A без B? → если да → soft
3. Транзитивность: если A→C и C→B — не добавляй A→B
4. Циклы: проверь что нет A→B→C→A
5. Cross-grade: явно пометь is_cross_grade=true для связей с предыдущим классом
</thinking_instructions>

JSON ответ (без комментариев):
{{
  "prerequisites": [
    {{
      "skill_id": "G{class_level}_P04",
      "prerequisite_id": "G{class_level}_P02",
      "dependency_type": "hard",
      "weight": 0.9,
      "criticality": 9,
      "is_cross_grade": false,
      "relationship_description": "Конкретное объяснение почему B блокирует A."
    }}
  ]
}}
"""


# ── Data loading ───────────────────────────────────────────────────────────────

def _load_l3(class_level: int) -> tuple[list, dict]:
    """Returns (l3_nodes, l2_name_map) for class_level."""
    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, level, parent_id, name_ru, description,
                       class_level_start, class_level_end
                FROM knowledge_hierarchy
                WHERE class_level_start = :cl
                  AND level IN ('L2', 'L3')
                  AND is_active = TRUE
                ORDER BY level, sequence_order
            """),
            {"cl": class_level},
        ).fetchall()

    l2_map = {}
    l3_nodes = []
    for r in rows:
        node = SkillNode(
            id=r[0], level=r[1], parent_id=r[2] or "",
            name_ru=r[3], description=r[4] or "",
            class_level_start=r[5] or class_level,
            class_level_end=r[6] or class_level,
            current_importance=5, cognitive_type="",
            example_task="", assessed_ability="", difficulty_level="", formula="",
        )
        if node.level == "L2":
            l2_map[node.id] = node.name_ru
        else:
            l3_nodes.append(node)

    return l3_nodes, l2_map


# ── Main ──────────────────────────────────────────────────────────────────────

def run(class_level: int, out_path: str) -> None:
    log.info("Step 2: L3 Prerequisites for class %d", class_level)
    log.info("Output: %s", out_path)

    current_l3, l2_map = _load_l3(class_level)
    prev_l3 = []
    if class_level > 5:
        prev_l3, _ = _load_l3(class_level - 1)

    log.info(
        "Loaded: %d L3 subtopics (class %d), %d prev-grade L3 (class %d)",
        len(current_l3), class_level, len(prev_l3), class_level - 1,
    )

    prompt = _build_prompt(class_level, current_l3, prev_l3, l2_map)

    try:
        raw = call_deepseek(
            prompt,
            model=get_deepseek_model(),
            temperature=0.1,
            max_tokens=16384,
            json_mode=True,
            timeout=240,
            thinking_budget=4096,
        )
        data = parse_json_response(raw)
        edges = data.get("prerequisites", [])
        log.info("Gemini returned %d edges", len(edges))
    except Exception as exc:
        log.error("FAILED: %s", exc)
        edges = []

    # Validate: skill_id must be from current grade
    current_ids = {n.id for n in current_l3}
    valid_edges = []
    skipped = 0
    for e in edges:
        if e.get("skill_id") not in current_ids:
            log.warning("  SKIP invalid skill_id: %s", e.get("skill_id"))
            skipped += 1
            continue
        valid_edges.append(e)

    if skipped:
        log.warning("Skipped %d edges with invalid skill_id", skipped)

    output = {
        "class_level": class_level,
        "total_edges": len(valid_edges),
        "errors": [] if valid_edges else ["no edges generated"],
        "edges": valid_edges,
    }

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    log.info(
        "Done: %d valid edges (%d skipped). Saved to %s",
        len(valid_edges), skipped, out_path,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--class", dest="class_level", type=int, required=True)
    parser.add_argument("--out", type=str, required=True)
    args = parser.parse_args()
    run(args.class_level, args.out)
