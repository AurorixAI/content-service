# -*- coding: utf-8 -*-
"""L6g: inside $...$ of display columns: \\tan/\\cot/\\arctan → tg/ctg/arctg (Russian school notation); unbraced decimal comma
d,d → d{,}d (KaTeX otherwise renders «0, 5»). Skipped: exact «[a,b]», «(a,b)», «{a,b}» (interval/point) and chains d,d,d."""
import json, re, sys, psycopg2
sys.path.insert(0, "/audit")
from latexsym import canon
DEC = re.compile(r"(?<![\d{,])(\d+),(\d+)(?![\d,}])")
def fix_math(m):
    m = re.sub(r"\\arctan(?![a-zA-Z])", lambda _: r"\operatorname{arctg}", m)
    m = re.sub(r"\\tan(?![a-zA-Z])", lambda _: r"\operatorname{tg}", m)
    m = re.sub(r"\\cot(?![a-zA-Z])", lambda _: r"\operatorname{ctg}", m)
    # spans where a comma separates elements, not a decimal: set braces \{...\} and bare pairs (a,b) / [a,b] with signs
    skip = [mo.span() for mo in re.finditer(r"\\\{[^{}]*?\\\}", m)]
    skip += [mo.span() for mo in re.finditer(r"[\(\[]\s*[-+−]?\d+,\s*[-+−]?\d+\s*[\)\]]", m)]
    def dec(mo):
        a, b = mo.start(), mo.end()
        if any(x <= a and b <= y for x, y in skip):
            return mo.group(0)
        pre, post = m[a - 1:a], m[b:b + 1]
        if (pre, post) in (("[", "]"), ("(", ")"), ("{", "}"), ("[", ")"), ("(", "]")):
            return mo.group(0)
        return mo.group(1) + "{,}" + mo.group(2)
    return DEC.sub(dec, m)
AMBIG = re.compile(r"\\\{[^{}]*\d,\s*-?\d[^{}]*\\\}|[\(\[]\s*[-+−]?\d+,\s*[-+−]?[\d\\]")
MANUAL = []
def fix(s, tid=None):
    if not isinstance(s, str) or "$" not in s: return s
    if AMBIG.search(s) and DEC.search(s):
        MANUAL.append((tid, s[:200]))
        s2 = re.sub(r"\\arctan(?![a-zA-Z])|\\tan(?![a-zA-Z])|\\cot(?![a-zA-Z])", lambda mo: {"\\arctan": "\\operatorname{arctg}", "\\tan": "\\operatorname{tg}", "\\cot": "\\operatorname{ctg}"}[mo.group(0)], s)
        return s2
    parts = s.replace("$$", "\x00").split("$")
    for i in range(1, len(parts), 2): parts[i] = fix_math(parts[i])
    return "$".join(parts).replace("\x00", "$$")
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex, answer_options_latex, distractor_meta FROM tasks_master WHERE is_active")
spec, diffs = {}, []
for tid, ql, kl, aol, dm in c.fetchall():
    f = {}
    for col, val in (("question_latex", ql), ("correct_answer_latex", kl)):
        nv = fix(val, tid)
        if nv != val: f[col] = nv; diffs.append((tid, col, val, nv))
    if isinstance(aol, list):
        new = [dict(o, text=fix(o.get("text"), tid)) if isinstance(o, dict) else fix(o, tid) for o in aol]
        if new != aol: f["answer_options_latex"] = new; diffs += [(tid, "opt", str(a), str(b)) for a, b in zip(aol, new) if a != b]
    if isinstance(dm, list):
        new = [dict(d, value_latex=fix(d.get("value_latex"), tid)) if isinstance(d, dict) and d.get("value_latex") else d for d in dm]
        if new != dm: f["distractor_meta"] = new; diffs += [(tid, "dm", a.get("value_latex"), b.get("value_latex")) for a, b in zip(dm, new) if a != b]
    if f:
        spec[tid] = {"why": "обозначения в LaTeX-колонках: tan/cot → tg/ctg (школьная запись), десятичная запятая в формулах d,d → d{,}d; смысл не меняется, сырые колонки не тронуты",
                     "source": "L6g, 25.09", "fields": f, "latex_symbol_only": True}
bad = [(t, col) for t, col, a, b in diffs if canon(a) != canon(b)]
print("tasks:", len(spec), "strings:", len(diffs), "canon mismatches:", len(bad), bad[:5])
json.dump(spec, open("/audit/restore_J_L6g.json", "w"), ensure_ascii=False, indent=1)
json.dump(diffs, open("/audit/l6g_diffs.json", "w"), ensure_ascii=False, indent=1)
json.dump(MANUAL, open("/audit/l6g_manual.json", "w"), ensure_ascii=False, indent=1)
print("left for manual review (ambiguous comma):", len(MANUAL), "strings in", len({t for t, _ in MANUAL}), "tasks")
