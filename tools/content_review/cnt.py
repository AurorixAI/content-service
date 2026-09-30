import psycopg2,re,collections
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,length(question_latex)+length(correct_answer_latex) from tasks_master where is_active")
cnt=collections.Counter(); ln=collections.Counter()
for i,l in cur.fetchall():
    m=re.match(r'^(?:GEN_|DIFF_|ds_llm_)?G?(\d+)',i)
    g='ds_llm' if i.startswith('ds_llm') else (('GEN'+m.group(1)) if i.startswith('GEN_') and m else (('DIFF'+m.group(1)) if i.startswith('DIFF_') and m else (m.group(1) if m else 'other')))
    cnt[g]+=1; ln[g]+=l
for g,n in sorted(cnt.items(),key=lambda x:-x[1]): print(g,n,ln[g]//n)
