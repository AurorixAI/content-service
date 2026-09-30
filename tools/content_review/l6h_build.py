# -*- coding: utf-8 -*-
"""L6h: the «d,d» commas L6g left as ambiguous. Each occurrence decided (l6h_scan evidence, l6h_rules context rules,
manual review 25.09 of the rest): decimal → d{,}d; element separator in points / sets / intervals → «a; b» (Russian
notation). Display columns only; every changed string must equal the old one up to commas, semicolons and spaces."""
import json, re, sys, psycopg2
sys.path.insert(0, "/audit")
from l6h_rules import classify
from l6h_scan import evidence, group, math_spans, DEC  # noqa (scan module re-runs its scan on import; cheap)

# manual decisions for occurrences the rules could not decide
MAN_DEC = {  # decimals: function of one variable f(1,5); points on the number ray (grade 5–6); lists and sums of decimals
    "G10_TB_§6_6_4_2", "G10_TB_§7_7_5_1", "G10_TB_§6_6_5_1", "G10_TB_§6_6_5_2", "G10_TB_§7_7_3_1", "G10_TB_§6_6_6_1",
    "G10_TB_§6_6_6_2", "G10_TB_§6_6_3_1", "G10_TB_§6_6_3_4", "G10_TB_§6_6_3_2", "G10_TB_§6_6_3_3", "G10_TB_§7_7_3_2",
    "G10_TB_§7_7_3_3", "G10_TB_§7_7_5_2", "G10_TB_§7_7_6_2", "G10_TB_§6_6_5_3", "G10_TB_§7_7_5_3", "G10_TB_§7_7_6_1",
    "G10_TB_§7_7_4_2", "G8_TB_42_1064", "G6_TB_37_1369.1", "G6_TB_37_1369.2", "G8_TB_12_297.4", "G9_TB_1_8_3",
    "G6_TB_4_166", "G6_TB_23_939", "G5_TB_57_1339.1", "G5_TB_57_1339.2", "G5_TB_57_1352.1", "G5_TB_31_1179.1",
    "G5_TB_31_1179.2", "G5_TB_31_1179.3", "G5_TB_31_1178.1", "G5_TB_31_1178.2", "G5_TB_31_1178.3", "G8_TB_40_985.2",
    "G8_TB_40_988.1", "G6_TB_89–90_758.2.2", "G6_TB_ТестVI_897.2", "G6_TB_12_521.1", "GEN_G6_S35_02_B_03",
    "G6_TB_38_1408.2"}
SEP = {  # points in the plane, sets, intervals / domains, outcome pairs: commas separate elements
    "ds_llm_1581d67e71b2", "ds_llm_1adfa8df8be0", "G10_TB_1_3_3_9", "G10_TB_1_3_3_4", "G10_TB_1_3_3_10",
    "G10_TB_1_3_3_8", "G10_TB_1_3_3_7", "G11_TB_5_10*_5_100", "GEN_G6_S45_02_C_02", "GEN_G6_S45_02_C_03",
    "GEN_G6_S43_04_C_02", "G9_TB_12_182.1", "G9_TB_23_448_4", "G11_TB_5_2_1_1", "G9_TB_ЗПТ_879", "G9_TB_34_460",
    "G9_TB_34_461", "G9_TB_37_481_1"}
# left unchanged on purpose: C(20,5) binomial notation (G10_TB_6_2_19), integer sequences «3,4,5,6» (ds_llm_a11d447996fd);
# G6_TB_8_349.1 has a broken key — separate repair
CONTENT = r"(?:[^;()\[\]{}\\$]|\\[a-zA-Z]+(?:\{[^{}]*\})?|\{[^{}]*\})*?"
GRP = re.compile(r"(\\\{|[\(\[])(\s*" + CONTENT + r",\s*" + CONTENT + r")(\\\}|[\)\]])")


