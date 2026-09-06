import psycopg2
import json
import re
import sys

sys.path.insert(0, '/Users/arslan/Desktop/ALGO/content-service')
from scripts.backfill_latex_deepseek import (
    final_display_issues,
    latex_status_from_issues,
    validate_display_contract,
    validate_professional_latex,
    validate_with_katex,
    _json_list
)

conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
cur = conn.cursor()

def sanitize_and_fix(tid: str, qt: str, ql: str, ca: str, cal: str, dm: list):
    # 1. ds_llm_4f91d75f76fc
    if tid == 'ds_llm_4f91d75f76fc':
        ql = (
            "Докажите, что система неравенств\n"
            "$$\\begin{cases}\n"
            "\\dfrac{2x-1}{3} - \\dfrac{x+2}{2} \\le 1 \\\\\n"
            "3(2-x) - 4(x+1) < -2x - 10\n"
            "\\end{cases}$$\n"
            "имеет решение, и запишите его в виде числового промежутка."
        )
        cal = r'$x \in \left(-\dfrac{12}{5}; 14\right]$'

    # 2. G11_TB_6_3_6_20_a
    if tid == 'G11_TB_6_3_6_20_a':
        ql = r'Найдите неопределённый интеграл: $$\int \dfrac{x}{\sqrt{a^{2} - x^{2}}} \, dx$$'
        cal = r'$-\sqrt{a^{2} - x^{2}} + C$'
        
    # 3. G11_TB_6_3_6_20_б
    if tid == 'G11_TB_6_3_6_20_б':
        ql = r'Найдите неопределённый интеграл: $$\int \dfrac{x}{\sqrt{4 - x^{2}}} \, dx$$'
        cal = r'$-\sqrt{4 - x^{2}} + C$'

    # 4. G10_TB_§8_8_1_2
    if tid == 'G10_TB_§8_8_1_2':
        ql = r'Имеет ли смысл запись: $\sqrt[3]{-2}$?'
        cal = 'Да, имеет'

    def clean_text_field(s: str) -> str:
        if not s:
            return s
        res = str(s).strip()
        # Замена спецсимволов
        res = res.replace('≥', r'\ge').replace('≤', r'\le').replace('≠', r'\ne')
        res = res.replace('±', r'\pm').replace('×', r'\cdot').replace('·', r'\cdot')
        res = res.replace(r'\leqslant', r'\le').replace(r'\geqslant', r'\ge')
        res = res.replace(r'\pik', r'\pi k')
        res = res.replace('²', '^{2}').replace('³', '^{3}')
        # Вынос \lim и \int в блочные формулы
        res = re.sub(r'(?<!\$)\$(?!\$)\s*(\\lim[^\$]+)\s*(?<!\$)\$(?!\$)', r'$$\1$$', res)
        res = re.sub(r'(?<!\$)\$(?!\$)\s*(\\int[^\$]+)\s*(?<!\$)\$(?!\$)', r'$$\1$$', res)
        res = re.sub(r'(?<!\$)\$(?!\$)\s*(?:[0-9a-zA-Zа-яА-Я][.)]?\s*)?(\\begin\{cases\}[\s\S]+?\\end\{cases\})\s*(?<!\$)\$(?!\$)', r'$$\1$$', res)
        
        # Исправление степеней и дробей внутри $...$
        def repl_inner(m):
            c = m.group(1).replace('$', '')
            c = re.sub(r'\\frac(?![A-Za-z])', r'\\dfrac', c)
            c = re.sub(r'(\^|_)([0-9a-zA-Z])(?![{0-9a-zA-Z])', r'\1{\2}', c)
            c = re.sub(r'([0-9a-zA-Z\\{}()]+)\s*/\s*([0-9a-zA-Z\\{}()]+)', r'\\dfrac{\1}{\2}', c)
            c = re.sub(r'(?<!\\)\b(sin|cos|tan|cot|tg|ctg|log|ln)\b', r'\\\1', c)
            c = c.replace('α', r'\alpha').replace('β', r'\beta').replace('γ', r'\gamma').replace('π', r'\pi')
            return f'${c}$'
        res = re.sub(r'\$([^$]+)\$', repl_inner, res)
        return res

    def clean_math_value(s: str) -> str:
        if not s:
            return s
        res = clean_text_field(s)
        # Если это двойные $$ в значении опции, делаем одинарные $
        if res.startswith('$$') and res.endswith('$$'):
            res = '$' + res[2:-2].strip() + '$'
        elif not res.startswith('$') and not res.endswith('$'):
            if re.fullmatch(r'[0-9a-zA-Z\s+\-*×·/=<>≤≥≠(),.;:^{}\\_]+', res):
                res = f"${res}$"
        # Склейка раздельных долларов
        if re.fullmatch(r'\$[^$]+\$(?:[;,]\s*\$[^$]+\$)+', res):
            parts = re.findall(r'\$([^$]+)\$', res)
            sep = '; ' if ';' in res else ', '
            res = '$' + sep.join(p.strip() for p in parts) + '$'
        return res

    new_ql = clean_text_field(ql or qt or '')
    new_cal = clean_math_value(cal or ca or '')
    
    new_dm = []
    for d in dm:
        if not isinstance(d, dict):
            continue
        d_c = dict(d)
        d_c['value_latex'] = clean_math_value(d_c.get('value_latex') or d_c.get('value') or '')
        
        desc = d_c.get('error_logic_latex') or d_c.get('explanation_latex') or d_c.get('error_logic') or d_c.get('explanation') or ''
        d_c['error_logic_latex'] = clean_text_field(desc)
        d_c['explanation_latex'] = clean_text_field(desc)
        new_dm.append(d_c)
        
    return new_ql, new_cal, new_dm

