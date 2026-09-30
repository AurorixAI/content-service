# -*- coding: utf-8 -*-
"""Build a manual compound-task split from specs/split_<name>.py (dict SPLIT).

A multi-part task (answer with а) б) в) ...) becomes one task per part, following the
bank's existing split convention: child id = <parent>.<N>, tags split_from / compound_split_ok.
Each part: q (statement, raw = LaTeX), k (key), d = [(wrong value, "Ученик ..." why), ...].
Children copy the parent's curriculum metadata; model-era verification tags, attestations
and IRT parameters (which described the compound item) are not copied.

Writes split_J_<name>.json (rows to insert + parents to retire), nested_after_state.json
(for grade_state.py) and kx_split_<name>.json (every string, for katex_check.js).
Prints only problems.  Usage: split_build.py <name>
"""
import importlib.util, json, re, sys
import psycopg2

name = sys.argv[1]
m = importlib.util.spec_from_file_location("cfg", f"/audit/specs/split_{name}.py"); cfg = importlib.util.module_from_spec(m); m.loader.exec_module(cfg)
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
BAD = "\x07\r\x0c\t\x08"
KEEP_TAGS = ("paragraph", "exercise", "category", "marker", "mapping_l3", "mapping_confidence", "mapping_reasoning")
nrm = lambda v: re.sub(r"\s|\$", "", str(v or "")).replace("\\dfrac", "\\frac").replace("{,}", ",")


def dm(v, why):
    return {"value": v, "value_latex": v, "error_type": "manual_review", "plausibility": 0.6,
            "error_logic": why, "error_logic_latex": why, "explanation": why, "explanation_latex": why}


out = {"new": {}, "retire": {}}
state, kx, problems = [], {}, 0
for parent, e in cfg.SPLIT.items():
    c.execute("SELECT answer_type, answer_options, tags FROM tasks_master WHERE id=%s AND is_active", (parent,))
    r = c.fetchone()
    if not r: print("PARENT NOT ACTIVE", parent); problems += 1; continue
    atype, ao, tags = r
    parts = e["parts"]
    ids = []
    for n, p in enumerate(parts, 1):
        cid = f"{parent}.{n}"
        c.execute("SELECT 1 FROM tasks_master WHERE id=%s", (cid,))
        pr = []
        if c.fetchone(): pr.append("id exists")
        q, k, ds = p["q"], p["k"], p["d"]
        vals = [v for v, _ in ds]
        if len(ds) < 3 and not p.get("yesno"): pr.append("few")
        if p.get("yesno") and len(ds) < 2 and k.strip() not in ("да", "нет"): pr.append("few-binary")  # diag builds options only for да/нет with one distractor
        if any(nrm(v) == nrm(k) for v in vals): pr.append("d==key")
        if len({nrm(v) for v in vals}) != len(vals): pr.append("dupvals")
        for s in [q, k] + [x for pair in ds for x in pair]:
            if any(ch in s for ch in BAD): pr.append("badchar")
            if s.count("$") % 2: pr.append("odd$:" + s[:50])
            if re.search(r"\\n(?![A-Za-z])", s): pr.append("literal \\n:" + s[:50])
        for _, why in ds:
            if not why.startswith("Ученик"): pr.append("why!Ученик:" + why[:40])
        if pr: problems += 1; print(cid, pr)
        ctags = {t: tags[t] for t in KEEP_TAGS if isinstance(tags, dict) and t in tags}
        ctags.update({"split_from": parent, "compound_split_ok": True, "split_part": n,
                      "split_batch": name, "split_source": "manual-split-2026-09-30",
                      "answer_verify_mode": "manual_verified"})
        dmeta = [dm(v, w) for v, w in ds]
        opts = ([k] + vals) if (isinstance(ao, list) and ao) else None
        row = {"question_text": q, "question_latex": q, "correct_answer": k, "correct_answer_latex": k,
               "distractor_meta": dmeta, "answer_options": opts, "answer_options_latex": opts, "tags": ctags}
        out["new"][cid] = {"parent": parent, "fields": row}
        state.append({"id": cid, "answer_type": atype, **{f: row[f] for f in ("question_text", "question_latex", "correct_answer", "correct_answer_latex", "answer_options", "answer_options_latex", "distractor_meta")}})
        kx[cid] = [q, k] + [x for pair in ds for x in pair]
        ids.append(cid)
    out["retire"][parent] = {"why": e["why"], "children": ids}

json.dump(out, open(f"/audit/split_J_{name}.json", "w"), ensure_ascii=False, indent=1)
json.dump(state, open("/audit/nested_after_state.json", "w"), ensure_ascii=False)
json.dump(kx, open(f"/audit/kx_split_{name}.json", "w"), ensure_ascii=False)
print(f"parents {len(out['retire'])} children {len(out['new'])} problems {problems}")
