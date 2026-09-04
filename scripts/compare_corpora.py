#!/usr/bin/env python3
"""Сравнить два корпуса задач одними и теми же проверками.

Смысл в том, чтобы «стало лучше» перестало быть мнением. Скрипт не знает, какой
корпус чей, и гоняет по обоим один и тот же код: гейты, детектор артефактов,
компиляцию KaTeX, валидатор дистракторов L1–L4.

    python3 scripts/compare_corpora.py \
        --corpus "старый:algo_content_prod:tasks_master" \
        --corpus "новый:algo_content:tasks_staging:28c2535ca4e54295"

Три сигнала измеряются независимо и умышленно не сводятся в один балл:
компиляция формул, лексические артефакты, структура и провенанс. Формула
`x \\cdot y` компилируется молча, будучи бессмыслицей, — поэтому compile_rate
сам по себе ничего не доказывает.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
from typing import Any, Dict, List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text  # noqa: E402

from src.pipeline import provenance as prov  # noqa: E402
from src.pipeline.distractor_gate import validate_distractor_set  # noqa: E402
from src.pipeline.gates import extract_formulas  # noqa: E402
from src.validate import katex, latex_artifacts  # noqa: E402

_NON_ASCII_RE = re.compile(r"[^\x20-\x7E]")
_PLACEHOLDER_ANSWER = {"", "—", "-", "?", "n/a", "нет ответа"}


def _dsn(db: str) -> str:
    base = os.environ.get(
        "COMPARE_DSN", "postgresql://algo:algo_password@localhost:5434/",
    )
    return base.rstrip("/") + "/" + db


_SQL_MASTER = """
SELECT id AS task_id, skill_id, question_text, question_latex,
       correct_answer, answer_type, distractor_meta,
       {prov} AS answer_source
