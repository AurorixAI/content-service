import psycopg2, re, json
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex, distractor_meta, source_reference FROM tasks_master WHERE is_active")
V = re.compile(r"^\s*(Найдите|Решите|Вычислите|Упростите|Докажите|Постройте|Сократите|Разложите|Представьте|Выполните|Сравните|Запишите|Укажите|Определите|Известно|Дано|Дана|Даны|При каких|Какое|Сколько)\b")
out = []
for tid, q, k, d, s in c.fetchall():
    for i, x in enumerate(d or []):
        v = (x.get("value") or "")
        v = str(v)
        if V.match(v):
            out.append((tid, i, v[:90], " ".join((q or "").split())[:90]))
print(len(out))
from collections import Counter
print(Counter(t.split("_")[0]+"_"+t.split("_")[1] for t,*_ in out).most_common(20))
json.dump(out, open("/audit/junkd.json","w"), ensure_ascii=False, indent=0)
for r in out[:60]: print(r)
