import psycopg2,re,json
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,regexp_replace(question_latex,'\\s+',' ','g'),correct_answer_latex from tasks_master where is_active and question_latex ~* '(на рисунк|рис\\.|изображ|на плане|чертеж|на диаграмм|по диаграмм|на графике|по графику|по рисунку|по таблице|показан[ыао]? на)'")
rows=cur.fetchall(); print(len(rows))
json.dump([r[0] for r in rows],open('fig_ids.json','w'))
for i,q,k in rows: print(f"{i} | {q[:230]} | K: {(k or '')[:60]}")
