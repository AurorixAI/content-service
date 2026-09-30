import json, psycopg2
ids = ["G11_TB_1_7","G11_TB_§19_1_3","G11_TB_§20_8_1","G11_TB_§24_8_2","G11_TB_§4_2_1","G11_TB_§4_2_2","G11_TB_§26_3","G11_TB_§19_4","G11_TB_§20_11"]
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, answer_type, question_text, question_latex, tags->'topic', tags ? 'latex_attested_fields' FROM tasks_master WHERE id = ANY(%s)", (ids,))
for r in c.fetchall(): print(r[0], r[1], r[4], r[5]); print("  QT:", r[2]); print("  QL:", r[3])
