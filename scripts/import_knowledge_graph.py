#!/usr/bin/env python3
"""Загрузить граф знаний (`knowledge_hierarchy`) из выгрузки и проверить его.

Зачем отдельный скрипт: без настоящего графа классификатор привязывает задачи
к тому, что найдёт, а промоушен упирается в заслон (см. B21). На первом живом
прогоне книги все 687 задач сели на единственный демо-навык `DEMO_S01_01_01`,
потому что локально в графе было 4 узла-заглушки.

Скрипт принимает JSON или CSV, проверяет целостность **до** записи и не трогает
БД, пока не убедится, что граф связный:

* уровни только L1–L4;
* у каждого узла ниже L1 есть существующий родитель;
* уровень родителя ровно на единицу выше;
* идентификаторы уникальны.

`--dry-run` по умолчанию — правило §0.7: сначала показать, что будет сделано.

    python3 scripts/import_knowledge_graph.py --file graph.json          # проверка
    python3 scripts/import_knowledge_graph.py --file graph.json --apply  # запись
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys
from typing import Any, Dict, List

# Работает и в контейнере (/app), и из корня репозитория на хосте.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from src.pipeline.db_writer import _engine  # noqa: E402

_LEVELS = ("L1", "L2", "L3", "L4")
_LEVEL_RANK = {lvl: i for i, lvl in enumerate(_LEVELS)}

#: Демо-узлы из `seed_demo_skills.py`. Настоящий граф их вытесняет.
_DEMO_PREFIX = "DEMO_"

_UPSERT = """
INSERT INTO knowledge_hierarchy (
    id, level, parent_id, name_ru, description,
    class_level_start, class_level_end, sequence_order, importance, is_active
) VALUES (
    :id, :level, :parent_id, :name_ru, :description,
    :class_level_start, :class_level_end, :sequence_order, :importance, TRUE
)
ON CONFLICT (id) DO UPDATE SET
    level             = EXCLUDED.level,
    parent_id         = EXCLUDED.parent_id,
    name_ru           = EXCLUDED.name_ru,
    description       = EXCLUDED.description,
    class_level_start = EXCLUDED.class_level_start,
    class_level_end   = EXCLUDED.class_level_end,
    sequence_order    = EXCLUDED.sequence_order,
    importance        = EXCLUDED.importance,
    is_active         = TRUE
