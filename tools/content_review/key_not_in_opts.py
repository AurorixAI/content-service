import json, re, psycopg2
from collections import Counter
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("""SELECT t.id, t.correct_answer, t.correct_answer_latex, t.answer_options, t.answer_options_latex, t.distractor_meta, t.question_latex, b.title
             FROM tasks_master t LEFT JOIN textbooks b ON b.textbook_id::text = split_part(t.source_reference,'::',1)
             WHERE t.is_active AND jsonb_typeof(t.answer_options)='array' AND jsonb_array_length(t.answer_options) >= 2""")
n = lambda s: re.sub(r"[\s$]", "", str(s or "")).replace("\\dfrac", "\\frac").replace("{,}", ",")
out = []
for tid, ca, cal, ao, aol, dm, q, book in c.fetchall():
    texts = [o.get("text") if isinstance(o, dict) else o for o in ao]
    if ca in texts: continue
    if n(ca) in {n(x) for x in texts} or n(cal) in {n(x) for x in texts}: continue
    out.append(dict(id=tid, book=book, q=q[:200], k=ca, kl=cal, opts=texts, optl=[(o.get("text") if isinstance(o, dict) else o) for o in (aol or [])],
                    dm=[d.get("value") for d in (dm or []) if isinstance(d, dict)]))
print(len(out), Counter(x["book"] for x in out).most_common())
json.dump(out, open("/audit/key_not_in_opts.json", "w"), ensure_ascii=False, indent=1)
