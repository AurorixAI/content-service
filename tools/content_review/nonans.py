import psycopg2,re,collections,json
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex,distractor_meta,answer_options from tasks_master where is_active and distractor_meta is not null")
pat=re.compile(r'^\s*(неверно|верно|нельзя однозначно ответить без вычисления|нельзя однозначно ответить|ответ неверный)\s*\.?\s*$',re.I)
cnt=collections.Counter(); ids=[]
for i,q,k,dm,ao in cur.fetchall():
    hits=[idx for idx,x in enumerate(dm or []) if pat.match(str(x.get('value') or x.get('value_latex') or ''))]
    if hits: ids.append((i,hits,len(dm))); cnt[i.rsplit('_',1)[0][:18]]+=1
print(len(ids)); print(cnt.most_common(10))
only=[i for i,h,n in ids if len(h)==n]
print('all distractors are non-answers:',len(only))
json.dump(ids,open('nonans.json','w'))
