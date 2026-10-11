"""Apply a reviewed, in-place bank repair. No new task IDs or pupil writes.

The manifest pins the complete educational source, not just the field being
edited. All rows are locked and checked before the first update. A private,
durable backup is required for execution; dry-run is the default. Rollback
refuses to overwrite subsequent edits or new display attestations.
"""
from __future__ import annotations

import argparse
import copy
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import create_engine, text


FIELDS = (
    "skill_id", "question_text", "question_latex", "question_image_url",
    "answer_type", "correct_answer", "correct_answer_latex", "sympy_solution",
    "answer_options", "answer_options_latex", "difficulty", "irt_discrimination",
    "irt_difficulty", "irt_guessing", "distractor_meta", "is_active", "toc_id",
    "cognitive_load", "verification_status", "source_type", "source_reference",
    "tags", "is_star", "task_category", "latex_status",
)
JSON_FIELDS = {"tags", "distractor_meta", "answer_options", "answer_options_latex"}
PAIRS = (
    ("question_text", "question_latex"),
    ("correct_answer", "correct_answer_latex"),
    ("answer_options", "answer_options_latex"),
)
STALE_TAGS = {
    "sympy_verified", "sympy_confidence", "answer_verify_mode", "reverified_by",
    "answer_gemini_verified", "answer_gemini_candidate", "answer_gemini_flash",
    "distractor_gate_passed", "verification_explanation", "verify_unresolved",
    "verified_by", "smart_verify_status", "answer_llm_prose",
    "sympy_compatible_string", "step_by_step_solution", "answer_format_preserved",
}


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def fingerprint(row: dict) -> str:
    payload = {key: _plain(row.get(key)) for key in FIELDS}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def attestation_patterns(changes: dict) -> list[str]:
    patterns = []
    for keys, pattern in ((PAIRS[0], "question"), (PAIRS[1], "answer"),
                          (PAIRS[2], "option[%"), (("distractor_meta",), "dmeta[%")):
        if any(k in changes for k in keys):
            patterns.append(pattern)
    return patterns


def _attested_unchanged(field: str, patterns: list[str]) -> bool:
    return not any(field.startswith(p[:-1]) if p.endswith("%") else field == p
                   for p in patterns)


def candidate(row: dict, entry: dict, batch: str) -> dict:
    result = copy.deepcopy(row)
    changes = entry["changes"]
    result.update(changes)
    tags = copy.deepcopy(row.get("tags") or {})
    for name in STALE_TAGS:
        tags.pop(name, None)
    if "skill_id" in changes:
        for name in ("mapping_reasoning", "mapping_confidence", "mapping_l3"):
            tags.pop(name, None)
    patterns = attestation_patterns(changes)
    if "latex_attested_fields" in tags:
        tags["latex_attested_fields"] = [f for f in tags["latex_attested_fields"]
                                        if _attested_unchanged(f, patterns)]
    quality = copy.deepcopy(tags.get("content_quality") or {})
    if "latex_attested_fields" in quality:
        quality["latex_attested_fields"] = [f for f in quality["latex_attested_fields"]
                                           if _attested_unchanged(f, patterns)]
    quality.update(status=entry.get("quality_status", "manually_reviewed"),
                   reason=entry["reason"], review_source=batch)
    tags["content_quality"] = quality
    tags["content_review"] = {
        "batch": batch, "before_sha256": entry["before_sha256"],
        "reason": entry["reason"], "evidence": entry["evidence"],
        "changed_fields": sorted(changes), "mode": "in_place_owner_requested",
        "irt_note": "Existing heuristic parameters retained; not empirically recalibrated.",
    }
    result["tags"] = tags
    return result


