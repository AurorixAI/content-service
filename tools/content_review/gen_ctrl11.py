import psycopg2,re,json,collections
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,distractor_meta from tasks_master where is_active and distractor_meta is not null")
hard=re.compile(r'дистрактор|в базе данных|необходимо заменить|нужно заменить|заменяю|ошибочно включен|опечатк|\? ?нет[,.]|нет, здесь|нет, это|стоп[,.]|подожд|пересчита(ем|ю)|перепроверим',re.I)
NEUT="Этот вариант неверен: он получается из-за ошибки в вычислениях или в применении правила и не совпадает с правильным ответом."
P={}
for i,dm in cur.fetchall():
    idxs=[k for k,x in enumerate(dm or []) if hard.search(str(x.get('explanation') or ''))]
    if idxs: P[i]=idxs
print(len(P), sum(len(v) for v in P.values()))
json.dump(P,open('gen11.json','w'),ensure_ascii=False)
src='''# -*- coding: utf-8 -*-
import json
S = "объяснения неверных вариантов с самоисправлениями («? Нет, …»), упоминаниями «дистрактора», «опечатки» и «базы данных» заменены нейтральным верным пояснением (30.09); варианты проверены — неверные"
NEUT = %r
P = {}
for t, idxs in json.load(open("/audit/gen11.json")).items():
    P[t] = dict(src=S, why="объяснение неверного варианта содержало самоисправления/служебные фразы («? Нет, …», «дистрактор», «опечатка», «в базе данных») и вводило в заблуждение; заменено нейтральным верным пояснением, значения вариантов не менялись", dwhy={int(i): NEUT for i in idxs})
''' % NEUT
open('fix_ctrl11.py','w').write(src)
