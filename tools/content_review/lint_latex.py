import json, re, psycopg2
from collections import Counter, defaultdict
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex, answer_options_latex, distractor_meta FROM tasks_master WHERE is_active")
FN = r"(?:arcsin|arccos|arctg|arcctg|arctan|sin|cos|tg|ctg|tan|cot|log|ln|lg|exp|max|min|lim)"
RULES = {
 "bare_fn": re.compile(r"(?<![\\a-zA-Z])" + FN + r"(?![a-zA-Z])"),
 "code_pow": re.compile(r"\*\*|\^\(|sqrt\(|(?<![\\a-zA-Z])sqrt(?![a-zA-Z])|(?<![\\a-zA-Z])pi(?![a-zA-Z])|>=|<=|!=|(?<=[\w)])\s*\*\s*(?=[\w(])"),
 "unicode_math": re.compile(r"[√π≤≥≠∞∈∉∪∩×÷·−→⇒⇔∅αβγφ°²³¹⁴⁵⁶⁷⁸⁹⁰⁻₀₁₂₃∑∫]"),
}
def maths(s):
    parts = (s or "").replace("$$", "$").split("$")
    out = [parts[i] for i in range(1, len(parts), 2)]
    return [re.sub(r"\\(operatorname|mathrm|text|mbox)\{[^{}]*\}", " ", x) for x in out]
hits = defaultdict(list); cnt = Counter()
for tid, ql, kl, aol, dm in c.fetchall():
    fields = [("q", ql), ("k", kl)]
    for i, o in enumerate(aol or []):
        fields.append((f"o{i}", o.get("text") if isinstance(o, dict) else o))
    for i, d in enumerate(dm or []):
        if isinstance(d, dict): fields.append((f"d{i}", d.get("value_latex")))
    for f, s in fields:
        if not isinstance(s, str) or not s: continue
        for name, rx in RULES.items():
            if name == "unicode_math":
                m = rx.findall(s)   # anywhere in a LaTeX display column
            else:
                m = [x for part in maths(s) for x in rx.findall(part)]
            if m:
                cnt[name] += 1; hits[tid].append((f, name, "".join(sorted(set(m)))[:20], s[:160]))
print(cnt, "tasks:", len(hits))
json.dump(hits, open("/audit/lint_latex.json", "w"), ensure_ascii=False, indent=1)