def validate_entry(entry: dict) -> None:
    if not entry.get("id") or not entry.get("reason") or not entry.get("evidence"):
        raise ValueError("each repair requires ID, reason and mathematical/source evidence")
    changes = entry.get("changes") or {}
    if not changes or set(changes) - (set(FIELDS) - {"tags"}):
        raise ValueError("empty repair or unsupported columns")
    for raw, display in PAIRS:
        if (raw in changes) != (display in changes):
            raise ValueError(f"repair must change {raw} and {display} together")
    if "distractor_meta" in changes:
        for d in changes["distractor_meta"]:
            if not d.get("value") or not d.get("value_latex"):
                raise ValueError("each distractor requires raw and display value")
            explanation = d.get("error_logic")
            if (not explanation or d.get("explanation") != explanation
                    or not d.get("error_logic_latex")
                    or d.get("error_logic_latex") != d.get("explanation_latex")):
                raise ValueError("distractor explanation mirrors must agree")


def validate_choices(row: dict) -> None:
    options = row.get("answer_options") or []
    displays = row.get("answer_options_latex") or []
    if options:
        if not all(isinstance(v, str) and v.strip() for v in options):
            raise ValueError("reviewed options must be nonempty canonical strings")
        if len(options) != len(displays) or len(set(options)) != len(options):
            raise ValueError("options must be unique with parallel display values")
        if len(set(displays)) != len(displays):
            raise ValueError("display options must be distinguishable")
        if options.count(row["correct_answer"]) != 1:
            raise ValueError("correct answer must occur exactly once")
        wrong_values = [d["value"] for d in row.get("distractor_meta") or []]
        if len(wrong_values) != len(set(wrong_values)) or set(wrong_values) != set(options) - {row["correct_answer"]}:
            raise ValueError("every wrong choice requires exactly one explanation")
        for d in row.get("distractor_meta") or []:
            if d["value"] == row["correct_answer"] or d["value"] not in options:
                raise ValueError("distractor must describe a displayed wrong choice")


def _load(conn, ids: list[str], lock: bool) -> list[dict]:
    suffix = " FOR UPDATE" if lock else ""
    rows = conn.execute(text("SELECT * FROM tasks_master WHERE id = ANY(:ids) "
                             "ORDER BY id" + suffix), {"ids": ids}).mappings().all()
    if {r["id"] for r in rows} != set(ids):
        raise ValueError("repair set has missing tasks; refusing partial application")
    return [_plain(dict(r)) for r in rows]


def _attestations(conn, ids: list[str], lock: bool = False) -> list[dict]:
    suffix = " FOR UPDATE" if lock else ""
    return [_plain(dict(r)) for r in conn.execute(text(
        "SELECT * FROM task_latex_display_attestations WHERE task_id = ANY(:ids) "
        "ORDER BY attestation_id" + suffix), {"ids": ids}).mappings().all()]


