import json, psycopg2, re
from collections import Counter
D = json.load(open("/audit/dupsweep.json"))
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
cls = Counter(); ex = {"same_ex": [], "diff_ex": [], "no_src": []}
for b, q, ids in D:
    c.execute("SELECT id, split_part(source_reference,'::',2) FROM tasks_master WHERE id = ANY(%s)", (ids,)); src = dict(c.fetchall())
    exn = set()
    for t in ids:
        s = src.get(t) or ""
        m = re.findall(r"\d+", s.split(":")[-1]) if s else []
        exn.add(tuple(m[:2]) if m else None)
    k = "no_src" if b == "none" else ("same_ex" if len(exn) == 1 else "diff_ex")
    cls[k] += 1; ex[k].append((ids, [src.get(t) for t in ids]))
print(cls)
for k in ex: print(k, ex[k][:4])
json.dump(ex, open("/audit/dupclass.json", "w"), ensure_ascii=False)
