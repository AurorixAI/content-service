import psycopg2,re,json,collections
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,correct_answer_latex,distractor_meta from tasks_master where is_active and distractor_meta is not null")
hard=re.compile(r'дистрактор|в базе данных|необходимо заменить|нужно заменить|заменяю|ошибочно включен|опечатк|ответ (в ключе|ключа)|по ключу|\? ?нет[,.]|нет, здесь|нет, это|стоп[,.]|подожд|пересчита(ем|ю)|перепроверим',re.I)
cnt=collections.Counter(); hits=[]
for i,k,dm in cur.fetchall():
    for idx,x in enumerate(dm or []):
        e=str(x.get('explanation') or '')
        m=hard.search(e)
        if m: cnt[m.group(0).lower()]+=1; hits.append((i,idx,m.group(0),e))
print(len(hits),len(set(h[0] for h in hits))); print(cnt.most_common())
json.dump(hits,open('meta3_hits.json','w'),ensure_ascii=False)
for h in hits[:25]: print(h[0],h[1],'|',h[3][:260].replace('\n',' '))
