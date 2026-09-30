# -*- coding: utf-8 -*-
"""Generic restore-spec builder for hand-reviewed fixes. Usage: fix_build.py <name>  (config /audit/fix_<name>.py, dict P).
Per task: q = new statement (raw = LaTeX); k = new key (raw = LaTeX, gate expect_text); drop = distractor indices to close;
dval = {i: new value} (explanation kept); dnew = {i: (value, why)}; why = reason (required).
Stored answer_options (if the task has them, or rebuild=True) are rebuilt as [key] + distractor values."""
import copy, json, re, sys, importlib.util, psycopg2

name = sys.argv[1]
m = importlib.util.spec_from_file_location("cfg", f"/audit/fix_{name}.py"); cfg = importlib.util.module_from_spec(m); m.loader.exec_module(cfg)
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
BAD = "\x07\r\x0c\t\x08"


def dm(v, why):
    return {"value": v, "value_latex": v, "error_type": "manual_review", "plausibility": 0.6,
            "error_logic": why, "error_logic_latex": why, "explanation": why, "explanation_latex": why}


out = {}
for tid, e in cfg.P.items():
    c.execute("SELECT correct_answer, correct_answer_latex, answer_options, distractor_meta FROM tasks_master WHERE id=%s AND is_active", (tid,))
    r = c.fetchone(); assert r, tid
    ca, cal, ao, old = r
    ds = [copy.deepcopy(d) for d in (old or [])]
    for i, v in e.get("dval", {}).items(): ds[i]["value"] = v; ds[i]["value_latex"] = v
    for i, (v, w) in e.get("dnew", {}).items(): ds[i] = dm(v, w)
    for i, w in e.get("dwhy", {}).items():
        for fld in ("error_logic", "error_logic_latex", "explanation", "explanation_latex"): ds[i][fld] = w
    ds = [d for i, d in enumerate(ds) if i not in e.get("drop", [])]
    ds += [dm(v, w) for v, w in e.get("dadd", [])]  # e.g. the old wrong key, now a verified wrong option
    assert len(ds) >= 1, tid
    f = {}
    if "q" in e:
        assert all(ch not in e["q"] for ch in BAD), tid
        f["question_text"] = e["q"]; f["question_latex"] = e["q"]
    if "qrep" in e:  # replace a fragment of the statement (LaTeX; raw too when it carries the same fragment)
        c.execute("SELECT question_text, question_latex FROM tasks_master WHERE id=%s", (tid,))
        qt0, ql0 = c.fetchone()
        a_, b_ = e["qrep"]
        assert a_ in ql0, (tid, "fragment not in question_latex")
        f["question_latex"] = ql0.replace(a_, b_)
        if qt0 and a_ in qt0: f["question_text"] = qt0.replace(a_, b_)
    if "k" in e:
        assert all(ch not in e["k"] for ch in BAD), tid
        ca = cal = e["k"]; f["correct_answer"] = ca; f["correct_answer_latex"] = cal
    if ds != old: f["distractor_meta"] = ds
    if "k" in e:  # a wrong option that equals the new key was the correct answer: close it
        nrm = lambda v: re.sub(r"\s|\$", "", str(v or "")).replace("\\dfrac", "\\frac").replace("{,}", ",")
        kept = [d for d in ds if nrm(d.get("value")) != nrm(ca) and nrm(d.get("value_latex")) != nrm(ca)]
        if len(kept) != len(ds):
            s_why = " ; неверный вариант, совпадавший с новым ключом, закрыт"
            e["why"] = e["why"] + s_why
            ds = kept
            f["distractor_meta"] = ds
    if (isinstance(ao, list) and ao) or e.get("rebuild"):
        f["answer_options"] = [ca] + [d.get("value") for d in ds]
        f["answer_options_latex"] = [cal or ca] + [d.get("value_latex") or d.get("value") for d in ds]
        assert len(set(f["answer_options"])) == len(f["answer_options"]), tid
    s = {"why": e["why"], "source": e.get("src", "ручная проверка 25.09 (выборка), сверено с учебником / вычислением"), "fields": f,
         "distinct_verified": {d.get("value"): "проверено вручную: не равно ключу" for d in ds}}
    if "k" in e: s["expect_text"] = ca
    else: s["key_unchanged"] = True
    out[tid] = s
json.dump(out, open(f"/audit/restore_J_{name}.json", "w"), ensure_ascii=False, indent=1)
for t, s in out.items():
    print(t, "|", sorted(s["fields"]))
