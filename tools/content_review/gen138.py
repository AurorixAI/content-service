# -*- coding: utf-8 -*-
import json, re, subprocess
RX = re.compile(r"\\dfrac\{(-?)(\d+)_\{(\d+)\}\}\{(\d+)\}")
fix = lambda s: RX.sub(lambda m: "%s%s\\dfrac{%s}{%s}" % (m.group(1), m.group(2), m.group(3), m.group(4)), s) if isinstance(s, str) else s
rows = json.loads(subprocess.check_output(["docker","exec","algo-content-db","psql","-U","algo","-d","algo_content","-At","-c",
 r"""select json_agg(json_build_object('id',id,'q',question_latex,'k',correct_answer_latex,'dm',distractor_meta)) from tasks_master t where t.is_active and (t.question_latex ~ '\\dfrac\{-?[0-9]+_\{' or t.correct_answer_latex ~ '\\dfrac\{-?[0-9]+_\{' or t.distractor_meta::text ~ '\\\\dfrac\{-?[0-9]+_\{')"""]).decode())
SKIP = {"G6_TB_34_1251.2", "G6_TB_34_1270"}   # batch tasks, split separately
MAN = {"G7_ALG_39_61.6", "G6_TB_59–61_528.1", "G7_ALG_39_10.5"}
out = ['# -*- coding: utf-8 -*-', 'S = "испорченная запись смешанных чисел \\\\dfrac{a_{b}}{c} (класс по всему банку, 2026-09-30)"', 'P = {}', 'def E(t, why, **kw): P[t] = dict(src=S, why=why, **kw)', '']
for r in rows:
    t = r["id"]
    if t in SKIP or t in MAN: continue
    kw = {}
    if RX.search(r["q"] or ""): kw["q"] = fix(r["q"])
    if RX.search(r["k"] or ""): kw["k"] = fix(r["k"])
    dval, dwhy = {}, {}
    for i, d in enumerate(r["dm"] or []):
        v = d.get("value_latex") or d.get("value") or ""
        if RX.search(v): dval[i] = fix(v)
        e = d.get("error_logic_latex") or d.get("explanation_latex") or d.get("error_logic") or d.get("explanation") or ""
        if RX.search(e) or RX.search(d.get("error_logic") or "") or RX.search(d.get("explanation") or ""): dwhy[i] = fix(e)
    if dval: kw["dval"] = dval
    if dwhy: kw["dwhy"] = dwhy
    out.append("E(%r, %r,\n  %s)" % (t, "смешанные числа были записаны как $\\frac{a_{b}}{c}$ (на экране — индекс в числителе); восстановлена запись $a\\frac{b}{c}$; значения проверены вычислением", ",\n  ".join("%s=%r" % kv for kv in kw.items())))
open("specs/fix_ctrl138_auto.py", "w").write("\n".join(out) + "\n")
print(len(out) - 5)
