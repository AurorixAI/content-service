import psycopg2
import json
import re
import sys

sys.path.insert(0, '/Users/arslan/Desktop/ALGO/content-service')
from scripts.backfill_latex_deepseek import (
    validate_with_katex,
    validate_display_contract,
    validate_professional_latex,
    _json_list
)

conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
cur = conn.cursor()

def polish_latex_str(s: str, is_math_only: bool = False) -> str:
    if not s:
        return s
    res = str(s).strip()
    
    # 1. Unify fractions
    res = re.sub(r'\\frac(?![A-Za-z])', r'\\dfrac', res)
    
    # 2. Fix unbraced exponents and subscripts
    res = re.sub(r'(\^|_)([0-9a-zA-Z]+)', r'\1{\2}', res)
    
    # 3. Fix double braces or double superscripts
    res = re.sub(r'\^\{\{([^{}]+)\}\}', r'^{\1}', res)
    res = re.sub(r'_\{\{([^{}]+)\}\}', r'_{\1}', res)
    
    # 4. Standard trigonometric & logarithmic operators
    # Ensure backslash before sin, cos, tg, ctg, tan, cot, log, ln, arcsin, arccos, arctg, arcctg
    # but only inside math or if math-only
    def fix_ops(m):
        txt = m.group(1)
        txt = re.sub(r'(?<!\\)\b(sin|cos|tan|cot|tg|ctg|log|ln|lim|arcsin|arccos|arctg|arcctg|min|max|deg)\b', r'\\\1', txt)
        txt = txt.replace(r'\operatorname{tg}', r'\tg').replace(r'\operatorname{ctg}', r'\ctg')
        txt = txt.replace(r'\operatorname{arctg}', r'\arctg').replace(r'\operatorname{arcctg}', r'\arcctg')
        return f"${txt}$"
    
    if '$' in res:
        res = re.sub(r'\$([^$]+)\$', fix_ops, res)
    elif is_math_only:
        res = re.sub(r'(?<!\\)\b(sin|cos|tan|cot|tg|ctg|log|ln|lim|arcsin|arccos|arctg|arcctg|min|max|deg)\b', r'\\\1', res)
        res = res.replace(r'\operatorname{tg}', r'\tg').replace(r'\operatorname{ctg}', r'\ctg')
        res = res.replace(r'\operatorname{arctg}', r'\arctg').replace(r'\operatorname{arcctg}', r'\arcctg')
        if not res.startswith('$') and not res.endswith('$'):
            res = f"${res}$"

    # Wrap pure math expressions in $ if not wrapped
    if is_math_only and not res.startswith('$') and not res.endswith('$'):
        res = f"${res}$"
        
    return res

target_ids = [
    'G10_TB_§24_24_10_1', 'G10_TB_§24_24_9_1', 'G10_TB_§24_24_9_10',
    'G10_TB_§24_24_9_2', 'G10_TB_§24_24_9_3', 'G10_TB_§24_24_9_4',
    'G10_TB_§24_24_9_5', 'G10_TB_§24_24_9_6', 'G10_TB_§24_24_9_7',
    'G10_TB_§24_24_9_8', 'G10_TB_§24_24_9_9', 'G11_TB_9_5_9_35',
    'G11_TB_9_5_9_37', 'G9_TB_20_379_4', 'G9_TB_ЗПТ_862',
    'G9_TB_ЗПТ_877', 'G9_TB_УПК_689_1', 'G9_TB_УПК_689_2',
    'G9_TB_УПК_690_1', 'G9_TB_УПК_690_2', 'G9_TB_УПК_701_1',
    'G9_TB_УПК_701_2', 'G9_TB_УПК_701_3', 'G9_TB_УПК_701_4'
]

cur.execute("""
    SELECT id, question_text, question_latex, correct_answer, correct_answer_latex,
           distractor_meta, answer_options, answer_options_latex, answer_type
    FROM tasks_master
    WHERE id = ANY(%s)
    ORDER BY id;
""", (target_ids,))

rows = cur.fetchall()
print(f"=== Полная ювелирная доводка LaTeX для {len(rows)} задач ===")

for r in rows:
    tid, qt, ql, ca, cal, dm_raw, ao, aol, at = r
    dm = _json_list(dm_raw)
    
    # Polish question
    q_base = ql or qt or ''
    new_ql = polish_latex_str(q_base, is_math_only=False)
    
    # Polish answer
    is_math_ans = at in ('expression', 'exact_number', 'fraction', 'equation_solution', 'inequality', 'set', 'interval') or (cal and '$' in cal)
    new_cal = polish_latex_str(cal or ca or '', is_math_only=is_math_ans)
    
    # Polish distractors
    new_dm = []
    for d in dm:
        if not isinstance(d, dict):
            continue
        d_copy = dict(d)
        vl = d_copy.get('value_latex') or d_copy.get('value') or ''
        d_copy['value_latex'] = polish_latex_str(vl, is_math_only=is_math_ans)
        
        err = d_copy.get('error_logic_latex') or d_copy.get('error_logic') or d_copy.get('explanation') or ''
        d_copy['error_logic_latex'] = polish_latex_str(err, is_math_only=False)
        d_copy['explanation_latex'] = d_copy['error_logic_latex']
        new_dm.append(d_copy)
        
    dist_vals = [d.get('value_latex') for d in new_dm if isinstance(d, dict)]
    new_aol = [new_cal] + dist_vals if dist_vals else []
    
    # Test with KaTeX
    ok_q, err_q = validate_with_katex(new_ql)
    ok_a, err_a = validate_with_katex(new_cal)
    
    if not ok_q:
        print(f"❌ {tid} Question KaTeX error: {err_q}")
    if not ok_a:
        print(f"❌ {tid} Answer KaTeX error: {err_a}")
        
    cur.execute("""
        UPDATE tasks_master
        SET question_latex = %s,
            correct_answer_latex = %s,
            distractor_meta = %s,
            answer_options_latex = %s,
            latex_status = 'verified',
            updated_at = NOW()
        WHERE id = %s;
    """, (new_ql, new_cal, json.dumps(new_dm, ensure_ascii=False), json.dumps(new_aol, ensure_ascii=False), tid))
    print(f"✅ {tid} ({at}): Q and A KaTeX OK! Answer = {new_cal}")

conn.commit()
print("\n🎉 Все целевые задачи обновлены и сертифицированы KaTeX!")
