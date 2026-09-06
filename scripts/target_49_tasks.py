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

def fix_49(tid, qt, ql, ca, cal, dm_raw, ao, aol):
    dm = _json_list(dm_raw)
    
    # 1. Задачи с missing_display_value в option: копируем из correct_answer и distractors
    if not aol or any(not opt for opt in aol):
        dist_vals = [d.get('value_latex') or d.get('value') for d in dm if isinstance(d, dict)]
        new_aol = [cal or ca] + dist_vals
    else:
        new_aol = aol

    def clean_s(s: str, is_val: bool = False) -> str:
        if not s:
            return s
        res = str(s).strip()
        # Замена спецсимволов и функций
        res = res.replace('≥', r'\ge').replace('≤', r'\le').replace('≠', r'\ne')
        res = res.replace('±', r'\pm').replace('×', r'\cdot').replace('·', r'\cdot')
        res = res.replace(r'\leqslant', r'\le').replace(r'\geqslant', r'\ge')
        res = res.replace(r'\pik', r'\pi k')
        res = res.replace('²', '^{2}').replace('³', '^{3}')
        
        # Исправление $1. \begin{cases} ... \end{cases}$
        if not is_val:
            res = re.sub(r'(?<!\$)\$(?!\$)\s*(?:[0-9a-zA-Zа-яА-Я][.)]?\s*)?(\\begin\{cases\}[\s\S]+?\\end\{cases\})\s*(?<!\$)\$(?!\$)', r'$$\1$$', res)
            res = re.sub(r'(?<!\$)\$(?!\$)\s*(\\lim[^\$]+)\s*(?<!\$)\$(?!\$)', r'$$\1$$', res)
            res = re.sub(r'(?<!\$)\$(?!\$)\s*(\\int[^\$]+)\s*(?<!\$)\$(?!\$)', r'$$\1$$', res)

        def fix_in_math(m):
            c = m.group(1).replace('$', '')
            c = re.sub(r'\\frac(?![A-Za-z])', r'\\dfrac', c)
            c = re.sub(r'(\^|_)([0-9a-zA-Z])(?![{0-9a-zA-Z])', r'\1{\2}', c)
            c = re.sub(r'(?<!\\)\b(sin|cos|tan|cot|tg|ctg|log|ln)\b', r'\\\1', c)
            c = c.replace('α', r'\alpha').replace('β', r'\beta').replace('γ', r'\gamma').replace('π', r'\pi')
            return f"${c}$"
            
        res = re.sub(r'\$([^$]+)\$', fix_in_math, res)
        
        if is_val:
            if res.startswith('$$') and res.endswith('$$'):
                res = '$' + res[2:-2].strip() + '$'
            elif not res.startswith('$') and not res.endswith('$'):
                if re.fullmatch(r'[0-9a-zA-Z\s+\-*×·/=<>≤≥≠(),.;:^{}\\_]+', res):
                    res = f"${res}$"
            if re.fullmatch(r'\$[^$]+\$(?:[;,]\s*\$[^$]+\$)+', res):
                parts = re.findall(r'\$([^$]+)\$', res)
                sep = '; ' if ';' in res else ', '
                res = '$' + sep.join(p.strip() for p in parts) + '$'
        return res

    new_ql = clean_s(ql or qt or '', is_val=False)
    new_cal = clean_s(cal or ca or '', is_val=True)
    
    new_dm = []
    for d in dm:
        if not isinstance(d, dict):
            continue
        d_c = dict(d)
        d_c['value_latex'] = clean_s(d_c.get('value_latex') or d_c.get('value') or '', is_val=True)
        desc = d_c.get('error_logic_latex') or d_c.get('explanation_latex') or d_c.get('error_logic') or d_c.get('explanation') or ''
        d_c['error_logic_latex'] = clean_s(desc, is_val=False)
        d_c['explanation_latex'] = clean_s(desc, is_val=False)
        new_dm.append(d_c)
        
    return new_ql, new_cal, new_dm, new_aol

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
    new_ql, new_cal, new_dm, new_aol = fix_49(tid, qt, ql, ca, cal, dm_raw, ao, aol)
    
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
                answer_options_latex = %s,
                latex_status = 'verified',
                latex_normalized_at = NOW()
            WHERE id = %s;
        """, (new_ql, new_cal, json.dumps(new_dm, ensure_ascii=False), json.dumps(new_aol, ensure_ascii=False), tid))
        promoted += 1
    else:
        cur.execute("""
            UPDATE tasks_master
            SET question_latex = %s,
                correct_answer_latex = %s,
                distractor_meta = %s,
                answer_options_latex = %s
            WHERE id = %s;
        """, (new_ql, new_cal, json.dumps(new_dm, ensure_ascii=False), json.dumps(new_aol, ensure_ascii=False), tid))

conn.commit()
print(f"🎉 Переведено в VERIFIED: {promoted} задач из {len(rows)}!")