def sep_math(m):
    def g(mo):
        inner = mo.group(2)
        if not re.search(r"\d|\\infty|[a-z]", inner):
            return mo.group(0)
        return mo.group(1) + re.sub(r"\s*,\s*", "; ", inner.strip()) + mo.group(3)
    prev = None
    while prev != m:
        prev, m = m, GRP.sub(g, m)
    return m


SKIP = {"G10_TB_6_2_19", "ds_llm_a11d447996fd", "ds_llm_785728d703f2", "G6_TB_8_349.1"}


def fix(s, raw, tid):
    if not isinstance(s, str) or "$" not in s or tid in SKIP: return s
    out, last = [], 0
    for x, y in math_spans(s):
        seg = s[x:y]
        reps = []
        for mo in DEC.finditer(s, x, y):
            a, b = mo.group(1), mo.group(2)
            kind, _ = evidence(raw, a, b)
            gr = group(s, mo.start())
            if not kind and gr and ";" in gr[2]: kind = "DEC"
            if not kind: kind, _ = classify({"kind": None, "start": mo.start(), "tok": mo.group(0)}, s)
            if tid in SEP and gr and not re.search(r"[+*/:=<>]|\\cdot|\\times", gr[2]):
                continue  # separator: handled by sep_math on the whole group
            if not kind and tid in MAN_DEC: kind = "DEC"
            if kind == "DEC": reps.append((mo.start() - x, mo.end() - x, a + "{,}" + b))
        for p, q, r in sorted(reps, reverse=True):
            seg = seg[:p] + r + seg[q:]
        if tid in SEP: seg = sep_math(seg)
        out.append(s[last:x]); out.append(seg); last = y
    out.append(s[last:])
    return "".join(out)


norm = lambda t: re.sub(r"\s", "", str(t)).replace("{,}", ",").replace(";", ",")
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
occ_ids = sorted({o["id"] for o in json.load(open("/audit/l6h_occ.json"))})
c.execute("SELECT id, question_text, question_latex, correct_answer, correct_answer_latex, answer_options, answer_options_latex, distractor_meta FROM tasks_master WHERE is_active AND id = ANY(%s)", (occ_ids,))
spec, diffs = {}, []
for tid, qt, ql, ca, cal, ao, aol, dm in c.fetchall():
    f = {}
    for col, val, raw in (("question_latex", ql, qt), ("correct_answer_latex", cal, ca)):
        nv = fix(val, raw, tid)
        if nv != val: f[col] = nv; diffs.append((tid, col, val, nv))
    if isinstance(aol, list):
        new = [fix(o, ao[i] if isinstance(ao, list) and i < len(ao) else None, tid) if isinstance(o, str) else o for i, o in enumerate(aol)]
        if new != aol: f["answer_options_latex"] = new; diffs += [(tid, "opt", a, b) for a, b in zip(aol, new) if a != b]
    if isinstance(dm, list):
        new = [dict(d, value_latex=fix(d.get("value_latex"), d.get("value"), tid)) if isinstance(d, dict) and d.get("value_latex") else d for d in dm]
        if new != dm: f["distractor_meta"] = new; diffs += [(tid, "dm", a.get("value_latex"), b.get("value_latex")) for a, b in zip(dm, new) if a != b]
    if f:
        spec[tid] = {"why": "запятые в LaTeX-колонках: десятичная запятая d,d → d{,}d, разделитель элементов в точках, множествах и промежутках → «; »; "
                            "каждое вхождение решено по сырой колонке, контексту или вручную; сырые колонки не тронуты",
                     "source": "L6h, 25.09", "fields": f, "latex_display_manual": True}
bad = [(t, col, a, b) for t, col, a, b in diffs if norm(a) != norm(b)]
assert not bad, bad[:3]
json.dump(spec, open("/audit/restore_J_L6h.json", "w"), ensure_ascii=False, indent=1)
json.dump(diffs, open("/audit/l6h_diffs.json", "w"), ensure_ascii=False, indent=1)
print("tasks:", len(spec), "strings:", len(diffs), "| only comma/semicolon/space changes: OK")
