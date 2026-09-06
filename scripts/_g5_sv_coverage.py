#!/usr/bin/env python3
import sys
sys.path.insert(0, "/app")
from sqlalchemy import create_engine, text
from src.core.config import get_settings

e = create_engine(get_settings().database_url)
with e.connect() as c:
    r = c.execute(text("""
        SELECT
          count(*) AS total,
          count(*) FILTER (
            WHERE coalesce(nullif(tags->>'smart_verify_status',''),'pending') = 'pending'
          ) AS pending,
          count(*) FILTER (
            WHERE tags->>'smart_verify_status' IN (
              'verified_match','verified_corrected','generated_from_scratch'
            )
          ) AS already_verified,
          count(*) FILTER (
            WHERE tags->>'smart_verify_status' LIKE 'failed%'
          ) AS failed,
          count(*) FILTER (
            WHERE tags->>'smart_verify_status' = 'needs_human_review'
          ) AS human,
          count(*) FILTER (
            WHERE tags->>'smart_verify_run_id' IS NOT NULL
              AND tags->>'smart_verify_run_id' != ''
          ) AS has_run_id,
          count(*) FILTER (
            WHERE tags->>'smart_verify_status' IN ('verified_match','verified_corrected')
              AND coalesce(tags->>'smart_verify_run_id','') = ''
          ) AS verified_no_run_id
        FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE tb.class_level = 5
    """)).one()

print("G5 smart_verify coverage")
print(f"  total:              {r.total}")
print(f"  pending (1st pass): {r.pending}")
print(f"  already verified:   {r.already_verified}")
print(f"  failed:             {r.failed}")
print(f"  human_review:       {r.human}")
print(f"  with run_id tag:    {r.has_run_id}")
print(f"  verified NO run_id: {r.verified_no_run_id}  <- старый проход, не reprocess")
