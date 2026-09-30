import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
for t in ["G10_TB_§25_25_3_1","G11_TB_§4_4_44_ж","G5_TB_10_179.2","G6_TB_ТестX_1177.2","G10_TB_§25_25_3_4","DIFF_G5_S33_01_C_01"]:
    c.execute("SELECT t.id, b.title, t.source_reference, t.question_text FROM tasks_master t LEFT JOIN textbooks b ON b.textbook_id::text = split_part(t.source_reference,'::',1) WHERE t.id=%s", (t,))
    r = c.fetchone(); print(r[0], "|", r[1], "|", r[2], "\n   QT:", (r[3] or "")[:200])
