#!/usr/bin/env python3
"""
Промоушен staging → tasks_master (инвариант И3).

Единственный путь, которым задача попадает в банк. Конвейер сюда не пишет.

    python3 scripts/promote.py --run <run_id>              # отчёт, ничего не пишет
    python3 scripts/promote.py --run <run_id> --apply      # перенести
    python3 scripts/promote.py --textbook <uuid> --apply

`--dry-run` — режим по умолчанию и это не формальность: правило §0.7 требует
сначала показать, что будет сделано. Запись — только явным `--apply`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.pipeline.staging import promote  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Промоушен tasks_staging → tasks_master")
    ap.add_argument("--run", help="run_id прогона конвейера")
    ap.add_argument("--textbook", help="textbook_id (UUID)")
    ap.add_argument("--limit", type=int, help="ограничить число задач")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="действительно записать (без него — только отчёт)",
    )
    ap.add_argument("--json", action="store_true", help="вывод машинно-читаемым JSON")
    ap.add_argument(
        "--allow-skill-collapse", action="store_true",
        help="промоутить, даже если все задачи замаплены на один навык "
             "(признак пустого графа знаний — по умолчанию это стоп)",
    )
    args = ap.parse_args()

    if not args.run and not args.textbook:
        ap.error("нужен --run или --textbook: промоушен «всего сразу» запрещён намеренно")

    if not os.environ.get("DATABASE_URL"):
        print("DATABASE_URL не задан — БД недоступна.", file=sys.stderr)
        return 2

    try:
        rep = promote(
            run_id=args.run,
            textbook_id=args.textbook,
            dry_run=not args.apply,
            limit=args.limit,
            allow_skill_collapse=args.allow_skill_collapse,
        )
    except Exception as exc:
        print(f"Промоушен не выполнен: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(rep.as_dict(), ensure_ascii=False, indent=2))
        return 0

    mode = "ЧТО БУДЕТ СДЕЛАНО (dry-run)" if rep.dry_run else "ВЫПОЛНЕНО"
    print(f"\n{mode}")
    print(f"  кандидатов (gate=pass, не перенесённых): {rep.candidates}")
    print(f"  перенесено в tasks_master:               {rep.promoted}")
    if rep.blocked_no_skill:
        print(f"  заблокировано: нет skill_id             {rep.blocked_no_skill}")
    if rep.blocked_bad_skill:
        print(f"  заблокировано: skill_id не L4/не найден {rep.blocked_bad_skill}")
    if rep.failed:
        print(f"  ошибок записи:                          {rep.failed}")
        for e in rep.errors[:5]:
            print(f"    - {e}")
    if rep.dry_run and rep.promoted:
        print("\n  Повторите с --apply, чтобы записать.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