def _private_backup(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # O_EXCL forbids replacing the only copy of an earlier rollback point.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _update(conn, task_id: str, fields: dict) -> None:
    clauses, parameters = [], {"id": task_id}
    for key, value in fields.items():
        if key not in FIELDS:
            raise ValueError("unsupported update column")
        clauses.append(f"{key} = CAST(:{key} AS jsonb)" if key in JSON_FIELDS else f"{key} = :{key}")
        # SQL NULL must stay SQL NULL (json.dumps(None) would store a JSON null and make rollback inexact).
        parameters[key] = (None if value is None else json.dumps(value, ensure_ascii=False)) if key in JSON_FIELDS else value
    conn.execute(text("UPDATE tasks_master SET " + ", ".join(clauses)
                      + ", updated_at = NOW() WHERE id = :id"), parameters)


def protected_ids(manifest: dict) -> list[str]:
    """Repair IDs the manifest marks as having historical pupil answers."""
    marked = set(manifest.get("historical_protection_required") or [])
    return sorted(e["id"] for e in manifest["repairs"] if e["id"] in marked)


def apply(engine, manifest: dict, *, execute: bool = False, backup: Path | None = None,
          ack_protected: bool = False) -> dict:
    batch, entries = manifest["batch"], manifest["repairs"]
    ids = [e["id"] for e in entries]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("repair IDs must be nonempty and unique")
    protected = protected_ids(manifest)
    if protected and not ack_protected:
        # Checked before any connection use, for dry-run and execute alike.
        raise ValueError("manifest repairs tasks with historical pupil answers "
                         f"({', '.join(protected)}); nothing written. Re-run with "
                         "--ack-protected only after the owner accepted the snapshot impact")
    for entry in entries:
        validate_entry(entry)
    if execute and backup is None:
        raise ValueError("execution requires a private rollback backup path")
    by_id = {e["id"]: e for e in entries}
    with engine.begin() as conn:
        from tools.content_review import knowledge_repair
        # Parent/identity drift is checked before any task or taxonomy write.
        rows = _load(conn, ids, execute)
        kplan = knowledge_repair.plan(conn, manifest)
        added_nodes, activations, new_edges = kplan['added'], kplan['activate'], kplan['edges']
        pending, unchanged = [], []
        for row in rows:
            entry = by_id[row["id"]]
            if fingerprint(row) == entry["after_sha256"]:
                unchanged.append(row["id"])
                continue
            if fingerprint(row) != entry["before_sha256"]:
                raise ValueError(f"source drift: {row['id']}; nothing written")
            after = candidate(row, entry, batch)
            if fingerprint(after) != entry["after_sha256"]:
                raise ValueError("manifest candidate fingerprint mismatch")
            if any(k in entry["changes"] for k in ("answer_options", "correct_answer", "distractor_meta")):
                validate_choices(after)
            pending.append((row, after, entry))
        if pending and (kplan['already_active'] or kplan['edges_present']
                        or kplan['already_updated'] or kplan['already_deactivated']):
            raise ValueError('taxonomy change already present while tasks are pending; nothing written')
        pending_ids = [before["id"] for before, _, _ in pending]
        report = {"batch": batch, "execute": execute,
                  "updated": pending_ids, "already_applied": unchanged}
        if manifest.get('knowledge_nodes'):
            report['knowledge_added'] = [n['id'] for n in added_nodes]
        if 'knowledge_activate' in manifest:
            report['knowledge_activated'] = [n['id'] for n in activations]
        if 'knowledge_update' in manifest:
            report['knowledge_updated'] = [n['id'] for n in kplan['update']]
        if 'knowledge_deactivate' in manifest:
            report['knowledge_deactivated'] = [n['id'] for n in kplan['deactivate']]
        if 'prerequisites' in manifest:
            report['prerequisites_added'] = [[e['skill_id'], e['prerequisite_id']] for e in new_edges]
        if not execute or not pending:
            if execute and (added_nodes or activations or new_edges or kplan['update'] or kplan['deactivate']):
                raise ValueError('applied tasks without required knowledge changes')
            return report
        attestations = _attestations(conn, pending_ids, lock=True)
        links = [_plain(dict(r)) for r in conn.execute(text(
            "SELECT * FROM textbook_tasks WHERE task_id = ANY(:ids) ORDER BY textbook_id, task_id"),
            {"ids": pending_ids}).mappings().all()]
        _private_backup(backup, {
            "batch": batch, "student_data_included": False,
            "before": [before for before, _, _ in pending],
            "after_sha256": {after["id"]: fingerprint(after) for _, after, _ in pending},
            "attestations_before": attestations, "textbook_links": links,
            "revoked_patterns": {e["id"]: attestation_patterns(e["changes"]) for _, _, e in pending},
            "knowledge_added": added_nodes,
            "knowledge_activated": activations,
            "knowledge_updated": kplan['update'],
            "knowledge_deactivated": kplan['deactivate'],
            "prerequisites_added": knowledge_repair.edge_records(new_edges),
        })
        knowledge_repair.insert(conn, added_nodes)
        knowledge_repair.activate(conn, activations)
        knowledge_repair.update(conn, kplan['update'])
        for before, after, entry in pending:
            _update(conn, before["id"], {**entry["changes"], "tags": after["tags"]})
            patterns = attestation_patterns(entry["changes"])
            if patterns:
                conn.execute(text("""
                    UPDATE task_latex_display_attestations
                    SET status='revoked', revoked_at=NOW(), revocation_reason=:reason
                    WHERE task_id=:id AND status='active' AND field_key LIKE ANY(:patterns)
                """), {"id": before["id"], "patterns": patterns, "reason": f"content repair {batch}"})
        knowledge_repair.retire(conn, kplan['deactivate'])
        knowledge_repair.insert_edges(conn, new_edges)
        for row in _load(conn, pending_ids, False):
            if fingerprint(row) != by_id[row["id"]]["after_sha256"]:
                raise ValueError("post-write source mismatch; transaction rolled back")
        knowledge_repair.verify_written(conn, kplan, entries)
        return report


def rollback(engine, saved: dict, *, execute: bool = False) -> dict:
    ids = [r["id"] for r in saved["before"]]
    with engine.begin() as conn:
        from tools.content_review import knowledge_repair
        rows = _load(conn, ids, execute)
        before = {r["id"]: r for r in saved["before"]}
        tasks_restored = all(fingerprint(r) == fingerprint(before[r["id"]]) for r in rows)
        if tasks_restored and knowledge_repair.state_restored(conn, saved):
            return {"batch": saved["batch"], "execute": execute, "already_restored": ids}
        if not tasks_restored:
            for row in rows:
                if fingerprint(row) != saved["after_sha256"][row["id"]]:
                    raise ValueError(f"rollback source drift: {row['id']}; nothing written")
            current = _attestations(conn, ids, lock=execute)
            expected = copy.deepcopy(saved["attestations_before"])
            for a in expected:
                patterns = saved["revoked_patterns"][a["task_id"]]
                if a["status"] == "active" and not _attested_unchanged(a["field_key"], patterns):
                    a["status"] = "revoked"
                    a["revocation_reason"] = f"content repair {saved['batch']}"
                    a["revoked_at"] = None  # transaction time is not a content identity
            for a in current:
                if a["revocation_reason"] == f"content repair {saved['batch']}":
                    a["revoked_at"] = None
            if current != expected:
                raise ValueError("rollback attestation drift; refusing to replace newer review")
        knowledge_repair.check_rollback(conn, saved.get('knowledge_added', []))
        knowledge_repair.check_rollback_activation(conn, saved.get('knowledge_activated', []))
        knowledge_repair.check_rollback_edges(conn, saved.get('prerequisites_added', []))
        knowledge_repair.check_rollback_after_images(conn, saved.get('knowledge_updated', []), 'update')
        knowledge_repair.check_rollback_after_images(conn, saved.get('knowledge_deactivated', []), 'deactivation')
        if execute:
            if not tasks_restored:
                for task_id, row in before.items():
                    _update(conn, task_id, {k: row.get(k) for k in FIELDS})
                for a in saved["attestations_before"]:
                    conn.execute(text("""
                        UPDATE task_latex_display_attestations SET status=:status,
                        revoked_at=:revoked_at, revocation_reason=:revocation_reason
                        WHERE attestation_id=:attestation_id
                    """), {k: a[k] for k in ("status", "revoked_at", "revocation_reason", "attestation_id")})
            knowledge_repair.remove_edges(conn, saved.get('prerequisites_added', []))
            knowledge_repair.unretire(conn, saved.get('knowledge_deactivated', []))
            knowledge_repair.restore_updated(conn, saved.get('knowledge_updated', []))
            knowledge_repair.deactivate(conn, saved.get('knowledge_activated', []))
            knowledge_repair.remove(conn, saved.get('knowledge_added', []))
        return {"batch": saved["batch"], "execute": execute, "restored": ids}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--manifest", type=Path)
    source.add_argument("--rollback", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--ack-protected", action="store_true",
                        help="allow tasks listed in historical_protection_required")
    args = parser.parse_args()
    # Deliberately do not load a service .env or fall back to its live database.
    engine = create_engine(os.environ["CONTENT_REPAIR_DATABASE_URL"])
    if args.rollback:
        result = rollback(engine, json.loads(args.rollback.read_text()), execute=args.execute)
    else:
        result = apply(engine, json.loads(args.manifest.read_text()), execute=args.execute, backup=args.backup,
                       ack_protected=args.ack_protected)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
