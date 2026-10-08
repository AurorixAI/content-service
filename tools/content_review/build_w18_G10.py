"""Build manifest n01-2026-10-08-w18-G10 (grade-10 skill remapping wave). Reads the local DB only (SELECT).

Inputs (tools/content_review/audit/f1g10):
  map_G10_part_01..23.jsonl + overrides_G10.jsonl   final mapping of 2 651 tasks ("NULL" = no suitable skill)
  verify_G10_map.jsonl                              independent check; its single "weak" item -> NULL
  new_skills_G10.json, new_skills_G10_extra.json    new L4 nodes (decision "new"); "existing" entries need no node

Rules: a task may end with skill_id NULL only if it has a toc_id (exam-only by project policy); a task without
toc_id keeps its current skill.  New nodes that end with <5 tasks are not created (tasks go to the closest skill).
Tasks with identical normalized text end on the same skill (majority, then confidence).

Usage (from content-service):
  CONTENT_REPAIR_DATABASE_URL=... python3 -m tools.content_review.build_w18_G10
Deterministic: the same DB state and inputs give a byte-identical manifest.
"""
from __future__ import annotations

import collections
import glob
import json
import os
import re
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

from tools.content_review import guarded_repair as gr

BATCH = "n01-source-repair-2026-10-08-w18-G10"
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/content_repairs/n01-2026-10-08-w18-G10.json"
AUDIT = Path(__file__).resolve().parent / "audit/f1g10"
LOG = AUDIT / "w18_G10_log.json"
NODE_FIELDS = ("id", "level", "parent_id", "name", "name_ru", "description", "assessed_ability",
               "class_level_start", "class_level_end", "importance", "sequence_order",
               "cognitive_type", "is_active")
MIN_NEW = 5
# independent check, single "weak" item: conceptual statement about extrema, no suitable skill -> NULL (has toc_id)
VERIFY_NULL = {"G10_TB_§39_39_16_1"}


