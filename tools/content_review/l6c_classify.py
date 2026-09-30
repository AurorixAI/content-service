import json, sys
sys.path.insert(0, "/audit")
import importlib.util
spec_ = importlib.util.spec_from_file_location("l6c", "/audit/l6c_build.py")
src = open("/audit/l6c_build.py").read().split("c = psycopg2.connect")[0]
ns = {}; exec(src, ns); n = ns["n"]
import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
S = json.load(open("/audit/restore_J_L6c.json"))
c.execute("SELECT id, correct_answer, correct_answer_latex, distractor_meta FROM tasks_master WHERE id = ANY(%s)", (list(S),))
a = b = 0
for tid, ca, cal, dm in c.fetchall():
    ks = {n(ca), n(cal)}
    for d in dm:
        if not isinstance(d, dict): continue
        rv, lv = d.get("value"), d.get("value_latex")
        if (rv is not None and n(rv) in ks):
            a += 1
        elif lv is not None and n(lv) in ks:
            b += 1; print("B", tid, "| raw:", rv, "| latex:", lv, "| key:", cal)
print("raw-equal:", a, "latex-only-equal:", b)
