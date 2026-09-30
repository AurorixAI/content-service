import psycopg2, json
S = json.load(open("/audit/skills_low.json"))
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
for s in S:
    c.execute("SELECT name_ru, parent_id FROM knowledge_hierarchy WHERE id=%s", (s["parent"],)); p = c.fetchone() or ("", "")
    c.execute("SELECT name_ru FROM knowledge_hierarchy WHERE id=%s", (p[1],)); gp = (c.fetchone() or ("",))[0]
    c.execute("SELECT id, is_active, difficulty, regexp_replace(question_latex,'\s+',' ','g'), correct_answer_latex, tags->>'deactivated_reason' FROM tasks_master WHERE skill_id=%s ORDER BY is_active DESC", (s["id"],))
    ts = c.fetchall()
    s["parent_name"] = p[0]; s["topic"] = gp; s["tasks"] = [dict(id=a, active=b, diff=d, q=q, k=k, reason=(r or "")[:80]) for a, b, d, q, k, r in ts]
    print(f'### {s["id"]} (G{s["grade"]}) {s["name"]} | {s["topic"]} → {s["parent_name"]} | desc: {(s["desc"] or "")[:70]} | ex: {(s["example"] or "")[:60]}')
    for t in s["tasks"]: print(f'   {"A" if t["active"] else "-"} {t["diff"]} {t["id"]}: {t["q"][:110]} | K: {(t["k"] or "")[:40]} {("| OFF: " + t["reason"]) if not t["active"] else ""}')
json.dump(S, open("/audit/skills_low_ctx.json", "w"), ensure_ascii=False, indent=1)
