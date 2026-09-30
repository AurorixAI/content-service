import psycopg2,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,regexp_replace(question_latex,'\\s+',' ','g'),correct_answer_latex from tasks_master where is_active and question_latex ~* 'иррациональност'")
for i,q,k in cur.fetchall():
    bad = re.search(r'\^\{\\frac|\^\{\\dfrac|\^\{\d/\d\}',k or '') or re.search(r'\\dfrac\{[^{}]*\}\{[^{}]*\\sqrt',k or '')
    print(('BAD ' if bad else 'ok  '),i,'|',q[-70:],'|',k)
