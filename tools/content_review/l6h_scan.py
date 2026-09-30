# -*- coding: utf-8 -*-
"""L6h scan: every remaining unbraced «d,d» inside $…$ of the display columns (left by L6g as ambiguous).
Each occurrence is classified: DEC (decimal comma → d{,}d) or SEP (element separator → «d; d», Russian notation),
by evidence from the raw column (d.d in raw = decimal; «d; d» / «d, d» in raw = separator) or from the enclosing bracket
group (a group already separated by «;» holds decimals). Unresolved occurrences are listed for manual decision."""
import json, re, psycopg2
DEC = re.compile(r"(?<![\d{,.])(\d+),(\d+)(?![\d}])")
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_text, question_latex, correct_answer, correct_answer_latex, answer_options, answer_options_latex, distractor_meta FROM tasks_master WHERE is_active")


def math_spans(s):
    out, i = [], 0
    for mo in re.finditer(r"\$\$(.+?)\$\$|\$(.+?)\$", s, re.S):
        g = 1 if mo.group(1) is not None else 2
        out.append((mo.start(g), mo.end(g)))
    return out


def group(s, pos):
    """innermost bracket group ( [ \\{ containing pos: returns (open_idx, close_idx, text) or None"""
    depth, i = 0, pos
    opens = {")": "(", "]": "[", "}": "{"}
    while i > 0:
        i -= 1
        ch = s[i]
        if ch in ")]" or (ch == "}" and s[i - 1:i] == "\\"):
            depth += 1
        elif ch in "([" or (ch == "{" and s[i - 1:i] == "\\"):
            if depth == 0:
                j, d2 = pos, 0
                while j < len(s):
                    cj = s[j]
                    if cj in "([" or (cj == "{" and s[j - 1:j] == "\\"): d2 += 1
                    elif cj in ")]" or (cj == "}" and s[j - 1:j] == "\\"):
                        if d2 == 0: return i, j, s[i:j + 1]
                        d2 -= 1
                    j += 1
                return i, None, s[i:]
            depth -= 1
    return None


def evidence(raw, a, b):
    raw = str(raw or "")
    if re.search(rf"(?<![\d.]){a}\.{b}(?!\d)", raw): return "DEC", "raw d.d"
    return None, None


occ, auto = [], {"DEC": 0, "SEP": 0}
for tid, qt, ql, ca, cal, ao, aol, dm in c.fetchall():
    pairs = [("question_latex", None, ql, qt), ("correct_answer_latex", None, cal, ca)]
    if isinstance(aol, list):
        pairs += [("answer_options_latex", i, (o.get("text") if isinstance(o, dict) else o), (ao[i] if isinstance(ao, list) and i < len(ao) else None)) for i, o in enumerate(aol)]
    if isinstance(dm, list):
        pairs += [("distractor_meta", i, d.get("value_latex"), d.get("value")) for i, d in enumerate(dm) if isinstance(d, dict)]
    for col, idx, s, raw in pairs:
        if not isinstance(s, str) or "$" not in s: continue
        for x, y in math_spans(s):
            for mo in DEC.finditer(s, x, y):
                a, b = mo.group(1), mo.group(2)
                kind, why = evidence(raw, a, b)
                g = group(s, mo.start())
                if not kind and g and ";" in g[2]:
                    kind, why = "DEC", "group uses ;"
                if kind: auto[kind] += 1
                occ.append(dict(id=tid, col=col, idx=idx, start=mo.start(), tok=mo.group(0), kind=kind, why=why,
                                ctx=s[max(0, mo.start() - 60):mo.end() + 60], raw=str(raw or "")[:300], grp=g[2][:80] if g else None))
json.dump(occ, open("/audit/l6h_occ.json", "w"), ensure_ascii=False, indent=1)
print("occurrences:", len(occ), "in tasks:", len({o["id"] for o in occ}), "auto:", auto, "unresolved:", sum(1 for o in occ if not o["kind"]))
