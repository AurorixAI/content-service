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

def format_from_raw(s: str, is_math: bool = False) -> str:
    if not s:
        return s
    res = str(s).strip()
    
    # 1. Замена знаков неравенств и спецсимволов
    res = res.replace('≥', r'\ge').replace('≤', r'\le').replace('≠', r'\ne')
    res = res.replace('±', r'\pm').replace('×', r'\cdot').replace('·', r'\cdot')
    res = res.replace(r'\leqslant', r'\le').replace(r'\geqslant', r'\ge')
    res = res.replace(r'\pik', r'\pi k')
    res = res.replace('²', '^{2}').replace('³', '^{3}')
    
    # 2. Если это чисто математическое значение
    if is_math:
        # Убираем лишние внешние скобки или пробелы
        if not res.startswith('$') and not res.endswith('$'):
            if re.fullmatch(r'[0-9a-zA-Z\s+\-*×·/=<>≤≥≠(),.;:^{}\\_]+', res):
                res = f"${res}$"
        # Склейка раздельных долларов в один
        if re.fullmatch(r'\$[^$]+\$(?:[;,]\s*\$[^$]+\$)+', res):
            parts = re.findall(r'\$([^$]+)\$', res)
            sep = '; ' if ';' in res else ', '
            res = '$' + sep.join(p.strip() for p in parts) + '$'

    # 3. Чистка формул внутри $...$
    def clean_math(m):
        c = m.group(1)
        c = c.replace('$', '')
        # \frac -> \dfrac
        c = re.sub(r'\\frac(?![A-Za-z])', r'\\dfrac', c)
        # x^2 -> x^{2}
        c = re.sub(r'(\^|_)([0-9a-zA-Z])(?![{0-9a-zA-Z])', r'\1{\2}', c)
        # a/b -> \dfrac{a}{b}
        c = re.sub(r'([0-9a-zA-Z\\{}]+)\s*/\s*([0-9a-zA-Z\\{}]+)', r'\\dfrac{\1}{\2}', c)
        # функции без слеша
        c = re.sub(r'(?<!\\)\b(sin|cos|tan|cot|tg|ctg|log|ln)\b', r'\\\1', c)
        # греческие буквы
        c = c.replace('α', r'\alpha').replace('β', r'\beta').replace('γ', r'\gamma').replace('π', r'\pi')
        return f"${c}$"
        
    res = re.sub(r'\$([^$]+)\$', clean_math, res)
    
    # 4. Вынос \int и \begin{cases} в блочный вид $$...$$
    if not is_math:
        res = re.sub(r'(?<!\$)\$(?!\$)\s*(\\int[^\$]+)\s*(?<!\$)\$(?!\$)', r'$$\1$$', res)
        res = re.sub(r'(?<!\$)\$(?!\$)\s*(\\begin\{cases\}[\s\S]+?\\end\{cases\})\s*(?<!\$)\$(?!\$)', r'$$\1$$', res)

    return res

print("=== 🚀 ВОССТАНОВЛЕНИЕ И ФИНАЛЬНАЯ СЕРТИФИКАЦИЯ 79 ЗАДАЧ ИЗ RAW ===")

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
    
    # Форматируем из RAW question_text и correct_answer
    new_ql = format_from_raw(qt, is_math=False)
    new_cal = format_from_raw(ca, is_math=True)
    
    new_dm = []
    for d in dm:
        if not isinstance(d, dict):
            continue
        d_new = dict(d)
        raw_v = d_new.get('value') or ''
        d_new['value_latex'] = format_from_raw(raw_v, is_math=True)
        
        raw_desc = d_new.get('error_logic') or d_new.get('explanation') or ''
        clean_desc = format_from_raw(raw_desc, is_math=False)
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
print(f"🎉 Успешно переведено в VERIFIED: {promoted} задач из {len(rows)}!")
