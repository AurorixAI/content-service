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

# 1. Исправление опечатки \pik -> \pi k в базе
cur.execute("""
    UPDATE tasks_master
    SET distractor_meta = REPLACE(distractor_meta::text, '\\\\pik', '\\\\pi k')::jsonb
    WHERE distractor_meta::text LIKE '%\\\\pik%';
""")

# 2. Исправление & в формуле ответа ds_llm_4f91d75f76fc
cur.execute("""
    UPDATE tasks_master
    SET correct_answer_latex = '$x \\in \\left(-\\dfrac{12}{5}; 14\\right]$'
    WHERE id = 'ds_llm_4f91d75f76fc';
""")

conn.commit()

cur.execute("""
    SELECT id, question_text, question_latex, correct_answer,
           correct_answer_latex, distractor_meta, answer_options,
           answer_options_latex
    FROM tasks_master
    WHERE latex_status = 'partial' AND verification_status = 'verified';
""")
rows = cur.fetchall()

def clean_formula_parens(s):
    if not s:
        return s
    res = str(s).replace(r'\pik', r'\pi k')
    # Исправление $1. \begin{cases} ... \end{cases}$
    res = re.sub(r'(?<!\$)\$(?!\$)\s*(?:[0-9a-zA-Zа-яА-Я][.)]?\s*)?(\\begin\{cases\}[\s\S]+?\\end\{cases\})\s*(?<!\$)\$(?!\$)', r'$$\1$$', res)
    # Исправление \displaystyle\int
    res = re.sub(r'\$\\displaystyle\\int([^\$]+)\$', r'$$\\int\1$$', res)
    # Исправление \int в вопросах
    res = re.sub(r'(?<!\$)\$(?!\$)\s*(\\int[^\$]+)\s*(?<!\$)\$(?!\$)', r'$$\1$$', res)
    # Исправление вложенных $ внутри формул
    def repl_inner(m):
        c = m.group(1).replace('$', '')
        c = re.sub(r'(\^|_)([0-9a-zA-Z])(?![{0-9a-zA-Z])', r'\1{\2}', c)
        return f'${c}$'
    res = re.sub(r'\$([^$]+)\$', repl_inner, res)
    return res

promoted = 0
for r in rows:
    tid, qt, ql, ca, cal, dm_raw, ao, aol = r
    dm = _json_list(dm_raw)
    
    new_ql = clean_formula_parens(ql or qt or '')
    new_cal = clean_formula_parens(cal or ca or '')
    new_dm = []
    for d in dm:
        if not isinstance(d, dict):
            continue
        d_c = dict(d)
        d_c['value_latex'] = clean_formula_parens(d_c.get('value_latex') or d_c.get('value'))
        d_c['error_logic_latex'] = clean_formula_parens(d_c.get('error_logic_latex') or d_c.get('error_logic'))
        d_c['explanation_latex'] = clean_formula_parens(d_c.get('explanation_latex') or d_c.get('explanation'))
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
print(f"🎉 Дополнительно переведено в VERIFIED: {promoted} задач из {len(rows)}!")
