import re, psycopg2, random
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex, answer_options_latex::text, distractor_meta::text FROM tasks_master WHERE is_active")
tan = dec = chain = 0; ex = []
DEC = re.compile(r"(?<![\d{,])(\d+),(\d+)(?![\d,}])")
for tid, *cols in c.fetchall():
    s = " ".join(x or "" for x in cols)
    if re.search(r"\\\\?(tan|cot|arctan)(?![a-zA-Z])", s): tan += 1
    parts = (cols[0] or "").split("$") + (cols[1] or "").split("$")
    mm = [p for i, p in enumerate(parts) if i % 2 and DEC.search(p)]
    if mm:
        dec += 1
        if len(ex) < 400: ex.append((tid, mm[0][:90]))
print("tan/cot tasks:", tan, "| q/key with unbraced d,d in math:", dec)
random.seed(1)
for e in random.sample(ex, 25): print(e)
