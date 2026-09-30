"""Owner-approved restoration of task content from a verified source (dry-run by default).

Spec: {task_id: {"why", "source", "expect": <LaTeX of the independently computed
answer>, "fields": {<column>: <new value>}}}. Only listed columns change.

Gates per task (nothing is written for a task that fails any):
* the key equals `expect` numerically (SymPy, several random points);
* stored options: the key is among them exactly once, no duplicates, and the
  LaTeX list is parallel;
* no distractor value equals the key;
* every string of every changed field renders with KaTeX.
Writes: previous values under tags.content_repair::<batch>; attestations of
changed raw fields revoked.
"""
import argparse
import re
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app/scripts")
sys.path.insert(0, "/audit")
from sqlalchemy import create_engine, text  # noqa: E402

from backfill_latex_deepseek import validate_with_katex  # noqa: E402
import nested_verify2 as nv  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--batch-id", required=True)
parser.add_argument("--spec", required=True)
parser.add_argument("--report", required=True)
parser.add_argument("--execute", action="store_true")
args = parser.parse_args()

FIELDS = nv.FIELDS
RAW_TO_ATTESTED = {"question_text": ["question"], "correct_answer": ["answer"],
                   "answer_options": ["option[%"], "distractor_meta": ["dmeta[%"]}
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
TAG = f"content_repair::{args.batch_id}"
SPEC = json.load(open(args.spec))


def strings(value, path=""):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from strings(v, f"{path}[{i}]")
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from strings(v, f"{path}.{k}")


def blocks_equal(a: str, b: str) -> bool:
    ba = nv.blocks(a) or [a]
    bb = nv.blocks(b) or [b]
    return len(ba) == len(bb) and all(nv.equal(x, y) for x, y in zip(ba, bb))


