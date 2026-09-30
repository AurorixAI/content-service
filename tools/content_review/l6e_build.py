import json, sys, psycopg2
sys.path.insert(0, "/audit")
from latexsym import fix, canon
h = json.load(open("/audit/lint_latex.json"))
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex, answer_options_latex, distractor_meta FROM tasks_master WHERE id = ANY(%s) AND is_active", (list(h),))
spec, diffs = {}, []
for tid, ql, kl, aol, dm in c.fetchall():
    f = {}
    for col, val in (("question_latex", ql), ("correct_answer_latex", kl)):
        nv = fix(val)
        if nv != val: f[col] = nv; diffs.append((tid, col, val, nv))
    if isinstance(aol, list):
        new = [dict(o, text=fix(o.get("text"))) if isinstance(o, dict) else fix(o) for o in aol]
        if new != aol: f["answer_options_latex"] = new; diffs += [(tid, "opt", a, b) for a, b in zip(aol, new) if a != b]
    if isinstance(dm, list):
        new = [dict(d, value_latex=fix(d.get("value_latex"))) if isinstance(d, dict) and d.get("value_latex") else d for d in dm]
        if new != dm: f["distractor_meta"] = new; diffs += [(tid, "dm", a.get("value_latex"), b.get("value_latex")) for a, b in zip(dm, new) if a != b]
    if f:
        spec[tid] = {"why": "обозначения в LaTeX-колонках отображения приведены к стандартной записи (sin → \\sin, tg → \\operatorname{tg}, ° → ^{\\circ}, π → \\pi, ∈ → \\in, <= → \\le и т. п.); смысл не меняется, сырые колонки не тронуты",
                     "source": "L6e, 25.09", "fields": f, "latex_symbol_only": True}
bad = [(t, col) for t, col, a, b in diffs if canon(a) != canon(b)]
print("tasks:", len(spec), "changed strings:", len(diffs), "canon mismatches:", len(bad), bad[:10])
json.dump(spec, open("/audit/restore_J_L6e.json", "w"), ensure_ascii=False, indent=1)
json.dump(diffs, open("/audit/l6e_diffs.json", "w"), ensure_ascii=False, indent=1)
