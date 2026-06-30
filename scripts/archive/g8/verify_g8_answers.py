#!/usr/bin/env python3
"""
Проверка корректности ответов G8 Макарычев.

1. Структурный аудит (пустые, подозрительные)
2. Gemini spot-check: перерешать выборку и сравнить с БД
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sys
import time

sys.path.insert(0, "/app")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("verify_answers")

from sqlalchemy import create_engine, text
from src.core.config import get_settings
from src.pipeline.gemini_client import call_gemini, get_flash_model, parse_json_response

TB = "b8f4a2c1-3d5e-4f60-9182-3456789abcde"

# Типы, где Gemini может осмысленно перепроверить
GEMINI_TYPES = frozenset({
    "exact_number", "expression", "equation_solution",
    "inequality", "fraction", "set",
})


def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"\s+", "", s)
    s = s.replace("−", "-").replace("–", "-").replace(",", ".")
    s = re.sub(r"^\d+\)\s*", "", s)
    s = re.sub(r"^[абвг]\)\s*", "", s)
    return s


def _answers_match(stored: str, solved: str) -> bool:
    a, b = _norm(stored), _norm(solved)
    if not a or not b:
        return False
    if a == b:
        return True
    # numeric tolerance
    try:
        fa, fb = float(a), float(b)
        return abs(fa - fb) < 1e-6
    except ValueError:
        pass
    # substring / set overlap for multi-value
    if len(a) > 3 and (a in b or b in a):
        return True
    return False


def structural_audit(engine) -> dict:
    with engine.connect() as c:
        rows = c.execute(
            text("""
                SELECT tm.id, tm.answer_type, tm.correct_answer,
                       tm.question_text, tm.tags,
                       (tm.tags ? 'split_from') AS is_split_child
                FROM tasks_master tm
                JOIN textbook_toc t ON t.id = tm.toc_id
                WHERE t.textbook_id = CAST(:tb AS UUID)
            """),
            {"tb": TB},
        ).mappings().all()

    total = len(rows)
    empty = []
    dash = []
    sympy_ok = 0
    sympy_tag = 0
    by_type: dict[str, dict] = {}

    for r in rows:
        at = r["answer_type"] or "?"
        by_type.setdefault(at, {"n": 0, "empty": 0, "has": 0})
        by_type[at]["n"] += 1
        ans = (r["correct_answer"] or "").strip()
        if not ans:
            empty.append(r["id"])
            by_type[at]["empty"] += 1
        elif ans in ("—", "-", "?"):
            dash.append(r["id"])
            by_type[at]["empty"] += 1
        else:
            by_type[at]["has"] += 1
        tags = r["tags"] or {}
        if isinstance(tags, str):
            tags = json.loads(tags) if tags else {}
        if tags.get("sympy_verified"):
            sympy_ok += 1
        if tags.get("sympy_verified") is not None:
            sympy_tag += 1

    split_empty = sum(
        1 for r in rows
        if r["is_split_child"] and not (r["correct_answer"] or "").strip()
    )
    split_total = sum(1 for r in rows if r["is_split_child"])

    return {
        "total": total,
        "empty": len(empty),
        "dash": len(dash),
        "sympy_verified": sympy_ok,
        "by_type": by_type,
        "split_total": split_total,
        "split_empty": split_empty,
        "empty_ids_sample": empty[:15],
    }


def sample_tasks(engine, n: int, seed: int) -> list[dict]:
    with engine.connect() as c:
        rows = c.execute(
            text("""
                SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type
                FROM tasks_master tm
                JOIN textbook_toc t ON t.id = tm.toc_id
                WHERE t.textbook_id = CAST(:tb AS UUID)
                  AND tm.correct_answer IS NOT NULL
                  AND tm.correct_answer != ''
                  AND tm.correct_answer NOT IN ('—', '-', '?')
                  AND tm.answer_type = ANY(:types)
                ORDER BY tm.id
            """),
            {"tb": TB, "types": list(GEMINI_TYPES)},
        ).mappings().all()

    pool = [dict(r) for r in rows]
    random.seed(seed)
    if len(pool) <= n:
        return pool
    # stratified: pick proportionally by type
    by_t: dict[str, list] = {}
    for r in pool:
        by_t.setdefault(r["answer_type"], []).append(r)
    out = []
    per = max(1, n // len(by_t))
    for tasks in by_t.values():
        out.extend(random.sample(tasks, min(per, len(tasks))))
    while len(out) < n and len(out) < len(pool):
        r = random.choice(pool)
        if r not in out:
            out.append(r)
    return out[:n]


def _gemini_solve(question: str, answer_type: str) -> str:
    prompt = (
        "Ты — математический педагог. Реши задачу и верни только ответ.\n\n"
        f"Текст: {question}\n"
        f"Тип ответа: {answer_type}\n\n"
        'Верни JSON: {"answer":"<окончательный ответ>"}\n'
        "answer — точный финальный ответ. Только JSON."
    )
    raw = call_gemini(
        prompt, model=get_flash_model(), temperature=0.1, max_tokens=2048,
        thinking_budget=0,
    )
    data = parse_json_response(raw)
    if isinstance(data, dict):
        ans = data.get("answer", "")
        if isinstance(ans, (int, float)):
            return str(ans)
        return str(ans).strip()
    return ""


def gemini_spot_check(tasks: list[dict], sleep: float = 0.5) -> dict:
    match = mismatch = fail = 0
    mismatches = []

    for row in tasks:
        try:
            solved = _gemini_solve(row["question_text"] or "", row["answer_type"] or "exact_number")
        except Exception as e:
            log.warning("%s solver error: %s", row["id"], e)
            fail += 1
            time.sleep(sleep)
            continue

        stored = (row["correct_answer"] or "").strip()
        if _answers_match(stored, solved):
            match += 1
            log.info("  ✓ %s", row["id"])
        else:
            mismatch += 1
            mismatches.append({
                "id": row["id"],
                "type": row["answer_type"],
                "stored": stored[:120],
                "gemini": solved[:120],
            })
            log.warning("  ✗ %s\n    stored: %s\n    gemini: %s",
                        row["id"], stored[:80], solved[:80])
        time.sleep(sleep)

    return {
        "checked": len(tasks),
        "match": match,
        "mismatch": mismatch,
        "solver_fail": fail,
        "mismatches": mismatches,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=25,
                    help="Gemini spot-check sample size (0=skip)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--sleep", type=float, default=0.4)
    ap.add_argument("--struct-only", action="store_true")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)

    log.info("=" * 60)
    log.info("STRUCTURAL AUDIT — G8 Макарычев")
    log.info("=" * 60)
    s = structural_audit(engine)
    log.info("Всего задач: %d", s["total"])
    log.info("Пустой ответ: %d (%.1f%%)", s["empty"], 100 * s["empty"] / max(s["total"], 1))
    log.info("SymPy verified (tags): %d", s["sympy_verified"])
    log.info("Split-дети: %d, пустых ответов: %d",
             s["split_total"], s["split_empty"])
    log.info("По типам (n / empty / ok):")
    for at, st in sorted(s["by_type"].items(), key=lambda x: -x[1]["n"]):
        log.info("  %-20s %4d  empty=%d  ok=%d",
                 at, st["n"], st["empty"], st["has"])

    if args.struct_only or args.sample <= 0:
        return 0

    log.info("=" * 60)
    log.info("GEMINI SPOT-CHECK (n=%d)", args.sample)
    log.info("=" * 60)
    sample = sample_tasks(engine, args.sample, args.seed)
    log.info("Выборка: %d задач", len(sample))
    g = gemini_spot_check(sample, sleep=args.sleep)
    checked = g["checked"] or 1
    log.info("=" * 60)
    log.info("ИТОГ spot-check: %d/%d совпали (%.0f%%) | mismatch=%d | fail=%d",
             g["match"], checked, 100 * g["match"] / checked,
             g["mismatch"], g["solver_fail"])
    if g["mismatches"]:
        log.info("Расхождения:")
        for m in g["mismatches"][:10]:
            log.info("  %s [%s]", m["id"], m["type"])
            log.info("    DB: %s", m["stored"])
            log.info("    AI: %s", m["gemini"])
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
