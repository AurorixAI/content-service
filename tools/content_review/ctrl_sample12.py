import random, json, glob, psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id FROM tasks_master WHERE is_active ORDER BY id")
ids = [r[0] for r in c.fetchall()]
prev = set()  # previous sample lists were in a wiped tmp dir; uniform sample over the whole active bank
pool = [t for t in ids if t not in prev]
random.Random(20261001).shuffle(pool)
s = pool[:300]
json.dump(s, open("/audit/ctrl12_todo.json", "w"))
c.execute("SELECT id, question_latex, correct_answer_latex, answer_type, distractor_meta, question_image_url, (tags->>'split_source') FROM tasks_master WHERE id = ANY(%s)", (s,))
rows = {r[0]: r for r in c.fetchall()}
out = []
for t in s:
    i, q, k, at, dm, img, sp_ = rows[t]
    out.append({"id": i, "q": q, "key": k, "type": at, "img": bool(img), "split_child": bool(sp_),
                "options": [{"v": (d.get("value_latex") or d.get("value")), "why": (d.get("error_logic_latex") or d.get("explanation") or "")} for d in (dm or [])]})
json.dump(out, open("/audit/ctrl12_dump.json", "w"), ensure_ascii=False, indent=0)
print("active", len(ids), "excluded prev", len(prev), "sample", len(s), "split children", sum(o["split_child"] for o in out))
