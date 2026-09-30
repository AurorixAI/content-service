import psycopg2,re,json
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,distractor_meta from tasks_master where is_active and distractor_meta is not null")
def clean(s):
    o=s
    s=s.replace('неверный знак сравнения (вместо закрытого варианта)','Ученик поставил неверный знак сравнения.')
    s=re.sub(r"\$'\$\s*(да|нет)\s*\$'\$",r"«\1»",s)
    s=re.sub(r"\$\\text\{(да|нет)\}\$",r"«\1»",s)
    return s
P={}
for i,dm in cur.fetchall():
    dw={}
    for idx,x in enumerate(dm or []):
        s=str(x.get('error_logic') or x.get('explanation') or '')
        n=clean(s)
        if n!=s: dw[idx]=n
    if dw: P[i]=dw
print(len(P),sum(len(v) for v in P.values()))
json.dump(P,open('gen17.json','w'),ensure_ascii=False)
open('fix_ctrl17.py','w').write('''# -*- coding: utf-8 -*-
import json
S = "косметика объяснений неверных вариантов: служебная фраза «(вместо закрытого варианта)» и испорченные кавычки $'$ да $'$ (30.09)"
P = {t: dict(src=S, why="в объяснении неверного варианта была служебная фраза или испорченная разметка кавычек; текст приведён к нормальному виду, значения вариантов не менялись", dwhy={int(a): b for a, b in d.items()}) for t, d in json.load(open("/audit/gen17.json")).items()}
''')
