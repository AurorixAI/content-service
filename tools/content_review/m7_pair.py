import json, re, sys
sys.argv = ["x", "makarychev7"]
exec(open("/audit/tb_answers.py").read().split("db = psycopg2.connect")[0])
import psycopg2
from collections import defaultdict
db = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
db.execute("SELECT id, source_reference, correct_answer_latex, correct_answer, question_latex FROM tasks_master WHERE is_active AND source_reference LIKE %s", (tbid + "%",))
by_ex = defaultdict(list)
for tid, src, cal, ca, q in db.fetchall():
    ex, it = locate(tid, src)
    if ex: by_ex[ex].append((tid, cal or ca or "", " ".join((q or "").split())))
def agree(bt, key):
    if not bt or not key: return False
    if norm(bt) == norm(key): return True
    ne = numeq(bt, key)
    if ne is True: return True
    if ne is None:
        a, b = nums(bt), nums(key)
        return len(a) > 0 and a == b
    return False
cands, stats = [], {"ex_with_answers": 0, "bank_tasks": 0, "matched": 0}
for ex, tasks in by_ex.items():
    a = ANS.get(ex)
    if not a: continue
    stats["ex_with_answers"] += 1
    book = {lab: txt for lab, txt in a.items() if txt.strip()}
    used = set(); unmatched = []
    for tid, key, q in tasks:
        stats["bank_tasks"] += 1
        hit = [lab for lab, txt in book.items() if agree(txt, key)]
        # multi-item keys ("x^6; x^6; a^20") : split and match each part
        if not hit and ";" in key:
            parts = [p for p in re.split(r";\s*", key.replace("$", "")) if p.strip()]
            hit = [lab for lab, txt in book.items() if any(agree(txt, p) for p in parts)]
        if hit: stats["matched"] += 1; used.update(hit)
        else: unmatched.append((tid, key, q))
    free_book = {lab: txt for lab, txt in book.items() if lab not in used}
    if unmatched and free_book: cands.append(dict(ex=ex, bank=unmatched, book=free_book))
json.dump(cands, open("/audit/m7_cands.json", "w"), ensure_ascii=False, indent=0)
print(stats, "exercises with unmatched bank keys AND unused book answers:", len(cands), "bank tasks in them:", sum(len(c["bank"]) for c in cands))
