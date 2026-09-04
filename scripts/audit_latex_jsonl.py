#!/usr/bin/env python3
"""Аудит LaTeX в выгрузке задач из файла (не из БД).

Тот же контур проверок, что и `audit_latex_compile.py`, но источник — JSON с
задачами, а не `tasks_master`. Нужен, чтобы мерить качество извлечения до
того, как задачи доехали до БД (и на выходе прототипа mathocr).

    python3 scripts/audit_latex_jsonl.py путь/к/tasks.json
    python3 scripts/audit_latex_jsonl.py out/*/tasks.json --limit-report 5

Формат входа: `{"tasks": [...]}` или просто список. У задачи берутся
`statement_md`, `subtasks[].md`, `answer.md` — то есть весь текст, где
встречаются формулы в `$…$`.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.eval.canonical import extract_formulas_raw  # noqa: E402
from src.validate import katex  # noqa: E402
from src.validate.latex_artifacts import find_artifacts, repair  # noqa: E402


def load_tasks(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data.get("tasks", [])


def task_texts(task: dict) -> list[str]:
    """Все куски текста задачи, где могут быть формулы."""
    out = [task.get("statement_md") or "", task.get("shared_context") or ""]
    out += [s.get("md") or "" for s in (task.get("subtasks") or [])]
    ans = task.get("answer") or {}
    if isinstance(ans, dict):
        out.append(ans.get("md") or "")
    return [t for t in out if t.strip()]


def audit(path: Path, limit_report: int) -> dict:
    tasks = load_tasks(path)
    if not tasks:
        return {"book": path.parent.name, "n_tasks": 0}

    formulas: list[str] = []
    owner: list[str] = []  # task_id для каждой формулы
    for t in tasks:
        tid = t.get("task_id") or t.get("id") or "?"
        for chunk in task_texts(t):
            for f in extract_formulas_raw(chunk):
                formulas.append(f)
                owner.append(tid)

    broken: list[tuple[str, str, str]] = []
    if katex.is_available() and formulas:
        for tid, f, res in zip(owner, formulas, katex.compile_with_errors(formulas)):
            if not res["ok"]:
                broken.append((tid, f, res["error"]))

    arts: list[tuple[str, str, list[str]]] = []
    for tid, f in zip(owner, formulas):
        issues = find_artifacts(f)
        if issues:
            arts.append((tid, f, issues))

    # сколько битых чинится детерминированным ремонтом
    repairable = 0
    if broken and katex.is_available():
        fixed = [repair(f) for _, f, _ in broken]
        repairable = sum(1 for ok in katex.compile_formulas(fixed) if ok)

    res = {
        "book": path.parent.name,
        "n_tasks": len(tasks),
        "n_formulas": len(formulas),
        "n_broken": len(broken),
        "compile_rate": round(1 - len(broken) / len(formulas), 4) if formulas else None,
        "n_artifacts": len(arts),
        "n_broken_repairable": repairable,
    }

    if broken:
        print(f"\n── {path.parent.name}: не компилируется ({len(broken)}) ──", file=sys.stderr)
        for kind, cnt in Counter(b[2].split(":")[0] for b in broken).most_common(6):
            print(f"  {cnt:5d}  {kind}", file=sys.stderr)
        for tid, f, err in broken[:limit_report]:
            print(f"  {tid}: {f[:70]!r}\n      └─ {err[:75]}", file=sys.stderr)
    if arts:
        print(f"\n── {path.parent.name}: артефакты бэкслеша ({len(arts)}) ──", file=sys.stderr)
        for kind, cnt in Counter(i for _, _, iss in arts for i in iss).most_common():
            print(f"  {cnt:5d}  {kind}", file=sys.stderr)
        for tid, f, iss in arts[:limit_report]:
            print(f"  {tid}: {f[:70]!r}\n      └─ {', '.join(iss)}", file=sys.stderr)
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--limit-report", type=int, default=5)
    args = ap.parse_args()

    if not katex.is_available():
        print("[audit] KaTeX недоступен — будет только детектор артефактов", file=sys.stderr)

    rows = [audit(p, args.limit_report) for p in args.paths if p.is_file()]
    print(json.dumps(rows, ensure_ascii=False, indent=2))

    tot_f = sum(r.get("n_formulas", 0) for r in rows)
    tot_b = sum(r.get("n_broken", 0) for r in rows)
    tot_a = sum(r.get("n_artifacts", 0) for r in rows)
    tot_r = sum(r.get("n_broken_repairable", 0) for r in rows)
    if tot_f:
        print(f"\nИТОГО: формул {tot_f}, битых {tot_b} "
              f"(compile_rate {1 - tot_b / tot_f:.4f}), из них чинится ремонтом {tot_r}; "
              f"артефактов {tot_a}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
