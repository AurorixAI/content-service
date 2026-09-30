import psycopg2, re, json
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, question_text, correct_answer_latex, distractor_meta, source_reference FROM tasks_master WHERE is_active")
J = re.compile(r"^\s*(Найдите (значение выражения|производную|все значения параметра)|Сравните числа: \$7\\sqrt|Сколько всего метров проволоки)")
CMPQ = re.compile(r"звёздочк|звездочк|\\ast|Сравните|сравните|знак", re.I)
junk, star = {}, []
for tid, q, qt, k, d, s in c.fetchall():
    q = q or ""
    idx = [i for i, x in enumerate(d or []) if J.match(str(x.get("value") or "")) and not q.lstrip().startswith(str(x.get("value"))[:12])]
    if idx:
        rest = [str(x.get("value")) for i, x in enumerate(d) if i not in idx]
        junk[tid] = {"drop": idx, "rest": rest, "k": k, "q": " ".join(q.split())[:200], "src": s}
    if CMPQ.search(q) and re.search(r"\d\}?\s*\\cdot\s*\\?d?f?r?a?c?\{?\d", q) and re.search(r"^\$?\s*[<>=]", (k or "").strip()):
        star.append((tid, " ".join(q.split())[:200], k))
json.dump({"junk": junk, "star": star}, open("/audit/junk2.json", "w"), ensure_ascii=False, indent=1)
print("junk tasks", len(junk), "junk distractors", sum(len(v["drop"]) for v in junk.values()))
from collections import Counter
print("rest-count after drop", Counter(len(v["rest"]) for v in junk.values()))
print("star candidates", len(star))
for t in star: print(" ", t)