"""


def load_rows(path: pathlib.Path) -> List[Dict[str, Any]]:
    """Прочитать выгрузку. JSON (список объектов) или CSV с заголовком."""
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("knowledge_hierarchy") or payload.get("rows") or []
    return list(payload)


def normalise(row: Dict[str, Any]) -> Dict[str, Any]:
    def _int(value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    parent = str(row.get("parent_id") or "").strip()
    return {
        "id": str(row.get("id") or "").strip(),
        "level": str(row.get("level") or "").strip().upper(),
        "parent_id": parent or None,
        "name_ru": str(row.get("name_ru") or row.get("name") or "").strip(),
        "description": (str(row.get("description") or "").strip() or None),
        "class_level_start": _int(row.get("class_level_start"), 5),
        "class_level_end": _int(row.get("class_level_end"), 11),
        "sequence_order": _int(row.get("sequence_order"), 0),
        "importance": min(10, max(1, _int(row.get("importance"), 5))),
    }


def validate(rows: List[Dict[str, Any]]) -> List[str]:
    """Проверить граф целиком. Возвращает список проблем (пусто — граф годен)."""
    problems: List[str] = []
    by_id: Dict[str, Dict[str, Any]] = {}

    for r in rows:
        if not r["id"]:
            problems.append("узел без id")
            continue
        if r["id"] in by_id:
            problems.append(f"дубль id: {r['id']}")
        by_id[r["id"]] = r
        if r["level"] not in _LEVELS:
            problems.append(f"{r['id']}: недопустимый уровень {r['level']!r}")
        if not r["name_ru"]:
            problems.append(f"{r['id']}: пустое имя")

    for r in by_id.values():
        if r["level"] == "L1":
            if r["parent_id"]:
                problems.append(f"{r['id']}: у корня L1 не должно быть родителя")
            continue
        if not r["parent_id"]:
            problems.append(f"{r['id']}: нет родителя при уровне {r['level']}")
            continue
        parent = by_id.get(r["parent_id"])
        if parent is None:
            problems.append(f"{r['id']}: родитель {r['parent_id']} отсутствует в выгрузке")
            continue
        if r["level"] in _LEVEL_RANK and parent["level"] in _LEVEL_RANK:
            if _LEVEL_RANK[r["level"]] - _LEVEL_RANK[parent["level"]] != 1:
                problems.append(
                    f"{r['id']} ({r['level']}): родитель {parent['id']} уровня "
                    f"{parent['level']} — разрыв иерархии"
                )
    return problems


def summarise(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {lvl: 0 for lvl in _LEVELS}
    for r in rows:
        if r["level"] in out:
            out[r["level"]] += 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", required=True, help="JSON или CSV с узлами графа")
    ap.add_argument("--apply", action="store_true", help="записать в БД (иначе только проверка)")
    ap.add_argument(
        "--drop-demo", action="store_true",
        help="удалить демо-узлы DEMO_* после импорта (на них не должно быть задач)",
    )
    args = ap.parse_args()

    path = pathlib.Path(args.file)
    if not path.is_file():
        print(f"файл не найден: {path}", file=sys.stderr)
        return 1

    rows = [normalise(r) for r in load_rows(path)]
    if not rows:
        print("выгрузка пуста", file=sys.stderr)
        return 1

    print(f"узлов в выгрузке: {len(rows)}")
    for lvl, n in summarise(rows).items():
        print(f"  {lvl}: {n}")

    problems = validate(rows)
    if problems:
        print(f"\nГРАФ НЕ ГОДЕН — проблем: {len(problems)}", file=sys.stderr)
        for p in problems[:20]:
            print(f"  · {p}", file=sys.stderr)
        if len(problems) > 20:
            print(f"  … и ещё {len(problems) - 20}", file=sys.stderr)
        return 2
    print("\nпроверка целостности пройдена: уровни, родители и иерархия связны")

    if not args.apply:
        print("\n--apply не задан: в БД ничего не записано")
        return 0

    # Порядок важен: родитель должен существовать раньше ребёнка (FK).
    rows.sort(key=lambda r: _LEVEL_RANK.get(r["level"], 9))
    engine = _engine()
    with engine.begin() as conn:
        for r in rows:
            conn.execute(text(_UPSERT), r)
        written = len(rows)

        demo_removed = 0
        if args.drop_demo:
            used = conn.execute(text(
                "SELECT count(*) FROM tasks_master WHERE skill_id LIKE :p"
            ), {"p": f"{_DEMO_PREFIX}%"}).scalar() or 0
            if used:
                print(f"\nдемо-узлы НЕ удалены: на них ссылаются {used} задач в tasks_master",
                      file=sys.stderr)
            else:
                res = conn.execute(text("DELETE FROM knowledge_hierarchy WHERE id LIKE :p"),
                                   {"p": f"{_DEMO_PREFIX}%"})
                demo_removed = res.rowcount or 0

    print(f"\nзаписано узлов: {written}")
    if args.drop_demo and demo_removed:
        print(f"удалено демо-узлов: {demo_removed}")

    with engine.connect() as conn:
        total = conn.execute(text("SELECT count(*) FROM knowledge_hierarchy")).scalar()
        l4 = conn.execute(text("SELECT count(*) FROM knowledge_hierarchy WHERE level='L4'")).scalar()
    print(f"в БД теперь: {total} узлов, из них L4 (на них ссылаются задачи): {l4}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
