#!/usr/bin/env python3
"""Re-run digitization to fill missing tasks (no DB wipe, upsert by id).

Content-first mode: Flash, full § re-extract, dedup by question text.
Tasks are anchored by paragraph — exact global exercise numbers are optional.

Usage:
    docker exec content-worker python /app/scripts/gap_fill_reingest.py --key g5_idum_ch2
    docker exec content-worker python /app/scripts/gap_fill_reingest.py --key g5_idum_ch2 --dry-run
    docker exec content-worker python /app/scripts/gap_fill_reingest.py --key g5_idum_ch2 --paragraph 68
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from scripts.full_reingest import _by_key
from src.core.config import get_settings
from src.core.job_enqueue import enqueue_digitization
from src.core.job_state import JobStateManager


def _audit_content_gaps(textbook_id: str) -> list[tuple[str, str, int, str]]:
    """§ that are empty or likely incomplete (by task count, not scan ranges)."""
    from scripts.audit_all_paragraphs import audit_textbook, load_textbooks

    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        rows = load_textbooks(conn)
        tb = next((r for r in rows if r.textbook_id == textbook_id), None)
        if not tb:
            return []
        rep = audit_textbook(conn, tb)

    gaps: list[tuple[str, str, int, str]] = []
    for item in rep["empty"] + rep["partial"]:
        num = str(item["number"]).split(".")[0]
        gaps.append((num, item["title"], item["tasks"], item["detail"]))
    return gaps


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True, help="e.g. g5_idum_ch1")
    ap.add_argument("--paragraph", help="single § only, e.g. 68")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    tb = _by_key(args.key)
    if not tb:
        print(f"Unknown key: {args.key}")
        return 1

    gaps = _audit_content_gaps(tb["id"])
    if args.paragraph:
        para = args.paragraph.strip().split(".")[0]
        gaps = [g for g in gaps if g[0] == para]
        if not gaps:
            # allow explicit re-run even if audit says OK
            engine = create_engine(get_settings().database_url)
            with engine.connect() as conn:
                row = conn.execute(
                    text("""
                        SELECT number, title,
                               (SELECT count(*) FROM tasks_master tm
                                JOIN textbook_tasks tt ON tt.task_id = tm.id
                                WHERE tt.textbook_id = CAST(:tid AS UUID)
                                  AND tt.paragraph_number = l.number) AS tasks
                        FROM textbook_toc l
                        WHERE textbook_id = CAST(:tid AS UUID)
                          AND split_part(number, '.', 1) = :para
                        LIMIT 1
                    """),
                    {"tid": tb["id"], "para": para},
                ).fetchone()
            if row:
                gaps = [(para, row.title or "", row.tasks or 0, "manual")]

    print(f"=== CONTENT-FIRST GAP-FILL {tb['title']} ===")
    print(f"§ to re-extract: {len(gaps)}  (Flash, full §, dedup by text)")
    for num, title, tasks, detail in gaps[:20]:
        print(f"  §{num:<4} {tasks:>3} tasks  {detail[:45]:<45}  {title[:35]}")
    if len(gaps) > 20:
        print(f"  ... +{len(gaps) - 20} more")

    if not gaps:
        print("Nothing to fill.")
        return 0

    if args.dry_run:
        print("\n[DRY-RUN] No job created.")
        return 0

    target = sorted({g[0] for g in gaps}, key=lambda x: int(x) if x.isdigit() else 0)
    job_id = str(uuid.uuid4())
    JobStateManager().create(
        job_id=job_id,
        textbook_id=tb["id"],
        class_level=tb["class_level"],
        source_type="pdf",
        source_path=tb["pdf"],
        content_first=True,
        target_paragraphs=target,
    )
    asyncio.run(enqueue_digitization(job_id))
    print(f"\njob_id: {job_id}")
    print(f"  target §: {', '.join(target)}")
    print(f"  docker exec content-worker python /app/scripts/report_job.py {job_id} --watch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
