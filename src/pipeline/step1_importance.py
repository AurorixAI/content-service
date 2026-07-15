"""
Step 1 — L3 Subtopic Importance
================================
Для каждого L2-кластера вызывает Gemini — оценивает важность (importance 1-10)
каждой L3 подтемы и самого кластера.

L4 importance больше не генерируется — диагностика использует L3→L3 граф для
навигации, а внутри L3 проходит по L4 навыкам бинарным поиском.

Запуск:
  python3 -m src.pipeline.step1_importance --class 5 --out data/curriculum/importance_class5.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.deepseek_client import call_deepseek, get_deepseek_model, parse_json_response
from src.pipeline.curriculum_analyzer import SkillNode

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


# ── Prompt ────────────────────────────────────────────────────────────────────

def _build_prompt(cluster: SkillNode, l3_nodes: list) -> str:
    """Build importance prompt for one L2 cluster — rates L3 subtopics only."""
    subtopics_block = "\n".join(
        f"  [{n.id}] {n.name_ru}"
        + (f" — {n.description}" if n.description else "")
        for n in l3_nodes
    )

    node_ids = [cluster.id] + [n.id for n in l3_nodes]

    return f"""Ты — старший методист математического образования (PhD, 15+ лет практики).
Задача: оценить важность (importance) подтем для адаптивной диагностики.

<context>
ТЕМА (L2): [{cluster.id}] {cluster.name_ru}
  Классы: {cluster.class_level_start}–{cluster.class_level_end}

ПОДТЕМЫ (L3) — оценить каждую:
{subtopics_block}
</context>

<task>
Для каждого узла задай importance (1–10) и cognitive_type.

ШКАЛА IMPORTANCE:
  10 = абсолютный фундамент: без него студент не освоит 5+ других подтем
  8–9 = критическая подтема: блокирует 2–4 подтемы, нужна немедленная диагностика
  6–7 = важная: нужна для нескольких подтем, но есть обходные пути
  4–5 = умеренная: полезна, не является жёстким блокером
  1–3 = факультативная: можно пропустить без большой потери прогресса

  ⚠ ПРАВИЛО: не более 30% подтем в кластере с importance ≥ 8
  ⚠ ПРАВИЛО: importance(L2 кластер) = max importance его подтем

COGNITIVE_TYPE (одно слово):
  recall | apply | analyze | evaluate | create

Node IDs для ответа: {json.dumps(node_ids, ensure_ascii=False)}
</task>

<thinking_instructions>
Для каждой подтемы:
1. Сколько других подтем она разблокирует? → importance
2. Какой главный когнитивный процесс? → cognitive_type
3. Проверь 30% правило
</thinking_instructions>

JSON ответ (без комментариев):
{{
  "importances": [
    {{"node_id": "...", "importance": 8, "cognitive_type": "apply", "rationale": "1 предложение"}}
  ]
}}
"""


# ── Data loading ───────────────────────────────────────────────────────────────

def _load_tree(class_level: int) -> dict:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, level, parent_id, name_ru, description,
                       class_level_start, class_level_end
                FROM knowledge_hierarchy
                WHERE class_level_start = :cl
                  AND is_active = TRUE
                  AND level IN ('L2', 'L3')
                ORDER BY level, sequence_order
            """),
            {"cl": class_level},
        ).fetchall()

    nodes = [
        SkillNode(
            id=r[0], level=r[1], parent_id=r[2] or "",
            name_ru=r[3], description=r[4] or "",
            class_level_start=r[5] or class_level,
            class_level_end=r[6] or class_level,
            current_importance=5,
            cognitive_type="",
            example_task="",
            assessed_ability="",
            difficulty_level="",
            formula="",
        )
        for r in rows
    ]
    return {
        "l2": [n for n in nodes if n.level == "L2"],
        "l3": [n for n in nodes if n.level == "L3"],
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def run(class_level: int, out_path: str) -> None:
    log.info("Step 1: L3 Importance analysis for class %d", class_level)
    log.info("Output: %s", out_path)

    tree = _load_tree(class_level)
    log.info(
        "Loaded: %d L2 clusters, %d L3 subtopics",
        len(tree["l2"]), len(tree["l3"]),
    )

    results = []
    errors = []

    for cluster in tree["l2"]:
        l3_children = [n for n in tree["l3"] if n.parent_id == cluster.id]

        if not l3_children:
            log.warning("Cluster %s has no L3 subtopics, skip", cluster.id)
            continue

        log.info(
            "Cluster %s (%s): %d L3 subtopics ...",
            cluster.id, cluster.name_ru, len(l3_children),
        )

        prompt = _build_prompt(cluster, l3_children)

        try:
            raw = call_deepseek(
                prompt,
                model=get_deepseek_model(),
                temperature=0.1,
                max_tokens=4096,
                json_mode=True,
                timeout=120,
                thinking_budget=2048,
            )
            data = parse_json_response(raw)
            items = data.get("importances", [])
            log.info("  → %d importance records", len(items))
            results.append({
                "cluster_id": cluster.id,
                "cluster_name": cluster.name_ru,
                "subtopics": [x for x in items if x.get("node_id") != cluster.id],
                "cluster_importance": next(
                    (x.get("importance", 5) for x in items if x.get("node_id") == cluster.id), 5
                ),
            })
        except Exception as exc:
            log.error("  FAILED: %s", exc)
            errors.append({"cluster": cluster.id, "error": str(exc)})

    output = {
        "class_level": class_level,
        "clusters_ok": len(results),
        "clusters_error": len(errors),
        "errors": errors,
        "data": results,
    }

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    log.info(
        "Done: %d/%d clusters OK, %d errors. Saved to %s",
        len(results), len(tree["l2"]), len(errors), out_path,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--class", dest="class_level", type=int, required=True)
    parser.add_argument("--out", type=str, required=True)
    args = parser.parse_args()
    run(args.class_level, args.out)
