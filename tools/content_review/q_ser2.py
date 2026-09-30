import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
for pat in ["G5_TB_38_1516.%", "G6_TB_14_596.%", "G6_TB_16_674.%", "G6_TB_30_1151.%", "G6_TB_30_1152.%", "G6_TB_34_1237.%", "G6_TB_34_1238.%", "G6_TB_34_1254.%", "G6_TB_18_747.%", "G5_TB_62_1474.%"]:
    c.execute("SELECT id, question_latex, correct_answer FROM tasks_master WHERE is_active AND id LIKE %s ORDER BY id", (pat,))
    for r in c.fetchall(): print(r[0], '|', r[1][-70:].replace(chr(10), ' '), '| K:', r[2])
