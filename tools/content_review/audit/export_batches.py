import psycopg2, json, random
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex, distractor_meta FROM tasks_master WHERE is_active ORDER BY id")
rows = c.fetchall()
excl = set(json.load(open('/audit/ctrl12_todo.json')))
rows = [r for r in rows if r[0] not in excl]
random.Random(20261002).shuffle(rows)
rows = rows[:2000]
def opt(i, d):
    if not isinstance(d, dict):
        return {"i": i, "v": str(d), "why": ""}
    v = d.get('value_latex') or d.get('value') or ""
    why = d.get('error_logic_latex') or d.get('explanation_latex') or d.get('explanation') or ""
    return {"i": i, "v": v, "why": why}
items = []
for id_, q, key, meta in rows:
    if isinstance(meta, str):
        meta = json.loads(meta)
    items.append({"id": id_, "q": q, "key": key, "opts": [opt(i, d) for i, d in enumerate(meta or [])]})
n = 0
for b in range(20):
    chunk = items[b*100:(b+1)*100]
    n += len(chunk)
    with open('/audit/audit/batch_%03d.json' % (b+1), 'w', encoding='utf-8') as f:
        json.dump(chunk, f, ensure_ascii=False, separators=(',', ':'))
json.dump([r[0] for r in rows], open('/audit/audit/sample2000_ids.json', 'w', encoding='utf-8'), ensure_ascii=False)
print(len(items), 20)
