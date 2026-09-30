import psycopg2,re,json
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex,distractor_meta from tasks_master where is_active and distractor_meta is not null")
pat=re.compile(r'дистрактор|в базе данных|ошибочно включен|необходимо заменить|нужно заменить|заменяю|опечатк|может быть дистр|это правильный ответ|правильный ответ, но|на самом деле (верн|правиль)|\? ?нет[,.]|нет, здесь|нет, это|стоп|подожд|перепроверим|пересчита(ем|ю)|hmm|wait|Ошибочно включена|ответ (на самом деле )?верен|не может быть неверн',re.I)
out={}
for i,q,k,dm in cur.fetchall():
    for idx,x in enumerate(dm or []):
        e=str(x.get('explanation') or '')+' '+str(x.get('error_logic') or '')
        m=pat.search(e)
        if m: out.setdefault(i,[]).append((idx,m.group(0)))
print(len(out), sum(len(v) for v in out.values()))
json.dump(out,open('meta2_ids.json','w'),ensure_ascii=False)
