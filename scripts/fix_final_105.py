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

def clean_specific_task(tid: str, qt: str, ql: str, ca: str, cal: str, dm: list):
    # 1. ds_llm_56fcab77bc10 child tasks
    if 'ds_llm_56fcab77bc10' in tid:
        ql = ql.replace(r'\text{ при }', ' при ').replace(r'\text', '')
        
    # 2. G11_TB_13_1*_12_20_b
    if tid == 'G11_TB_13_1*_12_20_b':
        ql = 'Решите неравенство: $(x^{2} - x - 30)\\sqrt{x^{2} - 4} \\le 0$'
        
    # 3. G10_TB_1_4_1_4_1
    if tid == 'G10_TB_1_4_1_4_1':
        ql = 'Даны функции $f(x)=x^{2}$ и $g(x)=x-3$. Найдите сложные функции $f(g(x))$ и $g(f(x))$ и их области определения.'
        cal = 'а) $f(g(x)) = (x-3)^{2}, D(f(g)) = \\mathbb{R}$; б) $g(f(x)) = x^{2} - 3, D(g(f)) = \\mathbb{R}$'

    # Общая чистка степеней вида x^6 -> x^{6}
    def fix_powers(s):
        if not s:
            return s
        return re.sub(r'(\^|_)([0-9a-zA-Z])(?![{0-9a-zA-Z])', r'\1{\2}', s)

    # Общая чистка дробей a / b -> \dfrac{a}{b}
    def fix_slashes(s):
        if not s:
            return s
        return re.sub(r'([0-9a-zA-Z\\{}()]+)\s*/\s*([0-9a-zA-Z\\{}()]+)', r'\\dfrac{\1}{\2}', s)

    ql = fix_powers(ql)
    cal = fix_powers(cal)
    
    clean_dm = []
    for d in dm:
        d_c = dict(d)
        v = d_c.get('value_latex') or d_c.get('value') or ''
        v = fix_powers(v)
        v = fix_slashes(v)
        d_c['value_latex'] = v
        
        desc = d_c.get('error_logic_latex') or d_c.get('explanation_latex') or d_c.get('error_logic') or d_c.get('explanation') or ''
        desc = fix_powers(desc)
        d_c['error_logic_latex'] = desc
        d_c['explanation_latex'] = desc
        clean_dm.append(d_c)
        
    return ql, cal, clean_dm

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
    
    new_ql, new_cal, new_dm = clean_specific_task(tid, qt, ql, ca, cal, dm)
    
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
