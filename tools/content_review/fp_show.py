import psycopg2,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
ids="G7_TB_25_593.1 G7_TB_1_6.1 G7_TB_2_17.1 G7_TB_20_452.1 G7_TB_20_462.1 G7_TB_21_471.1 G7_TB_2_24.1 G7_TB_34_877.1 G7_TB_13_270.1 G7_TB_5_91.1 G7_TB_35_912.1 G7_TB_2_22.1 G7_TB_34_876.1 G7_TB_16_316.1 G7_TB_11_252.1 G7_TB_18_397.1 G7_TB_18_399.1 G7_TB_18_399.3 G7_TB_18_397.2 G7_TB_35_900.5".split()
for i in ids:
    cur.execute("select question_latex,correct_answer_latex,jsonb_array_length(distractor_meta) from tasks_master where id=%s and is_active",(i,))
    r=cur.fetchone()
    base=i.rsplit('.',1)[0]
    cur.execute("select id from tasks_master where id like %s and is_active order by id",(base+'.%',))
    sib=[x[0] for x in cur.fetchall()]
    print(i,'\n  Q:',repr(r[0]),'\n  K:',repr(r[1]),'nd',r[2],'sib',sib)
