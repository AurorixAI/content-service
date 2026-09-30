import psycopg2, re, json
from collections import defaultdict
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex, split_part(source_reference,'::',1) FROM tasks_master WHERE is_active")
def nq(q):
    q = (q or "").replace("\\dfrac", "\\frac").replace("{,}", ",").replace("\\left", "").replace("\\right", "")
    q = re.sub(r"\\square|\[\?\]|▢|\\ast|\*", "#", q)
    q = re.sub(r"^\s*(?:\d+[.)]|[а-яa-z]\))\s*", "", q)
    q = re.sub(r"[\s$.;:,!?]|\\[,;!]", "", q).lower()
    return q
g = defaultdict(list)
for t, q, k, b in c.fetchall():
    if len(nq(q)) < 12: continue
    g[(b, nq(q), re.sub(r"[\s$]|\\[,;]", "", (k or "")).replace("\\dfrac", "\\frac"))].append(t)
d = {k: v for k, v in g.items() if len(v) > 1}
print("duplicate groups", len(d), "extra tasks", sum(len(v) - 1 for v in d.values()))
from collections import Counter
print(Counter((k[0] or "none")[:8] for k in d).most_common())
json.dump([[(k[0] or "none")[:8], k[1][:120], v] for k, v in d.items()], open("/audit/dupsweep.json", "w"), ensure_ascii=False, indent=0)
for k, v in list(d.items())[:25]: print(v, "|", k[1][:90])
