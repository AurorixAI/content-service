import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex, distractor_meta, answer_options FROM tasks_master WHERE is_active AND id LIKE 'G5_TB_16_65%%' ORDER BY id")
for t, q, k, d, ao in c.fetchall():
    print(t, "| Q:", q[-60:], "| K:", k, "| D:", [x.get("value") for x in d or []], "| AO:", bool(ao))
