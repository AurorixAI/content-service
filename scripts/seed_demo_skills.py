#!/usr/bin/env python3
"""
Демо-сид графа знаний. **Не содержание, а строительные леса.**

`tasks_master` требует `skill_id` на L4 (триггер `trg_tasks_master_skill_l4`),
а маппинг задач на навыки делает `mapper` по реальному графу из
`knowledge_hierarchy` — ~1 374 узла, которые живут на staging и локально
недоступны. Без графа промоушен корректно упирается в «нет skill_id», и
последний шаг конвейера на локальной машине не показать.

Этот скрипт заводит минимальную цепочку L1→L2→L3→L4, чтобы прогнать промоушен
целиком. Все узлы помечены `origin='demo_seed'` — по этой метке их видно
и можно снести одной командой (`--drop`). В прод такой сид не едет: там граф
настоящий, и `ON CONFLICT DO NOTHING` не даст затереть его узлы.

    python3 scripts/seed_demo_skills.py            # завести
    python3 scripts/seed_demo_skills.py --drop     # снести
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from src.pipeline.db_writer import _engine  # noqa: E402

DEMO_SKILL_ID = "DEMO_S01_01_01"

_NODES = [
    ("DEMO_SEC01", "L1", None, "Демо-раздел"),
    ("DEMO_T01", "L2", "DEMO_SEC01", "Демо-тема"),
    ("DEMO_S01_01", "L3", "DEMO_T01", "Демо-подтема"),
    (DEMO_SKILL_ID, "L4", "DEMO_S01_01", "Демо-навык"),
]


def seed() -> int:
    engine = _engine()
    with engine.begin() as conn:
        for node_id, level, parent, name in _NODES:
            conn.execute(
                text("""
                    INSERT INTO knowledge_hierarchy
                        (id, level, parent_id, name_ru, origin, is_active)
                    VALUES (:id, :level, :parent, :name, 'demo_seed', TRUE)
                    ON CONFLICT (id) DO NOTHING
                """),
                {"id": node_id, "level": level, "parent": parent, "name": name},
            )
    print(f"Заведено узлов: {len(_NODES)}. Навык для промоушена: {DEMO_SKILL_ID}")
    return 0


def drop() -> int:
    engine = _engine()
    with engine.begin() as conn:
        n = conn.execute(
            text("""
                DELETE FROM knowledge_hierarchy
                WHERE origin = 'demo_seed'
                  AND id NOT IN (SELECT skill_id FROM tasks_master WHERE skill_id IS NOT NULL)
            """)
        ).rowcount
    print(f"Снесено демо-узлов: {n}")
    print("(узлы, на которые уже ссылаются задачи, не трогаются)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Демо-сид графа знаний")
    ap.add_argument("--drop", action="store_true", help="снести демо-узлы")
    args = ap.parse_args()
    if not os.environ.get("DATABASE_URL"):
        print("DATABASE_URL не задан", file=sys.stderr)
        return 2
    return drop() if args.drop else seed()


if __name__ == "__main__":
    raise SystemExit(main())
