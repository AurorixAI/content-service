import psycopg2,json,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
bad=json.load(open('reatt_bad.json'))
NEUT="Этот вариант неверен: он получается из-за ошибки в вычислениях или в применении правила и не совпадает с правильным ответом."
def outside(s):
    s=re.sub(r'\$\$.*?\$\$','',str(s or ''),flags=re.S); return re.sub(r'\$.*?\$','',s,flags=re.S)
def probs(s):
    s=str(s or ''); out=[]
    t=s.replace('\\$','')
    if t.count('$')%2: out.append('odd$')
    if re.search(r'\$\d+\$[.,]\$\d',s): out.append('splitdec')
    if re.search(r'\\[a-zA-Z]{2,}|[\^_]\{|\{,\}',outside(s)): out.append('latex_outside')
    if re.search(r'(?<!\\)\bsqrt\[|(?<!\\)\bsqrt\{|(?<!\\)\bfrac\{',s): out.append('nobackslash')
    return out
def fixdec(s):
    s=re.sub(r'\$(-?~?\d+)\$([.,])\$(\d+)\$',lambda m:'$'+m.group(1)+'{,}'+m.group(3)+'$',s)
    s=re.sub(r'\$(-?~?\d+)\$([.,])(\d+)(?!\d)',lambda m:'$'+m.group(1)+'{,}'+m.group(3)+'$',s)
    return s
nrm=lambda s: re.sub(r'\s|\$|\\left|\\right|\\,','',str(s or '')).replace('\\dfrac','\\frac').replace('{,}',',')
FORCE={'G10_TB_1_3_3_2','G10_TB_§10_10_1_3','G11_TB_§18_10_1','G11_TB_§4_5_4','G5_TB_32_1201.5','G6_TB_23_927.4','ds_llm_1d661655d570','ds_llm_f67cdf27f13e'}
P={};left=[]
for tid in bad:
    cur.execute("select question_text,question_latex,correct_answer,correct_answer_latex,distractor_meta from tasks_master where id=%s",(tid,))
    qt,ql,ca,cal,dm=cur.fetchone(); e={}
    def salvage(raw,lat):
        r=fixdec(str(raw or ''))
        if not probs(r): return r
        if tid in FORCE and lat and not probs(lat): return lat
        if lat and not probs(lat) and nrm(lat)==nrm(raw): return lat
        if lat and not probs(lat) and nrm(fixdec(str(lat)))==nrm(r): return lat
        return None
    if probs(qt):
        v=salvage(qt,ql)
        if v is None: left.append((tid,'q',str(qt)[:120]))
        elif v!=qt: e['q']=v
    if tid=='G11_TB_§18_10_2':
        e['k']=r'б) $(-\infty; 0) \cup [e; +\infty)$; в) при $a < 0$ — $1$ корень, при $0 \leq a < e$ — $0$ корней, при $a = e$ — $1$ корень, при $a > e$ — $2$ корня'
    elif probs(ca):
        v=salvage(ca,cal)
        if v is None: left.append((tid,'a',str(ca)[:120]))
        elif v!=ca: e['k']=v
    dval={};dwhy={}
    for i,x in enumerate(dm or []):
        val=x.get('value'); vl=x.get('value_latex')
        if probs(val):
            v=salvage(val,vl)
            if v is None: left.append((tid,f'dv{i}',str(val)[:120]))
            elif v!=val: dval[i]=v
        ex=x.get('explanation')
        if probs(ex):
            r=fixdec(str(ex))
            dwhy[i]=r if not probs(r) else NEUT
    if dval: e['dval']=dval
    if dwhy: e['dwhy']=dwhy
    if e: P[tid]=e
print(len(P),'tasks;',len(left),'unresolved')
for l in left[:25]: print(l)
json.dump({t:{k:({str(a):b for a,b in v.items()} if isinstance(v,dict) else v) for k,v in e.items()} for t,e in P.items()},open('gen14.json','w'),ensure_ascii=False)
src='''# -*- coding: utf-8 -*-
import json
S = "ручная проверка отображения (вместо повторной аттестации): исправлены разорванные десятичные дроби, потерянные обратные слэши и разметка $ в условиях, ключах, вариантах и объяснениях; неисправимые объяснения заменены нейтральными (30.09)"
P = {}
for t, e in json.load(open("/audit/gen14.json")).items():
    d = dict(src=S, why="исправлено отображение сырого текста, у которого после исправления содержимого нет подтверждённого LaTeX-отображения (разорванные десятичные, потерянные слэши, неправильная разметка $)")
    if "q" in e: d["q"] = e["q"]
    if "k" in e: d["k"] = e["k"]
    if "dval" in e: d["dval"] = {int(a): b for a, b in e["dval"].items()}
    if "dwhy" in e: d["dwhy"] = {int(a): b for a, b in e["dwhy"].items()}
    P[t] = d
'''
open('fix_ctrl14.py','w').write(src)
