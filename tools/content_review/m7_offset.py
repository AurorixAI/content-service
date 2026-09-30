import json, re, sys
sys.argv = ["x", "makarychev7"]
src = open("/audit/tb_answers.py").read()
exec(src.split("db = psycopg2.connect")[0])
import psycopg2
db = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
db.execute("SELECT id, source_reference, correct_answer_latex, correct_answer FROM tasks_master WHERE is_active AND source_reference LIKE %s", (tbid + "%",))
rows = db.fetchall()
def agrees(bt, key):
    if bt is None: return False
    if norm(bt) == norm(key): return True
    ne = numeq(bt, key)
    if ne is True: return True
    return ne is None and nums(bt) == nums(key) and len(nums(key)) > 0
from collections import defaultdict, Counter
by_ex = defaultdict(list)
for tid, src, cal, ca in rows:
    ex, it = locate(tid, src)
    if ex and ex.isdigit(): by_ex[int(ex)].append((tid, it, cal or ca or ""))
res = {}
for ex, items in sorted(by_ex.items()):
    score = {}
    for off in range(-8, 9):
        a = ANS.get(str(ex + off))
        if not a: continue
        score[off] = sum(1 for tid, it, k in items if agrees(a.get(it) if it else (a.get("") or (list(a.values())[0] if len(a) == 1 else None)), k))
    if score:
        best = max(score, key=lambda o: (score[o], -abs(o)))
        res[ex] = (best, score.get(0, 0), score[best], len(items))
json.dump(res, open("/audit/m7_offsets.json", "w"))
# print runs of offsets
prev = None
for ex, (off, s0, sb, n) in sorted(res.items()):
    tag = off if sb > s0 else 0
    if tag != prev: print(f"from №{ex}: offset {tag} (own {s0}/{n}, best {sb}/{n})"); prev = tag
