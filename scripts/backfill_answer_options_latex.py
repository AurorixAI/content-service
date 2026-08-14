#!/usr/bin/env python3
"""Populate tasks_master.answer_options_latex without touching raw options.

This is intentionally separate from distractor backfill.  Legacy options often
have formatting that does not byte-match distractor_meta, so positional or
fuzzy matching would be unsafe.  Each raw answer_options item gets its own
parallel display value in the new JSONB column.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

from backfill_latex_deepseek import field_is_acceptable, format_latex  # noqa: E402


def option_text(option: object) -> str:
    if isinstance(option, dict):
        return str(option.get("value") or option.get("text") or option.get("content") or "").strip()
    return str(option or "").strip()


def options_fingerprint(options: object) -> str:
    payload = json.dumps(options, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def process_task(task_id: str, options: object, existing_latex: object, semaphore: asyncio.Semaphore) -> dict:
    raw_options = list(options) if isinstance(options, list) else []
    current = list(existing_latex) if isinstance(existing_latex, list) else []
    jobs: list[tuple[int, object]] = []
    output = list(current)
    if len(output) < len(raw_options):
        output.extend([""] * (len(raw_options) - len(output)))

    for index, option in enumerate(raw_options):
        if option_text(option) and not str(output[index] or "").strip():
            jobs.append((index, format_latex(option_text(option), semaphore)))

    results = await asyncio.gather(*[job for _, job in jobs])
    failures: dict[str, str] = {}
    for (index, _), result in zip(jobs, results):
        if field_is_acceptable(result):
            output[index] = result["canonical"]
        else:
            failures[str(index)] = result.get("ambiguity_reason") or result.get("katex_error") or "unacceptable"

    return {
        "task_id": task_id,
        "raw_options": copy.deepcopy(raw_options),
        "raw_fingerprint": options_fingerprint(raw_options),
        "latex_options": output,
        "failures": failures,
    }


def save_result(conn, result: dict) -> None:
    current = conn.execute(text("""
        SELECT answer_options
        FROM tasks_master
        WHERE id = :id
        FOR UPDATE
    """), {"id": result["task_id"]}).fetchone()
    if current is None:
        raise RuntimeError(f"Task {result['task_id']} disappeared before write")
    if options_fingerprint(current[0]) != result["raw_fingerprint"]:
        raise RuntimeError(f"Raw answer_options changed concurrently for task {result['task_id']}; refusing to write")
    conn.execute(text("""
        UPDATE tasks_master
        SET answer_options_latex = :latex_options,
            latex_normalized_at = NOW()
        WHERE id = :id
    """), {"id": result["task_id"], "latex_options": json.dumps(result["latex_options"], ensure_ascii=False)})

    # `latex_status` covers the full display contract, not just answer options.
    # Recompute it after the parallel option array is written; otherwise a task
    # repaired by this second-stage script would remain `partial` forever.
    conn.execute(text("""
        UPDATE tasks_master AS tm
        SET latex_status = CASE
            WHEN
                (COALESCE(btrim(tm.question_text), '') = '' OR COALESCE(btrim(tm.question_latex), '') <> '')
                AND (COALESCE(btrim(tm.correct_answer), '') = '' OR COALESCE(btrim(tm.correct_answer_latex), '') <> '')
                AND NOT EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(COALESCE(tm.distractor_meta, '[]'::jsonb)) AS d
                    WHERE (
                        COALESCE(NULLIF(btrim(d->>'value'), ''), NULLIF(btrim(d->>'text'), ''), NULLIF(btrim(d->>'content'), ''), '') <> ''
                        AND COALESCE(NULLIF(btrim(d->>'value_latex'), ''), NULLIF(btrim(d->>'text_latex'), ''), NULLIF(btrim(d->>'content_latex'), ''), '') = ''
                    ) OR (
                        COALESCE(NULLIF(btrim(d->>'error_logic'), ''), NULLIF(btrim(d->>'explanation'), ''), '') <> ''
                        AND CASE
                            WHEN NULLIF(btrim(d->>'error_logic'), '') IS NOT NULL THEN COALESCE(NULLIF(btrim(d->>'error_logic_latex'), ''), '')
                            ELSE COALESCE(NULLIF(btrim(d->>'explanation_latex'), ''), '')
                        END = ''
                    )
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(COALESCE(tm.answer_options, '[]'::jsonb)) WITH ORDINALITY AS opt(item, idx)
                    WHERE COALESCE(NULLIF(btrim(opt.item->>'value'), ''), NULLIF(btrim(opt.item->>'text'), ''), NULLIF(btrim(opt.item->>'content'), ''), NULLIF(btrim(opt.item #>> '{}'), ''), '') <> ''
                      AND COALESCE(
                          NULLIF(btrim((CAST(:latex_options AS jsonb) ->> (opt.idx - 1))), ''),
                          NULLIF(btrim(opt.item->>'value_latex'), ''),
                          NULLIF(btrim(opt.item->>'text_latex'), ''),
                          NULLIF(btrim(opt.item->>'content_latex'), ''),
                          NULLIF(btrim(opt.item->>'latex'), ''),
                          ''
                      ) = ''
                )
            THEN 'verified'
            ELSE 'partial'
        END
        WHERE tm.id = :id
    """), {
        "id": result["task_id"],
        "latex_options": json.dumps(result["latex_options"], ensure_ascii=False),
    })
    if result["failures"]:
        conn.execute(text("""
            INSERT INTO review_queue (item_type, item_id, review_reason, priority, status, ai_suggestion)
            SELECT 'task', :task_id, 'answer_options_latex_backfill_failed', 'high', 'pending', :suggestion
            WHERE NOT EXISTS (
                SELECT 1 FROM review_queue
                WHERE item_type = 'task'
                  AND item_id = :task_id
                  AND review_reason = 'answer_options_latex_backfill_failed'
                  AND status = 'pending'
            )
        """), {
            "task_id": str(result["task_id"]),
            "suggestion": json.dumps(result["failures"], ensure_ascii=False),
        })


async def main() -> int:
    parser = argparse.ArgumentParser(description="Fill parallel answer_options_latex safely")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--task-id", action="append", default=[], help="Restrict to an exact task ID (repeatable)")
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL") or "postgresql://algo:algo_password@127.0.0.1:5434/algo_content"
    engine = create_engine(db_url)
    task_filter = "AND id = ANY(:task_ids)" if args.task_id else ""
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT id, answer_options, answer_options_latex
            FROM tasks_master
            WHERE is_active = true
              AND answer_options IS NOT NULL
              AND jsonb_array_length(answer_options) > 0
              AND (
                  answer_options_latex IS NULL
                  OR jsonb_array_length(answer_options_latex) < jsonb_array_length(answer_options)
                  OR EXISTS (
                      SELECT 1
                      FROM jsonb_array_elements_text(answer_options_latex) AS latex(value)
                      WHERE btrim(latex.value) = ''
                  )
              )
              {task_filter}
            ORDER BY id DESC
        """), {"task_ids": args.task_id} if args.task_id else {}).fetchall()
    if args.limit:
        rows = rows[:args.limit]

    print(f"mode={'EXECUTE' if args.execute else 'DRY-RUN'} candidates={len(rows)}")
    semaphore = asyncio.Semaphore(args.concurrency)
    results = []
    for row in rows:
        result = await process_task(row[0], row[1], row[2], semaphore)
        results.append(result)
        if len(results) <= args.samples:
            print(f"task={row[0]} fields={len(result['latex_options'])} failures={len(result['failures'])}")

    if args.execute:
        with engine.begin() as conn:
            for result in results:
                save_result(conn, result)
    failed = sum(len(result["failures"]) for result in results)
    print(f"completed={len(results)} failures={failed} writes={len(results) if args.execute else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
