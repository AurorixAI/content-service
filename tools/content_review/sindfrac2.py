import psycopg2,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex,distractor_meta from tasks_master where is_active and (question_latex like '%dfrac%' or correct_answer_latex like '%dfrac%')")
for i,q,k,d in cur.fetchall():
    for lab,s in [('Q',q),('K',k)]:
        for m in re.finditer(r'\\(?:sin|cos|tan|tg|ctg|arcsin|arctg|arctan)\s*\\dfrac\{([^{}]+)\}\{([^{}]+)\}',s or ''):
            a,b=m.group(1).replace(' ',''),m.group(2).replace(' ','')
            if a==b or re.fullmatch(r'\d*[a-z]',a) and a==b:
                print(i,lab,'|',re.sub(r'\s+',' ',s)[:140]); break
