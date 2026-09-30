import sys, psycopg2, json
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
for loc in sys.argv[1].split(","):
    c.execute("SELECT id, question_text, question_latex, correct_answer_latex, distractor_meta FROM tasks_master WHERE is_active AND source_reference = %s", ("1b758c3d-9d0d-41f6-ad0b-dcf3c3872a75::" + loc,))
    for tid, qt, ql, k, d in c.fetchall():
        print("##", loc, tid); print(" QT:", repr(qt)); print(" QL:", repr(ql)); print(" K:", k); print(" D:", [x.get("value") for x in (d or [])])
