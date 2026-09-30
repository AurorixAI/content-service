import subprocess,json,re
q="select id, correct_answer_latex, distractor_meta::text from tasks_master where is_active and question_latex ~* '(возраст|убыва|монотон)'"
out=subprocess.check_output(["docker","exec","algo-content-db","psql","-U","algo","-d","algo_content","-At","-F","\x1f","-c",q]).decode()
def norm(s): return re.sub(r"[\[\]\(\)]|\\left|\\right|\s","",s)
n=0
for line in out.splitlines():
    p=line.split("\x1f")
    if len(p)<3: continue
    tid,k,dm=p
    try: d=json.loads(dm)
    except: continue
    vals=[x.get("value") or x.get("latex") or "" for x in (d if isinstance(d,list) else d.get("distractors",[]))] if d else []
    for v in vals:
        if v and v!=k and norm(v)==norm(k):
            n+=1; print(tid,"| K:",k[:90],"| D:",v[:90])
print("total",n)
