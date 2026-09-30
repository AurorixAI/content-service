# -*- coding: utf-8 -*-
"""Build specs/fix_ctrl136.py: displayed dot-decimals -> comma, context references to other exercises,
garbled 'find a number between' tasks, broken keys found by the full-bank LaTeX census (2026-09-30).
Strings are written with %r (never r%r)."""
import json, re, subprocess

def q(sql):
    return subprocess.check_output(["docker", "exec", "algo-content-db", "psql", "-U", "algo", "-d", "algo_content", "-At", "-c", sql]).decode()

rows = json.loads(q("""select coalesce(json_agg(json_build_object('id',t.id,'dm',t.distractor_meta,'q',t.question_latex)),'[]') from tasks_master t
 where t.is_active and exists (select 1 from jsonb_array_elements(case when jsonb_typeof(t.distractor_meta)='array' then t.distractor_meta else '[]' end) d
 where d->>'value_latex' ~ '(^|[^\\\\a-z])[0-9]+[.][0-9]')"""))
SKIP = {"G5_TB_2_25",            # task is about digit grouping; dotted groups are the intended wrong notation
        "G11_TB_6_4_6_28_1", "G8_TB_10_270",           # rewritten by hand below
        "G5_TB_31_1183.2", "G5_TB_31_1183.6", "G6_TB_25_1012.3"}  # garbled, rewritten by hand below
DEC = re.compile(r"(?<![\d.])(\d+)\.(\d+)(?![\d.])")

def in_math(s):
    return re.sub(r"\$[^$]*\$", lambda m: DEC.sub(r"\1{,}\2", m.group(0)), s)

def plain(s):
    def num(m):
        a = m.group(0)
        if "." in a:
            i, f = a.split("."); return "$%s{,}%s$" % (i, f)
        if len(a) >= 5:
            return "$" + "{:,}".format(int(a)).replace(",", "\\,") + "$"
        return "$%s$" % a
    return re.sub(r"(?<![\d.])\d+(?:\.\d+)?(?![\d.])", num, s)

P = {}
for r in rows:
    if r["id"] in SKIP: continue
    dval = {}
    for i, d in enumerate(r["dm"]):
        v = d.get("value_latex") or ""
        if not re.search(r"(^|[^\\a-z])[0-9]+[.][0-9]", v): continue
        nv = in_math(v) if "$" in v else plain(v)
        if nv != v: dval[i] = nv
    if dval: P[r["id"]] = dval

out = ['# -*- coding: utf-8 -*-',
       'S = "перепись показываемого LaTeX (2026-09-30): десятичные с точкой → запятая; ссылки на другие задания; испорченные значения"',
       'P = {}', 'def E(t, why, **kw): P[t] = dict(src=S, why=why, **kw)', '']
for tid, dval in sorted(P.items()):
    out.append("E(%r, %r,\n  dval=%r)" % (tid, "десятичная дробь в неверном варианте была записана с точкой (в банке и учебниках — запятая); только оформление, значение не менялось", dval))
open("specs/fix_ctrl136_auto.py", "w").write("\n".join(out) + "\n")
for tid, dval in sorted(P.items()):
    for i, v in dval.items():
        old = [d.get("value_latex") for r in rows if r["id"] == tid for d in r["dm"]][i]
        print(tid, i, "|", old[:90], "=>", v[:90])
print("tasks", len(P))
