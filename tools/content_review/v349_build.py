# -*- coding: utf-8 -*-
"""Vilenkin 6, No. 349 (calculator programs with the exchange key ↔). The book (No. 700: program
«0,675 × 2,4 − 0,022 ÷ 3,995 ↔ =» computes 3,995 / (0,675·2,4 − 0,022)) shows that ↔ swaps the operands of the
pending operation. Stored keys ignored ↔ (and 349 а) was garbled); in 349 а) the «wrong» option 0,2·(2,9 − 0,82:0,4)
was the correct answer. Values: а) (2,9 − 2,05)·0,2 = 0,17; б) 3,5 : 1,4 = 2,5."""
import json, psycopg2

NOTE = r" (клавиша $\boxed{\leftrightarrow}$ меняет местами числа, над которыми выполняется действие)"
P = {
 "G6_TB_8_349.1": {
  "q": r"Значение какого выражения можно вычислить на микрокалькуляторе по программе $0{,}82\ \boxed{\div}\ 0{,}4\ \boxed{-}\ 2{,}9\ \boxed{\leftrightarrow}\ \boxed{\times}\ 0{,}2\ \boxed{=}$" + NOTE + "?",
  "k": r"$(2{,}9 - 0{,}82 : 0{,}4) \cdot 0{,}2$",
  "d": {1: (r"$(0{,}82 : 0{,}4 - 2{,}9) \cdot 0{,}2$", r"Не учтена клавиша $\boxed{\leftrightarrow}$: она меняет местами уменьшаемое и вычитаемое, поэтому вычисляется $2{,}9 - 0{,}82 : 0{,}4$, а не $0{,}82 : 0{,}4 - 2{,}9$.")}},
 "G6_TB_8_349.2": {
  "q": r"Значение какого выражения можно вычислить на микрокалькуляторе по программе $0{,}25\ \boxed{\times}\ 0{,}16\ \boxed{+}\ 1{,}36\ \boxed{\div}\ 3{,}5\ \boxed{\leftrightarrow}\ \boxed{=}$" + NOTE + "?",
  "k": r"$3{,}5 : (0{,}25 \cdot 0{,}16 + 1{,}36)$"},
}
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
out = {}
for tid, e in P.items():
    c.execute("SELECT distractor_meta, answer_options FROM tasks_master WHERE id=%s AND is_active", (tid,))
    dm, ao = c.fetchone()
    assert not ao, tid  # open-answer tasks: no stored options
    dm = [dict(d) for d in dm]
    for i, (v, w) in e.get("d", {}).items():
        dm[i] = {"value": v, "value_latex": v, "error_type": "misprint_fix_review", "plausibility": 0.7,
                 "error_logic": w, "error_logic_latex": w, "explanation": w, "explanation_latex": w}
    f = {"question_text": e["q"], "question_latex": e["q"], "correct_answer": e["k"], "correct_answer_latex": e["k"], "distractor_meta": dm}
    out[tid] = {"why": "ключ исправлен по учебнику (Виленкин 6, № 349; смысл клавиши ↔ — № 700: она меняет местами операнды действия); "
                       "прежний ключ не учитывал ↔, запись клавиши в условии была искажена («\\le ftrightarrow»); в 349 а) неверный вариант "
                       "$0{,}2\\cdot(2{,}9 - 0{,}82/0{,}4)$ был верным ответом — заменён прежним ключом",
                "source": "Виленкин 6 (OCR gemini_a1977d3a58a1e322, стр. 53–56, 110–116)", "expect_text": e["k"], "fields": f}
json.dump(out, open("/audit/restore_J_v349.json", "w"), ensure_ascii=False, indent=1)
print("tasks:", len(out))
