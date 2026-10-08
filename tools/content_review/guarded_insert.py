"""Insert reviewed NEW tasks into tasks_master (manifest key ``new_tasks``).

Sibling of guarded_repair.py, which cannot create tasks. Rules:

* dry-run is the default and runs in a READ ONLY transaction (nothing can be written);
* every id in the manifest must be absent (any existing id aborts the whole
  batch; the only exception is an exact replay: every row already present and
  identical to the pinned ``after_sha256`` -> reported as ``already_applied``);
* every row carries ALL FIELDS explicitly, so the stored row is exactly the
  fingerprinted one (no silent column defaults);
* all rows are inserted in ONE transaction and re-read/fingerprinted before commit;
* execution requires a private (0600, O_EXCL) backup written before the first INSERT;
* rollback deletes ONLY the inserted ids, and only if the row is still
  byte-identical (fingerprint) and nothing references it (attestations, audits,
  figure refs, textbook links, ...). Anything else aborts without writing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from sqlalchemy import create_engine, text

from tools.content_review.guarded_repair import (
    FIELDS, JSON_FIELDS, _plain, _private_backup, fingerprint, validate_choices,
)

IRT_DIFFICULTY = {"A": -1.0, "B": 0.5, "C": 1.5}
ID_RE = re.compile(r"^[A-Za-z0-9_]{3,60}$")
_norm = lambda s: re.sub(r"[\s$]|\\,", "", str(s or "")).replace("\\dfrac", "\\frac").replace("{,}", ",").lower()


def validate_new_task(row: dict, batch: str) -> None:
    tid = row.get("id")
    if not isinstance(tid, str) or not ID_RE.match(tid):
        raise ValueError(f"bad task id: {tid!r}")
    missing = [k for k in FIELDS if k not in row]
    if missing:
        raise ValueError(f"{tid}: new task must supply every field explicitly; missing {missing}")
    extra = set(row) - set(FIELDS) - {"id", "after_sha256"}
    if extra:
        raise ValueError(f"{tid}: unsupported columns {sorted(extra)}")
    if not row["skill_id"] or not row["question_text"].strip() or not row["correct_answer"].strip():
        raise ValueError(f"{tid}: skill, statement and key are required")
    if row["difficulty"] not in IRT_DIFFICULTY:
        raise ValueError(f"{tid}: difficulty must be A, B or C")
    if row["question_text"] != row["question_latex"] or row["correct_answer"] != row["correct_answer_latex"]:
        raise ValueError(f"{tid}: raw and display statement/key must agree")
    if row["answer_options"] != row["answer_options_latex"]:
        raise ValueError(f"{tid}: raw and display options must agree")
    options = row["answer_options"] or []
    if row["answer_type"] != "multiple_choice":
        raise ValueError(f"{tid}: new tasks with choices must have answer_type multiple_choice")
    if len(options) < 3:
        raise ValueError(f"{tid}: multiple choice needs the key and at least two distractors")
    validate_choices(row)
    for d in row["distractor_meta"]:
        if not str(d.get("error_logic", "")).startswith("Ученик"):
            raise ValueError(f"{tid}: every distractor needs an 'Ученик ...' explanation")
        if d.get("plausibility") is None:
            raise ValueError(f"{tid}: distractor plausibility required")
    if row["is_active"] is not True:
        raise ValueError(f"{tid}: new tasks are inserted active (owner-approved batch)")
    review = (row["tags"] or {}).get("content_review") or {}
    if review.get("batch") != batch:
        raise ValueError(f"{tid}: tags.content_review.batch must equal the manifest batch")


def _existing(conn, ids: list[str], lock: bool) -> dict:
    suffix = " FOR UPDATE" if lock else ""
    rows = conn.execute(text("SELECT * FROM tasks_master WHERE id = ANY(:ids)" + suffix),
                        {"ids": ids}).mappings().all()
    return {r["id"]: _plain(dict(r)) for r in rows}


def _referencing(conn, ids: list[str]) -> list[str]:
    """Rows in ANY table that has a foreign key to tasks_master(id) for these ids."""
    fks = conn.execute(text("""
        SELECT c.conrelid::regclass::text AS tbl, a.attname AS col
        FROM pg_constraint c
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
        WHERE c.contype = 'f' AND c.confrelid = 'tasks_master'::regclass AND array_length(c.conkey, 1) = 1
    """)).all()
    found = []
    for tbl, col in fks:
        n = conn.scalar(text(f"SELECT count(*) FROM {tbl} WHERE {col} = ANY(:ids)"), {"ids": ids})
        if n:
            found.append(f"{tbl}.{col}={n}")
    return found


def _insert(conn, row: dict) -> None:
    cols = ["id"] + list(FIELDS)
    params = {}
    for c in cols:
        v = row[c]
        params[c] = json.dumps(v, ensure_ascii=False) if c in JSON_FIELDS else v
    placeholders = [f"CAST(:{c} AS jsonb)" if c in JSON_FIELDS else f":{c}" for c in cols]
    conn.execute(text(f"INSERT INTO tasks_master ({', '.join(cols)}) VALUES ({', '.join(placeholders)})"), params)


def apply(engine, manifest: dict, *, execute: bool = False, backup: Path | None = None) -> dict:
    batch, rows = manifest["batch"], manifest["new_tasks"]
    ids = [r.get("id") for r in rows]
    if not rows or len(set(ids)) != len(ids):
        raise ValueError("new task ids must be nonempty and unique")
    if manifest.get("student_data_included") not in (False, None):
        raise ValueError("manifest must not include student data")
    for r in rows:
        validate_new_task(r, batch)
        if fingerprint(r) != r.get("after_sha256"):
            raise ValueError(f"{r['id']}: manifest fingerprint mismatch (row edited after the manifest was built)")
    if execute and backup is None:
        raise ValueError("execution requires a private rollback backup path")
    with engine.begin() as conn:
        if not execute:
            conn.execute(text("SET TRANSACTION READ ONLY"))
        else:
            # serialise concurrent executions: the loser sees the winner's rows and reports already_applied
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('guarded_insert_new_tasks'))"))
        present = _existing(conn, ids, execute)
        if present:
            if set(present) == set(ids) and all(fingerprint(present[i]) == r["after_sha256"]
                                                for i, r in zip(ids, rows)):
                return {"batch": batch, "execute": execute, "inserted": [], "already_applied": ids}
            raise ValueError("task id(s) already exist, refusing to insert: " + ", ".join(sorted(present)))
        skills = {r["skill_id"] for r in rows}
        active = {s for (s,) in conn.execute(text(
            "SELECT id FROM knowledge_hierarchy WHERE id = ANY(:s) AND is_active"), {"s": sorted(skills)})}
        if active != skills:
            raise ValueError("unknown or inactive skill(s): " + ", ".join(sorted(skills - active)))
        bank = {_norm(q): t for t, q in conn.execute(text(
            "SELECT id, question_text FROM tasks_master WHERE is_active"))}
        seen = {}
        for r in rows:
            key = _norm(r["question_text"])
            if key in bank:
                raise ValueError(f"{r['id']}: same statement already in the bank ({bank[key]})")
            if key in seen:
                raise ValueError(f"{r['id']}: duplicate statement inside the batch ({seen[key]})")
            seen[key] = r["id"]
        report = {"batch": batch, "execute": execute, "inserted": ids, "already_applied": [],
                  "per_skill": {s: sum(1 for r in rows if r["skill_id"] == s) for s in sorted(skills)}}
        if not execute:
            return report
        _private_backup(backup, {
            "batch": batch, "mode": "insert_new_tasks", "student_data_included": False,
            "inserted": [{"id": r["id"], "after_sha256": r["after_sha256"]} for r in rows],
            "rows": rows,
        })
        for r in rows:
            _insert(conn, r)
        after = _existing(conn, ids, False)
        for r in rows:
            if r["id"] not in after or fingerprint(after[r["id"]]) != r["after_sha256"]:
                raise ValueError(f"{r['id']}: post-insert row differs from manifest; transaction rolled back")
        return report


def rollback(engine, saved: dict, *, execute: bool = False) -> dict:
    pinned = {e["id"]: e["after_sha256"] for e in saved["inserted"]}
    ids = sorted(pinned)
    with engine.begin() as conn:
        if not execute:
            conn.execute(text("SET TRANSACTION READ ONLY"))
        else:
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('guarded_insert_new_tasks'))"))
        present = _existing(conn, ids, execute)
        if not present:
            return {"batch": saved["batch"], "execute": execute, "already_rolled_back": ids}
        for tid, row in present.items():
            if fingerprint(row) != pinned[tid]:
                raise ValueError(f"rollback source drift: {tid}; nothing deleted")
        refs = _referencing(conn, list(present))
        if refs:
            raise ValueError("inserted tasks are referenced elsewhere (" + "; ".join(refs) + "); nothing deleted")
        if execute:
            res = conn.execute(text("DELETE FROM tasks_master WHERE id = ANY(:ids)"), {"ids": sorted(present)})
            if res.rowcount != len(present):
                raise ValueError("unexpected delete count; transaction rolled back")
        return {"batch": saved["batch"], "execute": execute, "deleted": sorted(present),
                "absent": sorted(set(ids) - set(present))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--manifest", type=Path)
    source.add_argument("--rollback", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    # Same rule as guarded_repair: never fall back to a service .env / live database.
    engine = create_engine(os.environ["CONTENT_REPAIR_DATABASE_URL"])
    if args.rollback:
        result = rollback(engine, json.loads(args.rollback.read_text()), execute=args.execute)
    else:
        result = apply(engine, json.loads(args.manifest.read_text()), execute=args.execute, backup=args.backup)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