FROM {table}
{where}
"""


def load(
    db: str, table: str, run_id: str | None, textbook_id: str | None = None,
) -> List[Dict[str, Any]]:
    has_prov = table == "tasks_staging"
    clauses: List[str] = []
    params: Dict[str, Any] = {}
    if run_id:
        clauses.append("run_id = :run_id")
        params["run_id"] = run_id
    if textbook_id:
        clauses.append("textbook_id = CAST(:textbook_id AS UUID)")
        params["textbook_id"] = textbook_id
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = _SQL_MASTER.format(
        table=table,
        where=where,
        prov="answer_source" if has_prov else "'unknown'",
    )
    if table == "tasks_staging":
        sql = sql.replace("SELECT id AS task_id", "SELECT task_id")
    engine = create_engine(_dsn(db))
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings()]


def _distractors(row) -> list[dict]:
    raw = row.get("distractor_meta")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    if not isinstance(raw, list):
        return []
    return [d for d in raw if isinstance(d, dict) and str(d.get("value", "")).strip()]


def measure(
    name: str,
    rows: List[Dict[str, Any]],
    *,
    skills: set[str],
    with_distractors: bool = True,
) -> Dict[str, Any]:
    n = len(rows)
    out: Dict[str, Any] = {"корпус": name, "задач": n}
    if not n:
        return out

    # ── провенанс ответа ──────────────────────────────────────────────────
    from_book = sum(1 for r in rows if r["answer_source"] in prov.FROM_BOOK)
    unknown = sum(1 for r in rows if r["answer_source"] == "unknown")
    out["ответ из книги"] = from_book
    out["провенанс неизвестен"] = unknown

    # ── гигиена идентификаторов ───────────────────────────────────────────
    out["id с не-ASCII"] = sum(1 for r in rows if _NON_ASCII_RE.search(r["task_id"] or ""))

    # ── структура ─────────────────────────────────────────────────────────
    out["пустое условие"] = sum(
        1 for r in rows if not (r["question_text"] or "").strip()
    )
    out["ответ-заглушка"] = sum(
        1 for r in rows
        if (r["correct_answer"] or "").strip().lower() in _PLACEHOLDER_ANSWER
    )
    # Демо-узлы (`DEMO_*`) формально уровня L4 и в графе присутствуют, поэтому
    # проверкой «есть в knowledge_hierarchy» не отсеиваются. Считать их
    # привязкой к навыку нельзя — это заглушка, а не содержание.
    out["навык вне графа"] = sum(
        1 for r in rows if r["skill_id"] and r["skill_id"] not in skills
    )
    out["навык-заглушка DEMO"] = sum(
        1 for r in rows if str(r["skill_id"] or "").startswith("DEMO_")
    )
    out["без навыка"] = sum(1 for r in rows if not r["skill_id"])

    # ── лексические артефакты LaTeX ───────────────────────────────────────
    out["с артефактами LaTeX"] = sum(
        1 for r in rows
        if latex_artifacts.has_artifacts(r["question_text"] or "")
        or latex_artifacts.has_artifacts(r["question_latex"] or "")
    )

    # ── компиляция формул ─────────────────────────────────────────────────
    formulas: List[str] = []
    for r in rows:
        formulas.extend(extract_formulas(r["question_text"] or "", r["question_latex"] or ""))
    if katex.is_available() and formulas:
        results = katex.compile_formulas(formulas)
        out["формул"] = len(formulas)
        out["формул не компилируется"] = sum(1 for ok in results if not ok)
    else:
        out["формул"] = len(formulas)
        out["формул не компилируется"] = None  # не измеряли — не 0

    # ── дистракторы ───────────────────────────────────────────────────────
    # Самая дорогая проверка: L1–L4 гоняет sympy на каждом варианте. На 35 202
    # задачах это десятки минут, поэтому её можно выключить — остальные
    # показатели считаются за секунды и не должны быть её заложниками.
    if not with_distractors:
        out["с дистракторами"] = None
        out["дистракторы прошли гейт (≥3)"] = None
        return out

    with_any = valid3 = 0
    for i, r in enumerate(rows, 1):
        if i % 2000 == 0:
            print(f"    дистракторы: {i}/{len(rows)}", flush=True)
        items = _distractors(r)
        if not items:
            continue
        with_any += 1
        accepted, _ = validate_distractor_set(
            items,
            question=r["question_text"] or "",
            correct_answer=r["correct_answer"] or "",
            answer_type=r["answer_type"] or "text",
            max_count=len(items),
            skip_l3=True,  # L3 решает уравнения — на 35k задач это часы
        )
        if len(accepted) >= 3:
            valid3 += 1
    out["с дистракторами"] = with_any
    out["дистракторы прошли гейт (≥3)"] = valid3
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", action="append", required=True,
                    help="имя:база:таблица[:run_id[:textbook_id]]")
    ap.add_argument("--skills-db", default="algo_content",
                    help="база, откуда брать граф знаний для проверки навыков")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-distractors", action="store_true",
                    help="пропустить гейт дистракторов (он самый долгий)")
    args = ap.parse_args()

    engine = create_engine(_dsn(args.skills_db))
    with engine.connect() as conn:
        skills = {
            r[0] for r in conn.execute(
                text("SELECT id FROM knowledge_hierarchy WHERE level='L4'")
            )
        }
    print(f"граф знаний: {len(skills)} узлов L4\n")

    reports = []
    for spec in args.corpus:
        parts = spec.split(":")
        name, db, table = parts[0], parts[1], parts[2]
        run_id = parts[3] if len(parts) > 3 and parts[3] else None
        book = parts[4] if len(parts) > 4 and parts[4] else None
        rows = load(db, table, run_id, book)
        if args.limit:
            rows = rows[: args.limit]
        print(f"считаю «{name}»: {len(rows)} задач…", flush=True)
        reports.append(measure(
            name, rows, skills=skills, with_distractors=not args.no_distractors,
        ))

    keys: List[str] = []
    for rep in reports:
        for k in rep:
            if k != "корпус" and k not in keys:
                keys.append(k)

    width = max(len(k) for k in keys) + 2
    header = "показатель".ljust(width) + "".join(r["корпус"].rjust(22) for r in reports)
    print("\n" + header)
    print("-" * len(header))
    total = {r["корпус"]: r.get("задач") or 1 for r in reports}
    for k in keys:
        line = k.ljust(width)
        for rep in reports:
            v = rep.get(k)
            if v is None:
                cell = "не измерено"
            elif k == "задач":
                cell = str(v)
            elif k == "формул":
                cell = str(v)
            elif k == "формул не компилируется":
                base = rep.get("формул") or 1
                cell = f"{v} ({100.0 * v / base:.2f}%)"
            else:
                cell = f"{v} ({100.0 * v / total[rep['корпус']]:.1f}%)"
            line += cell.rjust(22)
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
