import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer, correct_answer_latex, answer_options_latex FROM tasks_master WHERE id = ANY(%s)", (["G5_TB_57_1352.1","G11_TB_5_2_1_1","G6_TB_8_349.1","G6_TB_89–90_758.2.2","G5_TB_57_1339.1"],))
for r in c.fetchall(): print(r[0], "\n Q:", r[1][:300], "\n K:", r[2][:200], "| KL:", r[3][:200], "\n O:", str(r[4])[:300])
