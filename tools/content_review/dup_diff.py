import json, psycopg2, re
from collections import Counter
exec(open("/audit/dup_strict.py").read().split("g = defaultdict(list)")[0])
S = {tuple(sorted(x["id"] for x in gr["items"])) for gr in json.load(open("/audit/dup_strict.json"))}
L = json.load(open("/audit/dupsweep.json"))
R = {r[0]: r for r in rows}
why = Counter(); ex = []
for b, q, ids in L:
    ids = [i for i in ids if i in R]
    if tuple(sorted(ids)) in S or len(ids) < 2: continue
    a, b2 = R[ids[0]], R[ids[1]]
    if nq(a[1]) != nq(b2[1]): w = "statement differs"
    elif nk(a[3] or a[4]) != nk(b2[3] or b2[4]): w = "key form differs"
    elif a[5] != b2[5]: w = "answer_type differs"
    else: w = "other"
    why[w] += 1; ex.append((w, ids[:2], nq(a[1])[:70], nq(b2[1])[:70], nk(a[3] or a[4])[:40], nk(b2[3] or b2[4])[:40]))
print(why)
for w in why:
    print("==", w); [print(" ", e[1:]) for e in ex if e[0] == w][:1]
    for e in [e for e in ex if e[0] == w][:8]: print(" ", e[1:])
json.dump(ex, open("/audit/dup_diff.json", "w"), ensure_ascii=False, indent=0)
