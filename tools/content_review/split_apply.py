# -*- coding: utf-8 -*-
"""Apply a split built by split_build.py in one transaction (dry run unless --execute).

Children are inserted with the parent's metadata (skill, difficulty, source, toc, ...) and the
fields from split_J_<name>.json; each parent is deactivated (never deleted) with provenance.
Reversible with one statement per table state:
  UPDATE tasks_master SET is_active=false WHERE tags->>'split_batch'='<name>';
  UPDATE tasks_master SET is_active=true,
         tags = tags - 'deactivated_reason' - 'deactivated_at' - 'deactivated_by'
                     - 'deactivation_batch' - 'deactivation_approved_by' - 'split_into'
  WHERE tags->>'deactivation_batch'='split-<name>';
Usage: split_apply.py <name> --approved-by <who> [--execute]
"""
import argparse, json
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import Json

ap = argparse.ArgumentParser()
ap.add_argument("name"); ap.add_argument("--approved-by", required=True); ap.add_argument("--execute", action="store_true")
a = ap.parse_args()
J = json.load(open(f"/audit/split_J_{a.name}.json"))
COPY = ("skill_id", "question_image_url", "answer_type", "difficulty", "toc_id", "cognitive_load",
        "verification_status", "source_type", "source_reference", "is_star", "task_category", "latex_status")
now = datetime.now(timezone.utc).isoformat()
cn = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content"); c = cn.cursor()
c.execute("SELECT count(*) FROM tasks_master WHERE is_active"); before = c.fetchone()[0]
parents = sorted(J["retire"])
c.execute("SELECT id FROM tasks_master WHERE id = ANY(%s) AND is_active FOR UPDATE", (parents,))
assert len(c.fetchall()) == len(parents), "a parent is missing or inactive"
c.execute("SELECT id FROM tasks_master WHERE id = ANY(%s)", (sorted(J["new"]),))
assert not c.fetchall(), "a child id already exists"
for cid, e in J["new"].items():
    c.execute(f"SELECT {', '.join(COPY)} FROM tasks_master WHERE id=%s", (e["parent"],))
    base = dict(zip(COPY, c.fetchone())); f = e["fields"]
    row = {**base, "id": cid, **{k: (Json(v) if isinstance(v, (dict, list)) else v) for k, v in f.items()},
           "is_active": True, "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()}
    cols = list(row)
    c.execute(f"INSERT INTO tasks_master ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})", [row[k] for k in cols])
for pid, e in J["retire"].items():
    c.execute("""UPDATE tasks_master SET is_active=false, updated_at=now(),
                 tags = COALESCE(tags,'{}'::jsonb) || jsonb_build_object(
                   'deactivated_reason', CAST(%s AS text), 'deactivated_at', CAST(%s AS text),
                   'deactivated_by', 'content-review', 'deactivation_batch', CAST(%s AS text),
                   'deactivation_approved_by', CAST(%s AS text), 'split_into', CAST(%s AS jsonb))
                 WHERE id=%s AND is_active""",
              ("разбита на отдельные задачи по пунктам: " + e["why"], now, "split-" + a.name, a.approved_by, json.dumps(e["children"]), pid))
    assert c.rowcount == 1, pid
c.execute("SELECT count(*) FROM tasks_master WHERE is_active"); after = c.fetchone()[0]
delta = len(J["new"]) - len(parents)
assert after - before == delta, (before, after, delta)
print(f"split={a.name} parents={len(parents)} children={len(J['new'])} active {before}->{after}")
if a.execute:
    cn.commit(); print("COMMITTED")
else:
    cn.rollback(); print("[DRY RUN] rolled back, nothing written")
