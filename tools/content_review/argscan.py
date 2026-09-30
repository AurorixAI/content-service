import psycopg2,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex,distractor_meta from tasks_master where is_active and question_latex like '%arg%' and (question_latex like '%z%')")
n=0
for i,q,k,d in cur.fetchall():
    n+=1
    print(i,'|',re.sub(r'\s+',' ',q)[:90],'| K',k,'| D',[x.get('value_latex') or x.get('value') for x in d or []])
print(n)
