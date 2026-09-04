#!/usr/bin/env python3
"""Привести `task_id` в `tasks_staging` к каноническому формату.

Нужен для прогонов, отснятых до `src/pipeline/task_ids.py`: там идентификатор
брался из рабочего `temp_id` (`TEMP_6_032`), который не говорит, что это за
задача, и совпадает у разных книг. Канонический вид — `{prefix}_{параграф}_{номер}`,
как в продовой базе.

Трогает только строки, ещё не промоутнутые: у промоутнутой задачи id уже стал
ключом в `tasks_master` и `textbook_tasks`, менять его здесь нельзя.

    python3 scripts/reformat_task_ids.py --run-id <id>            # показать
    python3 scripts/reformat_task_ids.py --run-id <id> --apply    # записать
"""
from __future__ import annotations

import argparse
import collections
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from src.pipeline.db_writer import _engine  # noqa: E402
from src.pipeline.exercise_ranges.registry import task_id_prefix  # noqa: E402
from src.pipeline.task_ids import build_task_id  # noqa: E402

_SELECT = """
SELECT staging_id, task_id, textbook_id, class_level,
       paragraph_number, exercise_number
FROM tasks_staging
WHERE promoted_at IS NULL
  AND (:run_id IS NULL OR run_id = :run_id)
ORDER BY staging_id
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    engine = _engine()
    with engine.connect() as conn:
        rows = conn.execute(text(_SELECT), {"run_id": args.run_id}).mappings().all()

    if not rows:
        print("нечего переименовывать")
        return 0

    planned: list[tuple[int, str, str]] = []
    unchanged = skipped = 0
    seen: dict[tuple[str, str], int] = {}
    for r in rows:
        prefix = task_id_prefix(str(r["textbook_id"]), r["class_level"] or 0)
        new_id = build_task_id(prefix, r["paragraph_number"], r["exercise_number"])
        if not new_id:
            skipped += 1
            continue
        if new_id == r["task_id"]:
            unchanged += 1
            continue
        key = (str(r["textbook_id"]), new_id)
        seen[key] = seen.get(key, 0) + 1
        planned.append((r["staging_id"], r["task_id"], new_id))

    collisions = {k: n for k, n in seen.items() if n > 1}
    print(f"строк рассмотрено:   {len(rows)}")
    print(f"уже в формате:       {unchanged}")
    print(f"нечем адресовать:    {skipped}  (нет ни параграфа, ни номера)")
    print(f"к переименованию:    {len(planned)}")
    print(f"коллизий нового id:  {len(collisions)}")
    for (book, tid), n in list(collisions.items())[:10]:
        print(f"    {tid} × {n} в книге {book}")
    for sid, old, new in planned[:8]:
        print(f"    {old}  →  {new}")
    if len(planned) > 8:
        print(f"    … ещё {len(planned) - 8}")

    if collisions:
        print("\nпереименование остановлено: новый формат схлопнул бы разные задачи")
        return 2
    if not args.apply:
        print("\n--apply не задан: в БД ничего не записано")
        return 0

    with engine.begin() as conn:
        for sid, _old, new in planned:
            conn.execute(
                text("UPDATE tasks_staging SET task_id = :tid, updated_at = NOW() "
                     "WHERE staging_id = :sid"),
                {"tid": new, "sid": sid},
            )
    print(f"\nпереименовано: {len(planned)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
