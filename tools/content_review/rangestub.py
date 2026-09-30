import psycopg2,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,regexp_replace(question_latex,'\\s+',' ','g'),correct_answer_latex,is_active from tasks_master where question_latex ~ '\\$\\(\\d+\\s*[-–]\\s*\\d+\\)\\$' and length(question_latex)<80")
for r in cur.fetchall(): print(r[3],r[0],'|',r[1],'|',(r[2] or '')[:50])
