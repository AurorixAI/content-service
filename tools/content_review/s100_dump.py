import psycopg2, json
ids = ["G10_TB_§25_25_3_1","G10_TB_§25_25_3_4","G5_TB_10_179.2","G6_TB_ТестX_1177.2","DIFF_G5_S33_01_C_01","G11_TB_§4_4_44_ж","G11_TB_8_1_7_18_5","G6_TB_49–50_412","G9_TB_3_27_г","G5_TB_59_1405.5","G8_ALG_32_557.5","G8_TB_32_711.4","G6_TB_19_767.3","GEN_G6_S35_03_A_04"]
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT t.id, b.title, t.question_text, t.question_latex, t.correct_answer, t.correct_answer_latex, t.answer_options, t.answer_options_latex, t.distractor_meta FROM tasks_master t LEFT JOIN textbooks b ON b.textbook_id::text = split_part(t.source_reference,'::',1) WHERE t.id = ANY(%s) ORDER BY t.id", (ids,))
for r in c.fetchall():
    print("###", r[0], "|", r[1]); print("  QT:", r[2][:260]); print("  QL:", r[3][:260]); print("  K:", r[4], "| KL:", r[5]); print("  AO:", r[6], "| AOL:", r[7])
    for d in r[8] or []: print("  D:", repr(d.get("value")), "|", repr(d.get("value_latex")))
