import psycopg2,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex from tasks_master where is_active and question_latex like '%dfrac%'")
pat=re.compile(r'\\(?:sin|cos|tg|ctg|operatorname\{tg\}|operatorname\{ctg\})\s*\\dfrac\{([^{}]*)\}\{([^{}]*[a-zA-Z][^{}]*)\}')
for i,q,k in cur.fetchall():
    m=pat.search(q or '')
    if m and not re.fullmatch(r'\s*\\pi\s*|\s*\d+\s*\\pi\s*',m.group(1)) :
        # skip when numerator is pi-multiple and denominator is a number handled above (letters required in denominator)
        print(i,'|',re.sub(r'\s+',' ',q)[:130],'| K',(k or '')[:60])
