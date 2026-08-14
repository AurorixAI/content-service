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

def clean_advanced(s: str, is_math: bool = False) -> str:
    if not s:
        return s
    res = str(s).strip()
    
    # 1. Замена ± на \pm, × на \cdot
    res = res.replace('±', r'\pm ').replace('×', r'\cdot ').replace('·', r'\cdot ')
    
    # 2. Исправление вложенных долларов вида $... $x^{2}$ ...$ -> $... x^{2} ...$
    # Если строка начинается с $ и заканчивается на $, но внутри есть нечетное число $, убираем лишние
    if res.startswith('$') and res.endswith('$') and not res.startswith('$$'):
        inner = res[1:-1]
        inner_fixed = inner.replace('$', '')
        res = f"${inner_fixed}$"
        
    # 3. Добавление фигурных скобок ко всем степеням: x^6 -> x^{6}, a^3 -> a^{3}
    def fix_math_blocks(m):
        content = m.group(1)
        # x^6 -> x^{6}
        content = re.sub(r'(?<=\^)([0-9a-zA-Z])(?![{0-9a-zA-Z])', r'{\1}', content)
        # a/b -> \dfrac{a}{b}
        content = re.sub(r'([0-9a-zA-Z\\{}]+)\s*/\s*([0-9a-zA-Z\\{}]+)', r'\\dfrac{\1}{\2}', content)
        return f"${content}$"
        
    res = re.sub(r'\$([^$]+)\$', fix_math_blocks, res)
    
    # 4. Преобразование систем $1. \begin{cases} ... \end{cases}$ в блочный $$\begin{cases} ... \end{cases}$$
    if not is_math:
        res = re.sub(r'(?<!\$)\$(?!\$)\s*([0-9a-zA-Zа-яА-Я][.)]?\s*)?(\\begin\{cases\}[\s\S]+?\\end\{cases\})\s*(?<!\$)\$(?!\$)', r'$$\2$$', res)
        # Вынос \lim в блочный вид если в вопросе
        res = re.sub(r'(?<!\$)\$(?!\$)\s*(\\lim[^\$]+)\s*(?<!\$)\$(?!\$)', r'$$\1$$', res)

    return res

print("=== 🚀 ОБРАБОТКА ПОСЛЕДНИХ 134 ЗАДАЧ ===")

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
    
    new_ql = clean_advanced(ql or qt or '', is_math=False)
    new_cal = clean_advanced(cal or ca or '', is_math=True)
    
    new_dm = []
    for d in dm:
        if not isinstance(d, dict):
            continue
        d_new = dict(d)
        v_l = clean_advanced(d_new.get('value_latex') or d_new.get('value') or '', is_math=True)
        d_new['value_latex'] = v_l
        
        desc = d_new.get('error_logic_latex') or d_new.get('explanation_latex') or d_new.get('error_logic') or d_new.get('explanation') or ''
        clean_desc = clean_advanced(desc, is_math=False)
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
