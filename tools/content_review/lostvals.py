import psycopg2,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex from tasks_master where is_active and correct_answer_latex ~ '^\\$?\\s*-?[0-9][0-9{},. ]*\\$?$' and question_latex ~ '(Найдите|Вычислите|Чему равно|Определите)'")
n=0;out=[]
for i,q,k in cur.fetchall():
    if re.search(r'=|если|при |где|при\s|\\in|<|>|≤|≥|\\le|\\ge',q or ''): continue
    ms=re.findall(r'\$([^$]+)\$',q)
    if len(ms)!=1: continue
    t=re.sub(r'\\(sin|cos|tg|ctg|tan|cot|log|lg|ln|sqrt|frac|dfrac|cdot|left|right|operatorname|text|mathbb|pi|arcsin|arccos|arctg|arcctg|circ|ldots|dots)\b','',ms[0])
    letters=set(re.findall(r'(?<![a-zA-Z\\])([a-zA-Z])(?![a-zA-Z])',t))
    if letters and not re.search(r'дл[ая]|значени[ея]?\s+(?:выражения|функции)?',q) or (letters and re.search(r'^Найдите (?:значение )?(?:произведение|сумму|разность|частное)',q)):
        out.append((i,re.sub(r'\s+',' ',q)[:100],k))
print(len(out))
for o in out[:60]: print(o)
