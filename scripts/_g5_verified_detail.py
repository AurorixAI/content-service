#!/usr/bin/env python3
import sys
sys.path.insert(0, "/app")
from sqlalchemy import create_engine, text
from src.core.config import get_settings

e = create_engine(get_settings().database_url)
with e.connect() as c:
    rows = c.execute(text("""
        SELECT coalesce(tags->>'smart_verify_status', '(null)') AS st, count(*)
        FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE tb.class_level = 5
        GROUP BY 1 ORDER BY 2 DESC
    """)).all()
    print("=== smart_verify_status ===")
    for st, n in rows:
        print(f"  {st}: {n}")

    v = c.execute(text("""
        SELECT
          count(*) FILTER (WHERE tags->>'smart_verify_status' IN (
            'verified_match','verified_corrected','generated_from_scratch')) AS sv_ok,
          count(*) FILTER (WHERE verification_status='verified'
            AND coalesce(nullif(tags->>'smart_verify_status',''),'pending')='pending') AS verified_no_sv,
          count(*) FILTER (WHERE tm.id LIKE '%.%' AND tags->>'smart_verify_status' IN (
            'verified_match','verified_corrected','generated_from_scratch')) AS children_sv,
          count(*) FILTER (WHERE tm.id NOT LIKE '%.%' AND tags->>'smart_verify_status' IN (
            'verified_match','verified_corrected','generated_from_scratch')) AS parents_sv,
          count(*) FILTER (WHERE tags->>'compound_whole' IS NOT NULL) AS compound_whole,
          count(*) FILTER (WHERE tags->>'compound_split_resolved'='keep_whole'
            AND tags->>'smart_verify_status' IN ('verified_match','verified_corrected')) AS keep_whole_sv
        FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE tb.class_level = 5
    """)).one()

    print("\n=== verified breakdown ===")
    print(f"  smart_verify OK total:     {v.sv_ok}")
    print(f"  verification=verified но sv=pending: {v.verified_no_sv}")
    print(f"  children (.suffix) sv OK:  {v.children_sv}")
    print(f"  parents (no dot) sv OK:      {v.parents_sv}")
    print(f"  compound_whole:              {v.compound_whole}")
    print(f"  keep_whole + sv OK:          {v.keep_whole_sv}")

    early = c.execute(text("""
        SELECT count(*) FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE tb.class_level = 5
          AND tags->>'smart_verify_status' IN ('verified_match','verified_corrected','generated_from_scratch')
          AND tm.updated_at < timestamp '2026-07-05 18:00:00'
    """)).scalar()
    late = c.execute(text("""
        SELECT count(*) FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE tb.class_level = 5
          AND tags->>'smart_verify_status' IN ('verified_match','verified_corrected','generated_from_scratch')
          AND tm.updated_at >= timestamp '2026-07-05 18:00:00'
    """)).scalar()
    print(f"\n  sv OK до 5 июл 18:00 (1-й bulk): {early}")
    print(f"  sv OK после 5 июл 18:00 (текущий): {late}")
