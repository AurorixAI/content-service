import psycopg2, re, json
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex FROM tasks_master WHERE is_active")
P1 = re.compile(r"\$(\d+)\$\s*:\s*\$\\d?frac\{\d+\}\{\d+\}")        # «$3$: $\dfrac{8}{17}...»  split mixed number
P2 = re.compile(r"\$(\d+)\$\s*:\s*\\d?frac")
P3 = re.compile(r"\$\d+\$\s*,\s*\$\d+\$")                          # «$1$, $2$» split decimal (check manually)
hits = []
for t, q, k in c.fetchall():
    q = q or ""
    if P1.search(q) or P2.search(q): hits.append(("MIX", t, " ".join(q.split())[-110:], k))
    elif P3.search(q) and not re.search(r"чис(ла|ел)|последовательн|значени[яй]", q): hits.append(("DEC?", t, " ".join(q.split())[-110:], k))
json.dump(hits, open("/audit/splitmix.json", "w"), ensure_ascii=False, indent=0)
from collections import Counter
print(Counter(h[0] for h in hits))
for h in hits: print(h)
