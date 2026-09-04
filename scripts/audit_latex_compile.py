#!/usr/bin/env python3
"""Аудит LaTeX в банке задач: что не компилируется и где артефакты бэкслеша.

    python3 scripts/audit_latex_compile.py --class-level 8              # только отчёт
    python3 scripts/audit_latex_compile.py --class-level 8 --repair --dry-run
    python3 scripts/audit_latex_compile.py --class-level 8 --repair     # ЗАПИСЬ В БД

Проверяются `question_latex` и `correct_answer_latex`. `value_latex` внутри
`distractor_meta` (JSONB) — пока нет: дистракторы правит отдельный контур
(`distractor_gate`), лезть туда этим скриптом опасно. Вынесено в С4.

**Две независимые проверки, обе нужны:**
1. Компиляция KaTeX — ловит структурные поломки (`\\left` без пары, незакрытая
   скобка, несуществующая команда).
2. Детектор артефактов — ловит то, что компилируется, но семантически неверно
   (`rac{1}{2}` рендерится текстом; `x \\\\cdot y` — перенос строки вместо умножения).

**Запись в БД только с явным `--repair` и без `--dry-run`.** Перед массовым
прогоном сделай бэкап: `scripts/backup_algo_content.sh` (правило 7 CLAUDE.md).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for p in ("/app", str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from sqlalchemy import create_engine, text  # noqa: E402

from src.validate import katex  # noqa: E402
from src.validate.latex_artifacts import find_artifacts, repair  # noqa: E402

# ВНИМАНИЕ (B10): `correct_answer_latex` читают 9 модулей, включая API-роутер,
# но НИ ОДНА миграция её не создаёт — на чистой БД из `alembic upgrade head`
# колонки не будет. Поэтому состав полей определяется по факту, а не жёстко.
_CANDIDATE_FIELDS = ("question_latex", "correct_answer_latex")

_COLUMNS = text("""
    SELECT column_name FROM information_schema.columns
     WHERE table_name = 'tasks_master'