def read_jsonl(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def norm(s):
    s = (s or "").lower().replace("{,}", ",").replace("\\left", "").replace("\\right", "")
    s = s.replace("\\,", "").replace("\\!", "").replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
    s = re.sub(r"[\s$]+", "", s).replace("\\text", "").replace("\\mathrm", "")
    return re.sub(r"[^0-9a-zа-яё\\^_{}=+\-*/()<>|]", "", s)


def main() -> None:
    engine = create_engine(os.environ["CONTENT_REPAIR_DATABASE_URL"])
    mapping, part_of = {}, {}
    for f in sorted(glob.glob(str(AUDIT / "map_G10_part_*.jsonl"))):
        for r in read_jsonl(f):
            mapping[r["id"]] = r
            part_of[r["id"]] = Path(f).stem.replace("map_G10_", "")
    for r in read_jsonl(AUDIT / "overrides_G10.jsonl"):
        if r["id"] not in mapping:
            raise SystemExit("override for unknown task " + r["id"])
        mapping[r["id"]].update(r)
        part_of[r["id"]] += "+overrides"
    verdict = {r["id"]: r for r in read_jsonl(AUDIT / "verify_G10_map.jsonl")}
    weak = {i for i, v in verdict.items() if v["verdict"] == "weak"}
    assert weak == VERIFY_NULL, weak
    for i in weak:
        mapping[i]["to"] = "NULL"
    for r in mapping.values():
        if r["to"] == "NULL":
            r["to"] = None
    news = json.load(open(AUDIT / "new_skills_G10.json", encoding="utf-8")) + \
        json.load(open(AUDIT / "new_skills_G10_extra.json", encoding="utf-8"))
    new_def = {x["target"]: x for x in news if x["decision"] == "new"}

    with engine.connect() as conn:
        K = {r["id"]: dict(r) for r in conn.execute(text("SELECT * FROM knowledge_hierarchy")).mappings()}
        T = {r["id"]: dict(r) for r in conn.execute(text(
            "SELECT id, skill_id, toc_id, question_text, question_latex, question_image_url "
            "FROM tasks_master WHERE is_active")).mappings()}
        missing = [i for i in mapping if i not in T]
        if missing:
            raise SystemExit("wave tasks missing/inactive: %s" % missing[:5])
        scope = {i for i in T if i.startswith("G10") or (T[i]["skill_id"] or "").startswith("G10")} | set(mapping)
        cur = {i: T[i]["skill_id"] for i in scope}
        for i in mapping:
            if cur[i] != mapping[i]["from"]:
                raise SystemExit("source skill drift: %s" % i)
        tgt = dict(cur)
        conf = {i: 0.0 for i in scope}
        why = {i: ("keep", "") for i in scope}
        for i, r in mapping.items():
            tgt[i] = r["to"]
            conf[i] = float(r.get("confidence") or 0)
            tag = "verify-weak-to-NULL" if i in weak else ("verify-" + verdict[i]["verdict"] if i in verdict else "unverified")
            why[i] = ("map", "%s; %s; %s" % (part_of[i], r.get("why") or "", tag))
        # NULL only with toc_id: a task without toc_id keeps its current skill
        no_toc_null = [i for i in mapping if tgt[i] is None and T[i]["toc_id"] is None]
        for i in no_toc_null:
            tgt[i] = cur[i]
            why[i] = ("keep", "NULL not allowed without toc_id")

        nodes_def = {}
        for sid, x in new_def.items():
            n = {k: x["node"][k] for k in NODE_FIELDS}
            assert n["id"] == sid and sid not in K and K[n["parent_id"]]["is_active"] and K[n["parent_id"]]["level"] == "L3", sid
            assert not [j for j in K if K[j]["parent_id"] == n["parent_id"] and K[j]["sequence_order"] == n["sequence_order"]], sid
            nodes_def[sid] = n
        kept_new = set(nodes_def)
        dropped = {}

        def is_valid(s):
            return s is not None and (s in kept_new or (s in K and K[s]["is_active"]))

        # identical text groups (union over question_text / question_latex, same image)
        parent = {}

        def find(a):
            while parent.setdefault(a, a) != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        keymap = collections.defaultdict(list)
        for i in sorted(scope):
            img = T[i]["question_image_url"] or ""
            for fld in ("question_text", "question_latex"):
                n = norm(T[i][fld] if T[i][fld] else T[i]["question_text"])
                if len(n) >= 12:
                    keymap[(n, img)].append(i)
        for ids in keymap.values():
            for j in ids[1:]:
                parent[find(j)] = find(ids[0])
        comps = collections.defaultdict(list)
        for i in sorted(scope):
            if i in parent:
                comps[find(i)].append(i)
        groups = sorted(sorted(v) for v in comps.values() if len(v) > 1)
        changed_consistency = {}

        def consistency():
            changed = 0
            for g in groups:
                votes = collections.Counter(tgt[i] for i in g if is_valid(tgt[i]))
                if len({tgt[i] for i in g}) == 1 or not votes:
                    continue
                top = max(votes.values())
                cands = [s for s, v in votes.items() if v == top]
                if len(cands) > 1:
                    cands.sort(key=lambda s: (max([conf[i] for i in g if tgt[i] == s and why[i][0] != "keep"] or [0.0]),
                                              -sum(1 for t in tgt.values() if t == s), s), reverse=True)
                win = cands[0]
                for i in g:
                    if tgt[i] != win:
                        changed_consistency.setdefault(i, []).append((tgt[i], win))
                        tgt[i] = win
                        if why[i][0] in ("keep", "map"):
                            why[i] = ("consistency", why[i][1])
                        changed += 1
            return changed

        for _round in range(10):
            cnt = collections.Counter(tgt.values())
            small = [s for s in sorted(kept_new) if cnt.get(s, 0) < MIN_NEW]
            for s in small:
                dest = next((a for a in new_def[s]["alt_targets"] if is_valid(a)), None)
                if dest is None:
                    raise SystemExit("new node %s has %d tasks (<%d), no alt target" % (s, cnt.get(s, 0), MIN_NEW))
                kept_new.discard(s)
                dropped[s] = (dest, cnt.get(s, 0))
                for i in scope:
                    if tgt[i] == s:
                        tgt[i] = dest
                        why[i] = ("merge", s)
            ch = consistency()
            if not small and not ch:
                break
        else:
            raise SystemExit("did not converge")
        nodes_def = {s: nodes_def[s] for s in kept_new}
        full_cnt = collections.Counter(tgt[i] if i in scope else t["skill_id"] for i, t in T.items())
        for s in kept_new:
            assert full_cnt[s] >= MIN_NEW, s

        knowledge_nodes = [nodes_def[s] for s in sorted(kept_new)]
        names = {s: K[s]["name_ru"] for s in K}
        names.update({s: n["name_ru"] for s, n in nodes_def.items()})

        def nm(s):
            return "«%s» (%s)" % (names.get(s, "?"), s) if s else "без навыка (NULL, есть toc_id)"

        ids = sorted(i for i in scope if tgt[i] != cur[i])
        rows = {r["id"]: r for r in gr._load(conn, ids, False)}
        repairs = []
        for i in ids:
            row, old, new = rows[i], cur[i], tgt[i]
            cat, det = why[i]
            head = "перепривязка навыка %s → %s" % (nm(old), nm(new))
            if cat == "map":
                part, _, rest = det.partition("; ")
                w, _, tag = rest.rpartition("; ")
                reason = "%s: %s" % (head, w or "по содержанию задачи")
                ev = ("Волна w18 (10 класс), независимая разметка %s (confidence %.2f); проверка verify_G10_map: %s. "
                      % (part, conf[i], tag))
                if new is None:
                    ev += "Подходящего активного навыка нет; у задачи есть toc_id, поэтому она остаётся доступной для экзаменов. "
            elif cat == "merge":
                reason = head + ": новый навык %s набрал <%d задач и не создаётся" % (det, MIN_NEW)
                ev = "Правило волны w18: новый навык с <%d задач не создаётся. " % MIN_NEW
            else:
                reason = head + ": задачи с одинаковым условием должны относиться к одному навыку"
                ev = "Совпадающее (нормализованное) условие у нескольких задач; выбран навык большинства. "
            e = {"id": i, "before_sha256": gr.fingerprint(row), "reason": reason,
                 "evidence": ev + "Целевой навык активен после волны. Меняется только skill_id; условие, ключ и дистракторы не тронуты.",
                 "changes": {"skill_id": new}}
            gr.validate_entry(e)
            e["after_sha256"] = gr.fingerprint(gr.candidate(row, e, BATCH))
            repairs.append(e)

        active_after = {s for s, k in K.items() if k["is_active"]} | set(kept_new)
        bad_inactive = sorted(i for i in T if (tgt[i] if i in scope else T[i]["skill_id"]) is not None
                              and (tgt[i] if i in scope else T[i]["skill_id"]) not in active_after)
        null_no_toc = sorted(i for i in T if (tgt[i] if i in scope else T[i]["skill_id"]) is None and T[i]["toc_id"] is None)
        null_wave = sorted(i for i in ids if tgt[i] is None)
        l4 = sorted(s for s in active_after if s.startswith("G10_S") and
                    (K[s]["level"] if s in K else nodes_def[s]["level"]) == "L4")
        empty = [s for s in l4 if full_cnt.get(s, 0) == 0]

    manifest = {"batch": BATCH, "mode": "in_place_owner_requested",
                "source_checked_at": "2026-10-08T00:00:00Z", "student_data_included": False,
                "knowledge_allow_active": True, "knowledge_nodes": knowledge_nodes, "repairs": repairs}
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    LOG.write_text(json.dumps({
        "consistency_groups": len(groups),
        "consistency_changes": {i: v for i, v in sorted(changed_consistency.items())},
        "dropped_new_nodes": dropped, "null_wave": null_wave, "kept_without_toc": no_toc_null,
        "empty_g10_l4": empty,
        "new_node_task_counts": {s: full_cnt[s] for s in sorted(kept_new)},
    }, ensure_ascii=False, indent=1) + "\n")
    cat_cnt = collections.Counter(why[i][0] for i in ids)
    print(OUT)
    print("repairs", len(repairs), dict(cat_cnt), "-> NULL", len(null_wave), "| nodes new", len(knowledge_nodes),
          {s: full_cnt[s] for s in sorted(kept_new)}, "dropped(<5)", dropped)
    print("consistency groups", len(groups), "changed tasks", len(changed_consistency), "| NULL kept (no toc_id)", len(no_toc_null))
    print("CHECK active tasks on inactive skills (bank-wide):", len(bad_inactive), bad_inactive[:5])
    print("CHECK active tasks with NULL skill and NULL toc_id:", len(null_no_toc), null_no_toc[:5])
    print("CHECK empty active G10 L4 (%d): %s" % (len(empty), ", ".join(empty)))
    if bad_inactive or null_no_toc:
        sys.exit(2)


if __name__ == "__main__":
    main()
