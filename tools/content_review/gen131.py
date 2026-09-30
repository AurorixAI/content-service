import subprocess,re
o=['# -*- coding: utf-8 -*-\nS = "исправление записи ctrl130: литеральные \\\\n вместо переносов строк"\nP = {}\ndef E(t, why, **kw): P[t] = dict(src=S, why=why, **kw)\n']
for t in ["G11_TB_17_1*_17_3","G11_TB_17_1*_17_4","G11_TB_17_1*_17_5","G11_TB_17_1*_17_6"]:
    q=subprocess.check_output(["docker","exec","algo-content-db","psql","-U","algo","-d","algo_content","-At","-c","select question_latex from tasks_master where id='%s'"%t]).decode().rstrip("\n")
    q2=re.sub(r"\\n(?=[а-яё]\))","\n",q)
    assert "\\n" not in q2.replace("\\neq",""), t
    print(t, q.count("\\n"), "->", q2.count("\n"))
    o.append("E(%r, %r,\n  q=%r)\n"%(t,"восстановлены переносы строк между пунктами (при записи ctrl130 они стали литералами \\n)",q2))
open("specs/fix_ctrl131.py","w").write("\n".join(o))
