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

def sanitize_latex_string(s: str, is_math_value: bool = False) -> str:
    if not s:
        return s
    res = str(s).strip()
    
    # 1. Замена \leqslant / \geqslant на \le / \ge
    res = res.replace(r'\leqslant', r'\le').replace(r'\geqslant', r'\ge')
    
    # 2. Замена Unicode в тексте/формулах на LaTeX
    res = res.replace('∛', r'\sqrt[3]').replace('√', r'\sqrt')
    res = res.replace('²', '^{2}').replace('³', '^{3}').replace('⁴', '^{4}')
    res = res.replace('Δx', r'\Delta x').replace('Δy', r'\Delta y').replace('Δf', r'\Delta f')
    res = res.replace('x₀', 'x_{0}').replace('y₀', 'y_{0}')
    
    # 3. Исправление делений вида -4\sqrt{2}/3 или a/b внутри $...$
    def fix_slash(m):
        inner = m.group(1)
        # -4\sqrt{2}/3 -> -\dfrac{4\sqrt{2}}{3}
        inner = re.sub(r'([+-]?)\s*([0-9a-zA-Z\\{}]+)/([0-9a-zA-Z\\{}]+)', r'\1\\dfrac{\2}{\3}', inner)
        # ^-40^\circ -> ^{-40^\circ}
        inner = re.sub(r'\^(-?[0-9]+)\^\\circ', r'^{\1^\\circ}', inner)
        # \cot(-40^\circ) -> \cot(-40^{\circ})
        inner = inner.replace(r'^\circ', r'^{\circ}')
        return f"${inner}$"
        
    res = re.sub(r'\$([^$]+)\$', fix_slash, res)
    
    # 4. Исправление перекрестных долларов вида $(($x^{2}$-x-30) -> $((x^{2}-x-30)
    res = re.sub(r'\(\(\$([^$]+)\$', r'$((\1', res)
    res = re.sub(r'\$([^$]+)\$\)', r'\1)$', res)
    
    # 5. Исправление $a)$ -> a)
    res = re.sub(r'\$([0-9a-zA-Zа-яА-Я])\)\$', r'\1)', res)
    res = re.sub(r'\$([0-9a-zA-Zа-яА-Я])\.', r'\1.', res)
    
    # 6. Преобразование инлайн интегралов $\int ...$ в блочные $$\int ...$$ в вопросах
    if not is_math_value:
        res = re.sub(r'(?<!\$)\$(?!\$)\s*(\\int[^\$]+)\s*(?<!\$)\$(?!\$)', r'$$\1$$', res)
        res = re.sub(r'(?<!\$)\$(?!\$)\s*(\\begin\{cases\}[\s\S]+?\\end\{cases\})\s*(?<!\$)\$(?!\$)', r'$$\1$$', res)
        res = re.sub(r'\\left\\\{\s*\\begin\{array\}\{l\}\s*([\s\S]+?)\s*\\end\{array\}\s*\\right\.', r'\\begin{cases} \1 \\end{cases}', res)

    # 7. Для pure_math_value склейка в монолитный $...$
    if is_math_value:
        if re.fullmatch(r'\$[^$]+\$(?:[;,]\s*\$[^$]+\$)+', res):
            parts = re.findall(r'\$([^$]+)\$', res)
            sep = '; ' if ';' in s else ', '
            res = '$' + sep.join(p.strip() for p in parts) + '$'
            
    return res

print("=== 🛠 ЗАПУСК ГЛУБОКОГО САНИТИЗАТОРА ДЛЯ 391 PARTIAL ЗАДАЧ ===")

cur.execute("""
    SELECT id, question_text, question_latex, correct_answer,
           correct_answer_latex, distractor_meta, answer_options,
           answer_options_latex
    FROM tasks_master
    WHERE verification_status = 'verified' AND latex_status = 'partial';
""")
rows = cur.fetchall()

success_count = 0
for r in rows:
    tid, qt, ql, ca, cal, dm_raw, ao, aol = r
    dm = _json_list(dm_raw)
    
    new_ql = sanitize_latex_string(ql or qt or '', is_math_value=False)
    new_cal = sanitize_latex_string(cal or ca or '', is_math_value=True)
    
    new_dm = []
    for d in dm:
        if not isinstance(d, dict):
            continue
        d_new = dict(d)
        d_new['value_latex'] = sanitize_latex_string(d_new.get('value_latex') or d_new.get('value') or '', is_math_value=True)
        
        desc = d_new.get('error_logic_latex') or d_new.get('explanation_latex') or d_new.get('error_logic') or d_new.get('explanation') or ''
        clean_desc = sanitize_latex_string(desc, is_math_value=False)
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
        success_count += 1
    else:
        cur.execute("""
            UPDATE tasks_master
            SET question_latex = %s,
                correct_answer_latex = %s,
                distractor_meta = %s
            WHERE id = %s;
        """, (new_ql, new_cal, json.dumps(new_dm, ensure_ascii=False), tid))

conn.commit()
print(f"✅ Успешно сертифицировано и переведено в VERIFIED ещё: {success_count} задач из 391!")