""")


def _select_sql(fields: tuple[str, ...]) -> text:
    cols = ",\n           ".join(f"COALESCE(tm.{f}, '') AS {f}" for f in fields)
    return text(f"""
        SELECT tm.id,
               {cols}
        FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb     ON tb.textbook_id = toc.textbook_id
        WHERE tb.class_level = :level
          AND tm.is_active = TRUE
    """)


def _update_sql(fields: tuple[str, ...]) -> text:
    sets = ", ".join(f"{f} = :{f}" for f in fields)
    return text(f"UPDATE tasks_master SET {sets}, updated_at = NOW() WHERE id = :id")


def _engine():
    url = os.environ.get("DATABASE_URL")
    if not url:
        from src.core.config import get_settings

        url = get_settings().database_url
    return create_engine(url)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--class-level", type=int, required=True)
    ap.add_argument("--repair", action="store_true", help="чинить артефакты")
    ap.add_argument("--dry-run", action="store_true", help="с --repair: показать, не писать")
    ap.add_argument("--limit-report", type=int, default=20, help="сколько примеров печатать")
    args = ap.parse_args()

    try:
        engine = _engine()
        with engine.connect() as conn:
            present = {r[0] for r in conn.execute(_COLUMNS)}
            fields = tuple(f for f in _CANDIDATE_FIELDS if f in present)
            if not fields:
                print("[audit] в tasks_master нет ни одной LaTeX-колонки", file=sys.stderr)
                return 1
            missing = set(_CANDIDATE_FIELDS) - present
            if missing:
                print(f"[audit] нет колонок {sorted(missing)} — пропускаю их (см. B10 "
                      "в CLAUDE.md: колонка есть в проде, но не в миграциях)",
                      file=sys.stderr)
            rows = [dict(r) for r in
                    conn.execute(_select_sql(fields), {"level": args.class_level}).mappings()]
    except Exception as exc:  # noqa: BLE001
        print(f"[audit] нет доступа к БД: {exc}", file=sys.stderr)
        return 2

    if not rows:
        print(f"[audit] нет активных задач для класса {args.class_level}", file=sys.stderr)
        return 1

    # ── 1. Компиляция ──────────────────────────────────────────────────────
    flat: list[str] = []
    index: list[tuple[int, str]] = []  # (номер строки, имя поля)
    for i, r in enumerate(rows):
        for f in fields:
            if (r[f] or "").strip():
                flat.append(r[f])
                index.append((i, f))

    compile_results = None
    if not katex.is_available():
        print("[audit] KaTeX недоступен (нет node или `npm install`) — "
              "проверка компиляции пропущена", file=sys.stderr)
    else:
        compile_results = katex.compile_with_errors(flat)

    broken: list[tuple[str, str, str, str]] = []  # (task_id, поле, latex, ошибка)
    if compile_results:
        for (i, f), res in zip(index, compile_results):
            if not res["ok"]:
                broken.append((rows[i]["id"], f, rows[i][f], res["error"]))

    # ── 2. Артефакты (ловят то, что компилируется, но неверно) ─────────────
    artifacts: list[tuple[str, str, str, list[str]]] = []
    for r in rows:
        for f in fields:
            issues = find_artifacts(r[f])
            if issues:
                artifacts.append((r["id"], f, r[f], issues))

    # ── Отчёт ──────────────────────────────────────────────────────────────
    n_formulas = len(flat)
    rate = (1 - len(broken) / n_formulas) if (compile_results and n_formulas) else None
    print(json.dumps({
        "class_level": args.class_level,
        "n_tasks": len(rows),
        "n_latex_fields": n_formulas,
        "compile_rate": round(rate, 4) if rate is not None else None,
        "n_compile_broken": len(broken) if compile_results else None,
        "n_with_artifacts": len(artifacts),
    }, ensure_ascii=False, indent=2))

    if broken:
        print(f"\n── Не компилируется ({len(broken)}) ──", file=sys.stderr)
        for kind, cnt in Counter(b[3].split(":")[0] for b in broken).most_common():
            print(f"  {cnt:5d}  {kind}", file=sys.stderr)
        for tid, f, ltx, err in broken[: args.limit_report]:
            print(f"  {tid} [{f}] {ltx[:70]!r}\n        └─ {err[:80]}", file=sys.stderr)

    if artifacts:
        print(f"\n── Артефакты бэкслеша ({len(artifacts)}) ──", file=sys.stderr)
        for kind, cnt in Counter(i for _, _, _, iss in artifacts for i in iss).most_common():
            print(f"  {cnt:5d}  {kind}", file=sys.stderr)
        for tid, f, ltx, iss in artifacts[: args.limit_report]:
            print(f"  {tid} [{f}] {ltx[:70]!r}\n        └─ {', '.join(iss)}", file=sys.stderr)

    # ── 3. Ремонт ──────────────────────────────────────────────────────────
    if not args.repair:
        if artifacts or broken:
            print("\n[audit] это только отчёт. Чинить: --repair --dry-run, "
                  "затем --repair (после бэкапа)", file=sys.stderr)
        return 0

    changed = []
    for r in rows:
        new = {f: repair(r[f]) for f in fields}
        if any(new[f] != r[f] for f in fields):
            changed.append((r["id"], r, new))

    print(f"\n[audit] ремонт затронет задач: {len(changed)}", file=sys.stderr)
    for tid, old, new in changed[: args.limit_report]:
        for f in fields:
            if old[f] != new[f]:
                print(f"  {tid} [{f}]\n    - {old[f][:80]!r}\n    + {new[f][:80]!r}",
                      file=sys.stderr)

    if args.dry_run:
        print("\n[audit] --dry-run: в БД ничего не записано", file=sys.stderr)
        return 0

    if not changed:
        return 0

    with engine.begin() as conn:
        upd = _update_sql(fields)
        for tid, _old, new in changed:
            conn.execute(upd, {"id": tid, **{f: new[f] for f in fields}})
    print(f"[audit] записано в БД: {len(changed)} задач", file=sys.stderr)
    print("[audit] перепроверь метрики: python3 scripts/eval.py --class-level "
          f"{args.class_level}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
