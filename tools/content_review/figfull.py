import psycopg2,re,json
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
ids=json.load(open('fig_ids.json'))
for i in ids:
    if not re.match(r'(GEN_G6_S4[67]|DIFF_G6_S4[67]|ds_llm_c5ef|ds_llm_9c2f|ds_llm_9368|ds_llm_cca5|ds_llm_9a55|DIFF_G5_S02_01|DIFF_G5_S27|G5_TB_31_554|G11_TB_§2_1[01]|GEN_G6_S47|G7_ALG_31_19)',i): continue
    cur.execute("select regexp_replace(question_latex,'\\s+',' ','g'),correct_answer_latex from tasks_master where id=%s",(i,)); q,k=cur.fetchone()
    print(f"## {i}\n Q: {q}\n K: {(k or '')[:120]}")
