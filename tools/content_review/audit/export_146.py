import psycopg2, json
ids=[json.loads(l)['id'] for l in open('/audit/audit/deferred.jsonl') if l.strip()]
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex, distractor_meta FROM tasks_master WHERE id = ANY(%s)",(ids,))
def opt(i, d):
    if not isinstance(d, dict):
        return {"i": i, "v": str(d), "why": ""}
    v = d.get('value_latex') or d.get('value') or ""
    why = d.get('error_logic_latex') or d.get('explanation_latex') or d.get('explanation') or ""
    return {"i": i, "v": v, "why": why}
items=[]
for id_,q,key,meta in c.fetchall():
    if isinstance(meta,str): meta=json.loads(meta)
    items.append({"id":id_,"q":q,"key":key,"opts":[opt(i,d) for i,d in enumerate(meta or [])]})
json.dump(items,open('/audit/audit/batch_146.json','w',encoding='utf-8'),ensure_ascii=False,separators=(',',':'))
print(len(items))
