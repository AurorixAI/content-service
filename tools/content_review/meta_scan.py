import psycopg2,re,json,collections
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,distractor_meta from tasks_master where is_active and distractor_meta is not null")
pat=re.compile(r'дистрактор|в базе данных|ошибочно включен|необходимо заменить|нужно заменить|это правильный ответ|является правильным ответом|на самом деле (верн|правиль)|фактически (верн|правиль)|верный ответ, но|правильный ответ, но|не является ошибкой|не является неверн|не является грубой|эквивалентн\w+,? но|что не является|тоже (верн|правильн)|также (верн|правильн)\w* (ответ|вариант)|вариант (верен|правилен)|является верным|является правильным',re.I)
hits=[]
for i,dm in cur.fetchall():
    for idx,x in enumerate(dm or []):
        e=str(x.get('explanation') or '')+' '+str(x.get('error_logic') or '')
        m=pat.search(e)
        if m: hits.append((i,idx,m.group(0),e[:170]))
print(len(hits), len(set(h[0] for h in hits)))
print(collections.Counter(h[2].lower() for h in hits).most_common(15))
json.dump(hits,open('meta_hits.json','w'),ensure_ascii=False)
for h in hits[:45]: print(h)
