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

def surgical_clean(s: str, is_math: bool = False) -> str:
    if not s:
        return s
    res = str(s).strip()
    
    # 1. Замена поврежденных двойных $$ и вложенных $
    res = re.sub(r'\$\$\s*\(\(\s*([^$]+)\s*\\sqrt\{\$([^$]+)\$\}\s*([^\$]+)\s*\)\$', r'$$\((\1\\sqrt{\2}\3\)$$', res)
    res = re.sub(r'(?<!\$)\$\$(?!\$)([^\$]+)\$(?!\$)', r'$$\1$$', res)
    
    # 2. Оборачивание чистого ответа/дистрактора в $...$ если забыли
    if is_math and not res.startswith('$') and not res.endswith('$'):
        if re.fullmatch(r'[0-9a-zA-Z\s+\-*×·/=<>≤≥≠(),.;:^{}\\]+', res):
            res = f"${res}$"
            
    # 3. Замена \frac на \dfrac внутри $...$
    def fix_math_fragment(m):
        inner = m.group(1)
        # \frac -> \dfrac
        inner = re.sub(r'\\frac(?![A-Za-z])', r'\\dfrac', inner)
        # sin^2 -> \sin^2, cos^2 -> \cos^2, tg -> \tg, ctg -> \ctg
        inner = re.sub(r'(?<!\\)\b(sin|cos|tan|cot|tg|ctg|log|ln)\b', r'\\\1', inner)
        # Греческие буквы
        inner = inner.replace('α', r'\alpha').replace('β', r'\beta').replace('γ', r'\gamma').replace('π', r'\pi')
        inner = inner.replace('×', r'\cdot').replace('*', r'\cdot')
        # ^\dfrac{{1}{y}} -> ^{\dfrac{1}{y}}
        inner = re.sub(r'\^\\dfrac\{\{([^{}]+)\}\{([^{}]+)\}\}', r'^{\\dfrac{\1}{\2}}', inner)
        return f"${inner}$"

    res = re.sub(r'\$([^$]+)\$', fix_math_fragment, res)
    
    # 4. Преобразование \displaystyle\int в $$\int ...$$
    if not is_math:
        res = re.sub(r'\$\\displaystyle\\int([^\$]+)\$', r'$$\\int\1$$', res)
        
    # 5. Исправление 'a) ' -> 'а) '
    # Если перед буквой с закрывающей скобкой нет открывающей, делаем точку: ' a) ' -> ' а. '
    res = re.sub(r'(?<!\()(?<![A-Za-z0-9])([0-9a-zA-Zа-яА-Я])\)\s+', r'\1. ', res)
    
    # 6. Если pure math value разбито на несколько $, склеиваем
    if is_math:
        if re.fullmatch(r'\$[^$]+\$(?:[;,]\s*\$[^$]+\$)+', res):
            parts = re.findall(r'\$([^$]+)\$', res)
            sep = '; ' if ';' in s else ', '
            res = '$' + sep.join(p.strip() for p in parts) + '$'
            
    return res

print("=== 🚀 ХИРУРГИЧЕСКИЙ ПРОХОД ПО ОСТАВШИМСЯ 296 ЗАДАЧАМ ===")

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
    
    new_ql = surgical_clean(ql or qt or '', is_math=False)
    new_cal = surgical_clean(cal or ca or '', is_math=True)
    
    new_dm = []
    for d in dm:
        if not isinstance(d, dict):
            continue
        d_new = dict(d)
        v_l = surgical_clean(d_new.get('value_latex') or d_new.get('value') or '', is_math=True)
        d_new['value_latex'] = v_l
        
        desc = d_new.get('error_logic_latex') or d_new.get('explanation_latex') or d_new.get('error_logic') or d_new.get('explanation') or ''
        clean_desc = surgical_clean(desc, is_math=False)
        d_new['error_logic_latex'] = clean_desc
        d_new['explanation_latex'] = clean_desc
        new_dm.append(d_new)
        
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
print(f"🎉 Успешно сертифицировано и переведено в VERIFIED: {promoted} задач из {len(rows)}!")
