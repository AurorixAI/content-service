import json, re, subprocess
from collections import Counter
q = r"""SELECT json_build_object('id',id,'q',question_latex,'k',correct_answer_latex,'dm',distractor_meta,
 'rev', EXISTS (SELECT 1 FROM jsonb_object_keys(tags) k WHERE k LIKE 'content_repair::manual-review-2026-09-2%-proof-%'))
 FROM tasks_master WHERE is_active AND question_latex ~* '(докаж|доказать|обоснуй|покажите,? что|объясните|выведите формулу|верно ли, что)'"""
rows=[json.loads(l) for l in subprocess.run(["docker","exec","algo-content-db","psql","-U","algo","-d","algo_content","-At","-c",q],capture_output=True,text=True).stdout.strip().split("\n")]
aud={x["id"]:x for x in json.load(open("proofs_audit.json"))}
def vis(s): return re.sub(r"\\[a-zA-Z]+|[{}$^_\\]","",s or "")
def words(s): return len(re.findall(r"[А-Яа-яЁё]{3,}", re.sub(r"\$[^$]*\$"," ",s or "")))
BARE=re.compile(r"^\W*(тождество |равенство |неравенство |утверждение )?(доказано|доказательство( тождества| методом математической индукции| по определению предела функции| с использованием.*)?)\W*$",re.I)
c=Counter(); bad=[]
for r in rows:
    k=r["k"] or ""; ds=[str(d.get("value_latex") or d.get("value") or "") for d in (r["dm"] or []) if isinstance(d,dict)]
    probs=[]
    if BARE.match(k.replace("$","")): probs.append("key_bare_Доказано")
    if words(k)>=3 and ds and sum(words(d)==0 for d in ds)>=2: probs.append("formula_distractors_vs_argument_key")
    if len(ds)<2 and not re.fullmatch(r"\W*(да|нет|верно|неверно)\W*",k.strip("$ ").lower()): probs.append("lt2_distractors")
    if len(vis(k))>600: probs.append("key_very_long")
    was=aud.get(r["id"],{}).get("cat")
    grp=("reviewed" if r["rev"] else "not_reviewed")+"/"+("was_problem" if was=="PROBLEM" else "was_ok" if was else "not_in_audit")
    c[grp]+=1
    for p in probs: c[grp+" :: "+p]+=1; bad.append((r["id"],grp,p))
for k,v in sorted(c.items()): print(f"{v:5}  {k}")
json.dump(bad,open("proofs_after_bad.json","w"),ensure_ascii=False,indent=1)
