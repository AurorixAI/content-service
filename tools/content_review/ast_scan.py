import psycopg2,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex from tasks_master where is_active and (question_latex ~ '[{ ]ast[} ]' or question_latex ~ '\\\\\\\\\\\\\\\\dfrac' or question_latex ~ 'text\\{ha\\}')")
for i,q in cur.fetchall(): print(i,'|',q[:120].replace('\n',' '))