cur.execute("""
    SELECT id, question_text, question_latex, correct_answer,
           correct_answer_latex, distractor_meta, answer_options,
           answer_options_latex
    FROM tasks_master
    WHERE latex_status = 'partial' AND verification_status = 'verified';
""")
rows = cur.fetchall()

promoted = 0
for r in rows:
    tid, qt, ql, ca, cal, dm_raw, ao, aol = r
    dm = _json_list(dm_raw)
    
    new_ql, new_cal, new_dm = sanitize_and_fix(tid, qt, ql, ca, cal, dm)
    
    c_q, _ = validate_display_contract('question', qt, new_ql)
    p_q, _ = validate_professional_latex(new_ql)
    k_q, _ = validate_with_katex(new_ql)
    
    c_a, _ = validate_display_contract('answer', ca, new_cal)
    p_a, _ = validate_professional_latex(new_cal)
    k_a, _ = validate_with_katex(new_cal)
    
    dms_ok = True
    for idx, d in enumerate(new_dm):
        vl = d.get('value_latex') or ''
        c_v, _ = validate_display_contract(f'dmeta[{idx}].value', d.get('value') or '', vl)
        p_v, _ = validate_professional_latex(vl)
        k_v, _ = validate_with_katex(vl)
        if not (c_v and p_v and k_v):
            dms_ok = False
            break
            
    if c_q and p_q and k_q and c_a and p_a and k_a and dms_ok and len(new_dm) >= 2:
        cur.execute("""
            UPDATE tasks_master
            SET question_latex = %s,
                correct_answer_latex = %s,
                distractor_meta = %s,
                latex_status = 'verified',
                latex_normalized_at = NOW()
            WHERE id = %s;
        """, (new_ql, new_cal, json.dumps(new_dm, ensure_ascii=False), tid))
        promoted += 1
    else:
        cur.execute("""
            UPDATE tasks_master
            SET question_latex = %s,
                correct_answer_latex = %s,
                distractor_meta = %s
            WHERE id = %s;
        """, (new_ql, new_cal, json.dumps(new_dm, ensure_ascii=False), tid))

conn.commit()
print(f"🎉 Переведено в VERIFIED: {promoted} задач из {len(rows)}!")
