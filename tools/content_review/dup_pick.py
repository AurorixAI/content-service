import json, re, psycopg2
from collections import Counter
G = json.load(open("/audit/dup_cls2.json"))
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
def exn(x, b8):
    last = (x["loc"] or "").split(":")[-1].strip(); p = last.split(".")
    if b8 in ("3aeaf6a8", "e92457e0") and len(p) >= 2 and p[0].isdigit(): return ".".join(p[:2])
    return p[0]
def order(s):
    try: return tuple(int(v) for v in re.findall(r"\d+", s)[:3])
    except: return (9999,)
MANUAL_KEEP = {"G7_TB_2_32.1": "G7_TB_2_22.1"}   # bank 32.1 is misfiled: book № 32 is a different exercise
plan, drop_ids = [], []
for g in G:
    b8 = g["book"][:8]; its = g["items"]; hits = (g.get("loc2") or {}).get("hits")
    hits = hits if isinstance(hits, list) else []
    def score(x):
        verified = exn(x, b8) in hits
        subsec = 0 if (x["loc"] or "").startswith(("§", "?")) else 1
        return (verified, x["skill"] is not None, subsec, x["nd"], x["vs"] == "verified", tuple(-v for v in order(exn(x, b8))), x["id"] < "")
    keep = max(its, key=score)
    for bad, good in MANUAL_KEEP.items():
        if any(x["id"] == bad for x in its): keep = next(x for x in its if x["id"] == good)
    drops = [x for x in its if x["id"] != keep["id"]]
    kind = g["cls"]
    if kind == "diff_ex": kind = "book_repeat" if sum(1 for x in its if exn(x, b8) in hits) >= 2 else ("import_dup" if len(hits) == 1 else "diff_ex_unverified")
    plan.append({"book": b8, "kind": kind, "keep": keep["id"], "drop": [x["id"] for x in drops], "keep_skill": keep["skill"], "drop_skills": [x["skill"] for x in drops], "q": its[0]["q"][:120]})
    drop_ids += [x["id"] for x in drops]
print(Counter(p["kind"] for p in plan), "drop", len(drop_ids))
# skill impact
c.execute("SELECT skill_id, count(*) FROM tasks_master WHERE is_active AND skill_id IS NOT NULL GROUP BY 1"); cnt = dict(c.fetchall())
c.execute("SELECT id, skill_id FROM tasks_master WHERE id = ANY(%s)", (drop_ids,)); dsk = Counter(s for _, s in c.fetchall() if s)
zero = [s for s, n in dsk.items() if cnt.get(s, 0) - n <= 0]
print("skills losing tasks:", len(dsk), "skills that would drop to 0:", zero)
changed = [p for p in plan if any(s != p["keep_skill"] for s in p["drop_skills"])]
print("groups where dropped copy has another skill:", len(changed))
json.dump(plan, open("/audit/dup_plan.json", "w"), ensure_ascii=False, indent=0)
