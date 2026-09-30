import json,sys
n=sys.argv[1]
J=json.load(open(f'restore_J_{n}.json'))
items=J if isinstance(J,list) else J.get('tasks',J)
if isinstance(items,dict): items=[dict(id=k,**v) if isinstance(v,dict) else v for k,v in items.items()]
def walk(o,a):
    if isinstance(o,str): a.append(o)
    elif isinstance(o,dict): [walk(v,a) for v in o.values()]
    elif isinstance(o,list): [walk(v,a) for v in o]
out={}
for it in items:
    a=[]; walk(it,a); out[it.get('id') or it.get('task_id')]=a
json.dump(out,open(f'kx{n}.json','w'),ensure_ascii=False)
