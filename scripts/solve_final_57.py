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

def clean_item(s: str, is_math: bool = False) -> str:
    if not s:
        return s
    res = str(s).strip()
    
    # 1. Если двойные $$ в дистракторе или ответе - меняем на $
    if is_math and res.startswith('$$') and res.endswith('$$'):
        res = '$' + res[2:-2].strip() + '$'
        
    # 2. Опечатки в скобках \sqrt{a^{2} -
    res = res.replace(r'\sqrt{a^{2} -', r'\sqrt{a^{2} - x^{2}}')
    res = res.replace(r'\sqrt{4 -', r'\sqrt{4 - x^{2}}')
    
    # 3. Скобки типа 1) или а) в вопросах: заменяем на (1) или 1.
    if not is_math:
        res = re.sub(r'(?<!\()(?<![0-9a-zA-Z])([0-9a-zA-Zа-яА-Я])\)\s*', r'(\1) ', res)
        # Если в тексте вопроса есть одиночные несбалансированные скобки
        # Превращаем \lim в блочный вид
        res = re.sub(r'(?<!\$)\$(?!\$)\s*(\\lim[^\$]+)\s*(?<!\$)\$(?!\$)', r'$$\1$$', res)

    # 4. Степени x^6 -> x^{6}, a^3 -> a^{3}
    def fix_pows(m):
        c = m.group(1)
        c = re.sub(r'(\^|_)([0-9a-zA-Z])(?![{0-9a-zA-Z])', r'\1{\2}', c)
        c = c.replace('π', r'\pi').replace('α', r'\alpha').replace('β', r'\beta')
        c = c.replace(r'\leqslant', r'\le').replace(r'\geqslant', r'\ge')
        c = c.replace(r'\pik', r'\pi k')
        c = re.sub(r'\\frac(?![A-Za-z])', r'\\dfrac', c)
        return f"${c}$"
        
    res = re.sub(r'\$([^$]+)\$', fix_pows, res)
    return res

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
    
    new_ql = clean_item(ql or qt or '', is_math=False)
    new_cal = clean_item(cal or ca or '', is_math=True)
    
    # Специальные фиксы для специфичных задач
    if tid == 'G9_TB_20_241_5':
        new_cal = r'$x = 2 + \dfrac{\pi k}{3}, k \in \mathbb{Z}$'
        
    new_dm = []
    for d in dm:
        if not isinstance(d, dict):
            continue
        d_c = dict(d)
        v = clean_item(d_c.get('value_latex') or d_c.get('value') or '', is_math=True)
        if tid == 'G9_TB_20_241_5':
            v = v.replace('$$', '$')
        d_c['value_latex'] = v
        
        desc = clean_item(d_c.get('error_logic_latex') or d_c.get('explanation_latex') or d_c.get('error_logic') or d_c.get('explanation') or '', is_math=False)
        d_c['error_logic_latex'] = desc
        d_c['explanation_latex'] = desc
        new_dm.append(d_c)
        
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
