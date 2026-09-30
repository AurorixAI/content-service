import psycopg2, json
ids = ["G6_TB_7_296.2","G6_TB_42_1490.2","G6_TB_6_228.1","G6_TB_6_228.2","G5_TB_43_1692.1","G5_TB_43_1692.2","G5_TB_40_1556.5","G5_TB_40_1592.3","G5_TB_39_1540.6"]
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, source_reference, answer_type, question_text, correct_answer, correct_answer_latex, answer_options, distractor_meta FROM tasks_master WHERE id = ANY(%s) ORDER BY id", (ids,))
for r in c.fetchall():
    print("###", r[0], r[1], r[2]); print("  Q:", r[3][:220]); print("  K:", r[4], "| KL:", r[5]); print("  O:", r[6])
    for d in r[7] or []: print("  D:", d.get("value"), "|", d.get("value_latex"), "|", (d.get("error_logic") or "")[:110])
