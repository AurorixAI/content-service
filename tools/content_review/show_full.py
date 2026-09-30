import sys, psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
for t in sys.argv[1].split(","):
    c.execute("SELECT question_latex, question_text, correct_answer_latex, distractor_meta FROM tasks_master WHERE id=%s", (t,))
    q, qt, k, d = c.fetchone()
    print(t, "\nQ:", q, "\nRAW:", qt if qt != q else "=", "\nK:", k)
    if len(sys.argv) > 2:
        for x in d or []: print("  D:", x.get("value_latex") or x.get("value"), "—", (x.get("explanation_latex") or x.get("explanation") or "")[:300])
    print()
