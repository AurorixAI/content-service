# -*- coding: utf-8 -*-
"""Restore spec for simp_triage defects whose repair is proven numerically (repaired key == statement at random points).
Classes: exponent swallowed a variable (a^{3b} → a^{3}b) in the key or the statement; power of the denominator moved onto
the whole fraction in the key ((4c/a)^2 → 4c/a^2); mixed number shown as division in the statement (3 : 7/9 → 3 7/9)."""
import json, re, psycopg2

T = json.load(open("/audit/simp_triage.json"))
WHY = {
 "question_exponent_swallowed": "в условии переменная попала в показатель степени (например, a^{2b} вместо a^{2}b); восстановлено — с исправленным условием ключ совпадает численно",
 "key_exponent_swallowed": "в ключе переменная попала в показатель степени (например, a^{3b} вместо a^{3}b); исправлено — исправленный ключ численно равен выражению из условия",
 "both_exponent_swallowed": "в условии и ключе переменная попала в показатель степени; исправлено — после исправления ключ численно равен выражению из условия",
 "key_power_moved_out_of_fraction": "в ключе показатель степени знаменателя был вынесен на всю дробь ((4c/a)² вместо 4c/a²); исправлено — исправленный ключ численно равен выражению из условия",
 "question_mixed_number_as_division": "в условии смешанное число было записано как деление («3 : 7/9» вместо 3 7/9); восстановлено — с исправленным условием ключ совпадает численно",
}
def tidy(s):
    return re.sub(r"\((\\?[A-Za-z]|\d+)\)\^\{(\d+)\}", r"\1^{\2}", s)

c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
out = {}
for tid, r in T.items():
    if r["class"] not in WHY: continue
    c.execute("SELECT question_text, question_latex, correct_answer, correct_answer_latex, answer_options, answer_options_latex FROM tasks_master WHERE id=%s AND is_active", (tid,))
    row = c.fetchone()
    if not row: continue
    qt, ql, ca, cal, ao, aol = row
    f = {}
    if r.get("fixed_q"):
        if r["q"] not in ql: continue
        f["question_latex"] = ql.replace(r["q"], r["fixed_q"])
        if qt and r["q"] in qt: f["question_text"] = qt.replace(r["q"], r["fixed_q"])
    s = {"why": WHY[r["class"]], "source": "численная проверка ключа по условию 25.09 (simp_verify + simp_triage)", "fields": f}
    if r.get("fixed_key"):
        nk = tidy(r["fixed_key"])
        old = [x for x in (ca, cal) if x]
        f["correct_answer"] = nk; f["correct_answer_latex"] = nk
        if isinstance(ao, list) and ao:
            f["answer_options"] = [nk if (o in old) else o for o in ao]
            f["answer_options_latex"] = [nk if (o in old) else o for o in (aol or ao)]
            if nk not in f["answer_options"]:
                continue  # stored options do not carry the old key verbatim — leave for manual review
        s["expect_text"] = nk
    else:
        s["key_unchanged"] = True
    out[tid] = s
json.dump(out, open("/audit/restore_J_autofix1.json", "w"), ensure_ascii=False, indent=1)
print("tasks:", len(out))
