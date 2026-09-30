import psycopg2,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,regexp_replace(question_latex,'\\s+',' ','g'),correct_answer_latex from tasks_master where is_active")
R=cur.fetchall()
print("== systems: plain 'solve the system' with non-pair key")
for i,q,k in R:
    if 'begin{cases}' in q and re.search(r'(Решите|Решить|Найдите решение)[^$]{0,60}систем',q) and not re.search(r'найдите (значение|сумм|произвед|количество)|укажите|запишите|определите|сколько',q,re.I):
        kk=(k or '')
        if not re.search(r'[;,]|решен|корн|\\varnothing|\\cup|<|>|\\leq|\\geq|\\le|\\ge|нет|бесконеч|любые|множеств|\\infty',kk) :
            print(i,'|',q[:90],'|',kk[:50])
print("== quadrant/point single coordinate")
for i,q,k in R:
    if re.search(r'четверт',q) and re.search(r'\b[A-Z]\(\s*-?\d+([.,]\d+)?\s*\)',q): print(i,'|',q[:110],'|',k)
print("== 'таблиц' without data")
n=0
for i,q,k in R:
    if re.search(r'таблиц',q,re.I) and not re.search(r'array|—|\||:\s*\$|=|\$[^$]*\d[^$]*\$[^$]*\$[^$]*\d',q) and len(q)<230:
        n+=1
        if n<=40: print(i,'|',q[:150])
print(n)
