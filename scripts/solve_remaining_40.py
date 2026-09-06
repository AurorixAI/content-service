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

def clean_ultimate(tid: str, qt: str, ql: str, ca: str, cal: str, dm: list):
    # 1. Замена номеров подпунктов типа $10) ...$ или $c) ...$ внутри формул -> убираем номер или выносим
    def strip_leading_item_num(s: str) -> str:
        if not s:
            return s
        # $10) ...$ -> $...$, $c) ...$ -> $...$
        res = re.sub(r'\$(?:[0-9a-zA-Zа-яА-Я][.)]\s*)([^\$]+)\$', r'$\1$', s)
        res = re.sub(r'\(\s*([0-9a-zA-Zа-яА-Я])\s*\)\s*', r'', res)
        # Исправление поврежденных -(3) -> - 3
        res = re.sub(r'-\s*\(([0-9]+)\)\s*', r'- \1', res)
        res = re.sub(r'\+\s*\(([0-9]+)\)\s*', r'+ \1', res)
        
        # Исправление Unicode корней ⁵√2 -> \sqrt[5]{2}, ⁶√(a) -> \sqrt[6]{a}
        res = re.sub(r'⁵√([0-9]+)', r'\\sqrt[5]{\1}', res)
        res = re.sub(r'⁶√\(([^()]+)\)', r'\\sqrt[6]{\1}', res)
        res = re.sub(r'⁶√([0-9]+)', r'\\sqrt[6]{\1}', res)
        res = re.sub(r'³√([0-9]+)', r'\\sqrt[3]{\1}', res)
        res = re.sub(r'⁴√([0-9]+)', r'\\sqrt[4]{\1}', res)
        res = re.sub(r'√([0-9a-zA-Z]+)', r'\\sqrt{\1}', res)
        
        # Степени без фигурных скобок: a^11, x^6, a^5b
        def fix_pows_all(m):
            c = m.group(1).replace('$', '')
            c = re.sub(r'\^([0-9a-zA-Z]+)', r'^{\1}', c)
            c = re.sub(r'_([0-9a-zA-Z]+)', r'_{\1}', c)
            c = re.sub(r'\\frac(?![A-Za-z])', r'\\dfrac', c)
            c = re.sub(r'(?<!\\)\b(sin|cos|tan|cot|tg|ctg|log|ln|lim|arcsin|arccos|arctg|arcctg)\b', r'\\\1', c)
            c = c.replace('α', r'\alpha').replace('β', r'\beta').replace('γ', r'\gamma').replace('π', r'\pi')
            c = c.replace('·', r'\cdot').replace('*', r'\cdot').replace('×', r'\cdot')
            c = c.replace('²', '^{2}').replace('³', '^{3}').replace('⁴', '^{4}').replace('⁵', '^{5}')
            c = re.sub(r'([0-9a-zA-Z\\{}()]+)\s*/\s*([0-9a-zA-Z\\{}()]+)', r'\\dfrac{\1}{\2}', c)
            return f"${c}$"
            
        res = re.sub(r'\$([^$]+)\$', fix_pows_all, res)
        return res

    def clean_val(s: str) -> str:
        if not s:
            return s
        res = strip_leading_item_num(s)
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

    new_ql = strip_leading_item_num(ql or qt or '')
    new_cal = clean_val(cal or ca or '')
    
    new_dm = []
    for d in dm:
        if not isinstance(d, dict):
            continue
        d_c = dict(d)
        d_c['value_latex'] = clean_val(d_c.get('value_latex') or d_c.get('value') or '')
        desc = d_c.get('error_logic_latex') or d_c.get('explanation_latex') or d_c.get('error_logic') or d_c.get('explanation') or ''
        d_c['error_logic_latex'] = strip_leading_item_num(desc)
        d_c['explanation_latex'] = strip_leading_item_num(desc)
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
    
    new_ql, new_cal, new_dm = clean_ultimate(tid, qt, ql, ca, cal, dm)
    dist_vals = [d.get('value_latex') or d.get('value') for d in new_dm if isinstance(d, dict)]
    new_aol = [new_cal] + dist_vals
    
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
