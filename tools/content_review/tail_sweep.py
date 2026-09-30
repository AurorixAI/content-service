# sub-items split from one exercise: the shared closing question stayed only on the last sub-item
import re, json, psycopg2, os
from collections import defaultdict
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, regexp_replace(question_latex,'\s+',' ','g') FROM tasks_master WHERE is_active")
G = defaultdict(list)
for t, q in c.fetchall():
    m = re.match(r"^(.*)\.(\d+)$", t)
    if m: G[m.group(1)].append((int(m.group(2)), t, q))
TAIL = re.compile(r"(?:[.;?]\s*|\s+и\s+)((?:[А-Я]|запишите|найдите|вычислите|сравните|объясните|постройте|определите)[^.;]{6,}[.?]?)\s*$")
out = []
for base, L in G.items():
    if len(L) < 2: continue
    L.sort(); qs = [q for _, _, q in L]
    stem = os.path.commonprefix(qs)
    if len(stem) < 12: continue
    last = qs[-1]; m = TAIL.search(last[len(stem):])
    if not m: continue
    tail = m.group(1).strip()
    key = re.sub(r"\W", "", tail.lower())[:25]
    miss = [t for _, t, q in L[:-1] if key not in re.sub(r"\W", "", q.lower())]
    if miss: out.append((base, len(L), tail, miss))
json.dump(out, open("/audit/tail_hits.json", "w"), ensure_ascii=False, indent=0)
print(len(out), sum(len(m) for *_, m in out))
for b, n, tl, miss in out: print(b, n, "|", tl[:110], "| miss", len(miss))
