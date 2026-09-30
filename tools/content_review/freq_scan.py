import psycopg2,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex from tasks_master where is_active and correct_answer_latex ~ 'M\\s*:'")
for i,q,k in cur.fetchall():
    m=re.search(r'M\s*:\s*([\d,\s]+)',k)
    if not m: continue
    M=[int(x) for x in re.findall(r'\d+',m.group(1))]
    n=re.findall(r'\$(\d+)\$\s*(?:компан|дн|учен|человек|измер|бросан|раз|наблюд)',q)
    print(i,sum(M),n[:2],'|',q[:80].replace('\n',' '))