engine = create_engine(os.environ["DATABASE_URL"])
conn = engine.connect()
trans = conn.begin()
report = {"batch": args.batch_id, "ok": [], "blocked": []}
revoked_total = 0
try:
    rows = conn.execute(text(f"SELECT id, is_active, {', '.join(FIELDS)} FROM tasks_master "
                             "WHERE id = ANY(:ids) ORDER BY id FOR UPDATE"),
                        {"ids": sorted(SPEC)}).mappings().fetchall()
    missing = sorted(set(SPEC) - {r["id"] for r in rows})
    if missing:
        raise SystemExit(f"SAFETY ABORT: missing tasks {missing}")
    for row in rows:
        tid, spec = row["id"], SPEC[row["id"]]
        new = {k: spec["fields"].get(k, row[k]) for k in FIELDS}
        changed = [k for k in FIELDS if new[k] != row[k]]
        problems = []
        if not row["is_active"]:
            problems.append("inactive")
        key = new["correct_answer"] or ""
        if spec.get("latex_notation_only"):
            # Display-only notation change (decimal point -> decimal comma, list separator ", " -> "; ").
            # Only LaTeX display columns may change, and each changed string must be identical to the
            # old one after undoing that notation. Raw columns used for grading stay untouched.
            def _undo(s):
                s = str(s if s is not None else "").replace("{,}", ".")
                return re.sub(r"\s*;\s*", ", ", s)
            def _latex_view(v, field):
                if field == "distractor_meta":
                    return [(d.get("value"), d.get("text"), d.get("error_logic"), d.get("explanation")) if isinstance(d, dict) else d for d in (v or [])]
                return v
            allowed = {"correct_answer_latex", "answer_options_latex", "distractor_meta"}
            if set(changed) - allowed:
                problems.append(f"latex_notation_only_touches:{sorted(set(changed) - allowed)}")
            if "distractor_meta" in changed and _latex_view(new["distractor_meta"], "distractor_meta") != _latex_view(row["distractor_meta"], "distractor_meta"):
                problems.append("latex_notation_only_changed_non_latex_distractor_fields")
            for k in changed:
                for (p1, a), (p2, b) in zip(strings(new[k]), strings(row[k])):
                    if a != b and _undo(a) != _undo(b):
                        problems.append(f"latex_notation_only_meaning_changed:{k}{p1}")
            notation_ok = True
        elif spec.get("latex_symbol_only"):
            # Display-only symbol normalisation (sin -> \sin, ° -> ^{\circ}, π -> \pi, <= -> \le ...). Only LaTeX display
            # columns may change; every changed string must be equal to the old one in latexsym.canon form.
            from latexsym import canon as _canon
            allowed = {"question_latex", "correct_answer_latex", "answer_options_latex", "distractor_meta"}
            if set(changed) - allowed:
                problems.append(f"latex_symbol_only_touches:{sorted(set(changed) - allowed)}")
            _view = lambda v: [(d.get("value"), d.get("text"), d.get("error_logic"), d.get("explanation")) if isinstance(d, dict) else d for d in (v or [])]
            if "distractor_meta" in changed and _view(new["distractor_meta"]) != _view(row["distractor_meta"]):
                problems.append("latex_symbol_only_changed_non_latex_distractor_fields")
            for k in changed:
                for (p1, a), (p2, b) in zip(strings(new[k]), strings(row[k])):
                    if a != b and _canon(a) != _canon(b):
                        problems.append(f"latex_symbol_only_meaning_changed:{k}{p1}")
            notation_ok = True
        elif spec.get("latex_display_manual"):
            # Hand-made display fixes (each checked against the raw value, see spec why); raw columns must stay untouched.
            allowed = {"question_latex", "correct_answer_latex", "answer_options_latex", "distractor_meta"}
            if set(changed) - allowed:
                problems.append(f"latex_display_manual_touches:{sorted(set(changed) - allowed)}")
            _view = lambda v: [(d.get("value"), d.get("text"), d.get("error_logic"), d.get("explanation")) if isinstance(d, dict) else d for d in (v or [])]
            if "distractor_meta" in changed and _view(new["distractor_meta"]) != _view(row["distractor_meta"]):
                problems.append("latex_display_manual_changed_non_latex_distractor_fields")
            notation_ok = True
        else:
            notation_ok = False
        if notation_ok:
            pass
        elif spec.get("key_unchanged"):
            # notation/question repair only: the key must stay exactly as it was
            if new["correct_answer"] != row["correct_answer"] or new["correct_answer_latex"] != row["correct_answer_latex"]:
                problems.append("key_changed_in_key_unchanged_spec")
        elif "expect_text" in spec:
            # Answers SymPy cannot read ("Верно", "x = \\pi/4", "0,05 %") were derived by
            # hand (see the spec's why); the key must be exactly that text.
            if key != spec["expect_text"] or (new["correct_answer_latex"] or key) != spec["expect_text"]:
                problems.append(f"key_differs_from_expected_text:{spec['expect_text']}")
        else:
            try:
                if not blocks_equal(key, spec["expect"]):
                    problems.append(f"key_differs_from_expected:{spec['expect']}")
                if new["correct_answer_latex"] and not blocks_equal(new["correct_answer_latex"], spec["expect"]):
                    problems.append("key_latex_differs_from_expected")
            except Exception as exc:
                problems.append(f"key_parse:{type(exc).__name__}")
        # option / distractor gates apply when the key or the options change; a question-only
        # repair (key_unchanged) must not be blocked by older option notation issues
        touches_options = (not notation_ok) and any(k in changed for k in ("correct_answer", "answer_options", "answer_options_latex", "distractor_meta"))
        for o in (new["answer_options"] or []) if touches_options else []:
            if isinstance(o, dict) and bool(o.get("is_correct")) != (o.get("text") == key):
                problems.append(f"is_correct_flag_disagrees_with_key:{o.get('text')}")
        opts = new["answer_options"] or []
        if opts and touches_options:
            texts = [o.get("text") if isinstance(o, dict) else o for o in opts]
            if texts.count(key) != 1:
                problems.append("key_not_exactly_once_among_options")
            if len(set(texts)) != len(texts):
                problems.append("duplicate_options")
            if len(opts) != len(new["answer_options_latex"] or []):
                problems.append("options_latex_not_parallel")
        verified = set(spec.get("distinct_verified", {}))  # values checked by hand as != key (see spec derivation)
        for d in (new["distractor_meta"] or []) if touches_options else []:
            if isinstance(d, dict) and (d.get("value") or d.get("text") or "") in verified:
                continue
            if isinstance(d, dict) and (d.get("value") or "") == key:
                problems.append(f"distractor_equals_key:{d.get('value')}")
                continue
            try:
                if isinstance(d, dict) and blocks_equal(d.get("value") or "", key):
                    problems.append(f"distractor_equals_key:{d.get('value')}")
            except Exception:
                pass
        for k in changed:
            for path, s in strings(new[k]):
                ok, err = validate_with_katex(s)
                if not ok:
                    problems.append(f"{k}{path}:katex:{(err or '')[:80]}")
        if problems:
            report["blocked"].append({"id": tid, "problems": problems})
            continue

        repair = {"batch": args.batch_id, "at": NOW, "reason": "restored_from_verified_source",
                  "rewrite_why": spec["why"], "source": spec["source"],
                  "by": "claude-manual-review", "approved_by": "product-owner-chat-2026-09-23",
                  "previous": {k: row[k] for k in changed}}
        revoke_keys = [p for k in changed for p in RAW_TO_ATTESTED.get(k, [])]
        revoked = 0
        for pattern in revoke_keys:
            res = conn.execute(text("""
                UPDATE task_latex_display_attestations
                SET status = 'revoked', revoked_at = now(), revocation_reason = :reason
                WHERE task_id = :id AND status = 'active' AND field_key LIKE :pattern"""),
                {"id": tid, "pattern": pattern, "reason": f"raw source changed by content repair {args.batch_id}"})
            revoked += res.rowcount
        revoked_total += revoked
        conn.execute(text("""
            UPDATE tasks_master SET
              question_text = :qt, question_latex = :ql,
              correct_answer = :ca, correct_answer_latex = :cal,
              answer_options = CAST(:ao AS jsonb), answer_options_latex = CAST(:aol AS jsonb),
              distractor_meta = CAST(:dm AS jsonb),
              tags = COALESCE(tags, '{}'::jsonb) || CAST(:patch AS jsonb), updated_at = now()
            WHERE id = :id"""), {
            "id": tid, "qt": new["question_text"], "ql": new["question_latex"],
            "ca": new["correct_answer"], "cal": new["correct_answer_latex"],
            "ao": None if new["answer_options"] is None else json.dumps(new["answer_options"], ensure_ascii=False),
            "aol": None if new["answer_options_latex"] is None else json.dumps(new["answer_options_latex"], ensure_ascii=False),
            "dm": None if new["distractor_meta"] is None else json.dumps(new["distractor_meta"], ensure_ascii=False),
            "patch": json.dumps({TAG: repair}, ensure_ascii=False)})
        if revoke_keys:
            conn.execute(text("""
                UPDATE tasks_master SET tags = jsonb_set(tags, '{latex_attested_fields}',
                  COALESCE((SELECT jsonb_agg(f) FROM jsonb_array_elements_text(tags->'latex_attested_fields') f
                            WHERE NOT (f = ANY(:exact) OR f LIKE ANY(:likes))), '[]'::jsonb))
                WHERE id = :id AND tags ? 'latex_attested_fields'"""), {
                "id": tid, "exact": [p for p in revoke_keys if "%" not in p],
                "likes": [p for p in revoke_keys if "%" in p]})
        report["ok"].append({"id": tid, "fields": changed, "revoked": revoked})

    report["revoked_attestations"] = revoked_total
    print(f"tasks: {len(rows)}  ok: {len(report['ok'])}  blocked: {len(report['blocked'])}  revoked attestations: {revoked_total}")
    for b in report["blocked"]:
        print("BLOCKED", b["id"], b["problems"][:4])
    json.dump(report, open(args.report, "w"), ensure_ascii=False, indent=1)
    if report["blocked"]:
        trans.rollback()
        raise SystemExit("ABORT: blocked tasks present; nothing written")
    if args.execute:
        trans.commit()
        print(f"COMMITTED {len(report['ok'])} tasks")
    else:
        trans.rollback()
        print(f"[DRY RUN] {len(report['ok'])} tasks validated; rolled back, nothing written")
except BaseException:
    if trans.is_active:
        trans.rollback()
    raise
finally:
    conn.close()
