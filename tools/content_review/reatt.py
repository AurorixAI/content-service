import psycopg2,json,re,collections
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("""select a.task_id, array_agg(distinct a.field_key), max(a.revoked_at), max(a.revocation_reason)
 from task_latex_display_attestations a join tasks_master t on t.id=a.task_id
 where a.status='revoked' and t.is_active
   and not exists (select 1 from task_latex_display_attestations b where b.task_id=a.task_id and b.field_key=a.field_key and b.status='active')
 group by a.task_id""")
rows=cur.fetchall(); print('tasks with revoked, no active replacement:',len(rows))
cnt=collections.Counter(re.sub(r'.*content repair ','',r[3] or '')[:22] for r in rows)
print(cnt.most_common(12))
json.dump([r[0] for r in rows],open('reatt_ids.json','w'))
# mismatch raw vs latex
nrm=lambda s: re.sub(r'\s+','',str(s or '')).replace('\\dfrac','\\frac')
mm=[]
for tid,fields,_,_ in rows:
    cur.execute("select question_text,question_latex,correct_answer,correct_answer_latex,answer_options,answer_options_latex,distractor_meta from tasks_master where id=%s",(tid,))
    qt,ql,ca,cal,ao,aol,dm=cur.fetchone()
    issues=[]
    if nrm(qt)!=nrm(ql): issues.append('question')
    if nrm(ca)!=nrm(cal): issues.append('answer')
    for i,x in enumerate(dm or []):
        if nrm(x.get('value'))!=nrm(x.get('value_latex')): issues.append(f'dvalue{i}')
    if ao and aol and [nrm(v) for v in ao]!=[nrm(v) for v in aol]: issues.append('options')
    # broken markup in raw
    for name,val in [('question',qt),('answer',ca)]:
        if str(val or '').count('$')%2: issues.append(name+'_odd$')
        if re.search(r'\$\d+\$[.,]\$\d',str(val or '')): issues.append(name+'_splitdec')
    if issues: mm.append((tid,issues))
print('display issues:',len(mm)); print(mm[:40])
json.dump(mm,open('reatt_issues.json','w'))
