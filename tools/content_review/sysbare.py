import psycopg2,re,json
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex,distractor_meta from tasks_master where is_active and question_latex like '%begin{cases}%'")
bare=re.compile(r'^\s*\$?\s*-?\d+([.,]\d+|\{,\}\d+)?\s*\$?\s*$')
rows=[r for r in cur.fetchall() if r[2] and bare.match(r[2])]
print(len(rows))
import collections
print(collections.Counter(r[0].rsplit('_',1)[0][:22] for r in rows).most_common(15))
json.dump([r[0] for r in rows],open('sysbare_ids.json','w'))
for r in rows[:8]: print(r[0], r[1][:100].replace('\n',' '), '|', r[2])
