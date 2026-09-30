import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, source_reference, answer_type, question_text, question_latex, correct_answer, correct_answer_latex, answer_options, distractor_meta FROM tasks_master WHERE id LIKE 'G6_TB_8_349%'")
for r in c.fetchall(): print(*r, sep="\n  ")
