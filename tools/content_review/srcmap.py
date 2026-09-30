import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
pats = ["G5_TB_26_1028%","G5_TB_30_1161%","G5_TB_37_1472%","G5_TB_4_67%","G5_TB_4_74%","G5_TB_5_172%","G5_TB_63_149%","G5_TB_70_17%","G5_TB_42_74%","G5_TB_50_12%","G5_TB_25_96%","G5_TB_24_946%","G5_TB_26_1032%","G5_TB_35_1370%","G5_TB_44_1738%","G6_TB_16_668%","G6_TB_15_624%","G6_TB_98%","G6_TB_95%","G6_TB_89%","G6_TB_4_1%","G6_TB_29_11%","G6_TB_20_859%","G6_TB_19_767%","G6_TB_24_976%","G7_TB_1_6.%","G9_TB_20_243%","G5_TB_1_10.%","G7_ALG_19_9%","G10_TB_3_1_3%","G5_TB_6_196%"]
for p in pats:
    c.execute("SELECT DISTINCT split_part(source_reference,'::',1), split_part(source_reference,'::',2) FROM tasks_master WHERE is_active AND id LIKE %s", (p,))
    print(p, c.fetchall()[:3])
c.execute("SELECT textbook_id, display_name FROM textbooks"); 
for r in c.fetchall(): print(r)
