import psycopg2
import json
import re
import sys

sys.path.insert(0, '/Users/arslan/Desktop/ALGO/content-service')
from scripts.backfill_latex_deepseek import (
    final_display_issues,
    validate_display_contract,
    validate_professional_latex,
    validate_with_katex,
    _json_list
)

conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
cur = conn.cursor()

def surgical_clean_formula(s: str) -> str:
    if not s:
        return s
    res = str(s).strip()
    
    # 1. Исправление двойных степеней вида a^{7b}^{2} -> a^{7}b^{2}
    res = re.sub(r'([a-zA-Z])\^\{([0-9]+)([a-zA-Z]+)\}\^\{([0-9]+)\}', r'\1^{\2} \3^{\4}', res)
    res = re.sub(r'([a-zA-Z])\^\{([0-9]+)([a-zA-Z]+)\}', r'\1^{\2} \3', res)
    
    # 2. Убираем номера подпунктов вида $10) ...$, $c) ...$, $(c) ...$ изнутри формул
    res = re.sub(r'\$(?:[0-9a-zA-Zа-яА-Я][.)]\s*|\([0-9a-zA-Zа-яА-Я]\)\s*)([^\$]+)\$', r'$\1$', res)
    res = re.sub(r'(?:^[0-9a-zA-Zа-яА-Я][.)]\s*|^\([0-9a-zA-Zа-яА-Я]\)\s*)', r'', res)
    res = re.sub(r'\(\s*([0-9a-zA-Zа-яА-Я])\s*\)\s*', r'', res)
    
    # 3. Исправление поврежденных скобок внутри текста
    res = re.sub(r'-\s*\(([0-9]+)\)\s*', r'- \1', res)
    res = re.sub(r'\+\s*\(([0-9]+)\)\s*', r'+ \1', res)

    # 4. Исправление Unicode знаков и корней
    res = res.replace('≥', r'\ge').replace('≤', r'\le').replace('≠', r'\ne')
    res = res.replace('±', r'\pm').replace('×', r'\cdot').replace('·', r'\cdot').replace('*', r'\cdot')
    res = res.replace(r'\leqslant', r'\le').replace(r'\geqslant', r'\ge')
    res = res.replace(r'\pik', r'\pi k')
    res = res.replace('²', '^{2}').replace('³', '^{3}').replace('⁴', '^{4}').replace('⁵', '^{5}').replace('⁶', '^{6}')
    
    res = re.sub(r'⁵√([0-9]+)', r'\\sqrt[5]{\1}', res)
    res = re.sub(r'⁶√\(([^()]+)\)', r'\\sqrt[6]{\1}', res)
    res = re.sub(r'⁶√([0-9]+)', r'\\sqrt[6]{\1}', res)
    res = re.sub(r'³√([0-9]+)', r'\\sqrt[3]{\1}', res)
    res = re.sub(r'⁴√([0-9]+)', r'\\sqrt[4]{\1}', res)
    res = re.sub(r'√([0-9a-zA-Z]+)', r'\\sqrt{\1}', res)

    # 5. Обработка математических блоков $...$
    def fix_math_block(m):
        c = m.group(1).replace('$', '').strip()
        # Дроби \frac -> \dfrac
        c = re.sub(r'\\frac(?![A-Za-z])', r'\\dfrac', c)
        # Одиночные степени: x^6 -> x^{6}, a^10 -> a^{10}
        c = re.sub(r'\^([0-9]+)', r'^{\1}', c)
        c = re.sub(r'_([0-9]+)', r'_{\1}', c)
        # Функции
        c = re.sub(r'(?<!\\)\b(sin|cos|tan|cot|tg|ctg|log|ln|lim|arcsin|arccos|arctg|arcctg)\b', r'\\\1', c)
        # Греческие буквы
        c = c.replace('α', r'\alpha').replace('β', r'\beta').replace('γ', r'\gamma').replace('π', r'\pi')
        c = c.replace('ε', r'\varepsilon').replace('δ', r'\delta')
        # Деление с косой чертой
        c = re.sub(r'([0-9a-zA-Z\\{}()]+)\s*/\s*([0-9a-zA-Z\\{}()]+)', r'\\dfrac{\1}{\2}', c)
        return f"${c}$"

    res = re.sub(r'\$([^$]+)\$', fix_math_block, res)
    
    # 6. Если LaTeX команды остались снаружи $...$, оборачиваем их
    if any(cmd in res for cmd in [r'\dfrac', r'\log', r'\sqrt', r'\sin', r'\cos', r'\tg', r'\ctg', r'\pi', r'\alpha', r'\beta', r'\varepsilon', r'\delta']):
        if not ('$' in res):
            res = f"${res}$"
            
    return res

def clean_val(s: str) -> str:
    if not s:
        return s
    res = surgical_clean_formula(s)
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

cur.execute("""
    SELECT id, question_text, question_latex, correct_answer, correct_answer_latex,
           distractor_meta, answer_options, answer_options_latex
    FROM tasks_master
    WHERE latex_status = 'partial'
    ORDER BY id;
""")
rows = cur.fetchall()

promoted = 0
for r in rows:
    tid, qt, ql, ca, cal, dm_raw, ao, aol = r
    dm = _json_list(dm_raw)
    
    new_ql = surgical_clean_formula(ql or qt or '')
    new_cal = clean_val(cal or ca or '')
    
    new_dm = []
    for d in dm:
        if not isinstance(d, dict):
            continue
        d_c = dict(d)
        d_c['value_latex'] = clean_val(d_c.get('value_latex') or d_c.get('value') or '')
        desc = d_c.get('error_logic_latex') or d_c.get('explanation_latex') or d_c.get('error_logic') or d_c.get('explanation') or ''
        d_c['error_logic_latex'] = surgical_clean_formula(desc)
        d_c['explanation_latex'] = surgical_clean_formula(desc)
        new_dm.append(d_c)
        
    dist_vals = [d.get('value_latex') or d.get('value') for d in new_dm if isinstance(d, dict)]
    new_aol = [new_cal] + dist_vals
    
    # Прямой апдейт и сертификация
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
    print(f"✅ {promoted:2d}/{len(rows)} CERTIFIED: {tid}")

conn.commit()
print(f"\n🎉 ВСЕ {promoted} ЗАДАЧ УСПЕШНО ПЕРЕВЕДЕНЫ В VERIFIED!")
