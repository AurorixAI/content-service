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

cur.execute("""
    SELECT id, question_text, question_latex, correct_answer, correct_answer_latex,
           distractor_meta, answer_options, answer_options_latex, answer_type
    FROM tasks_master
    ORDER BY id;
""")
rows = cur.fetchall()
total = len(rows)

stats = {
    'total': total,
    'missing_distractors': [],
    'less_than_3_distractors': [],
    'distractor_equals_answer': [],
    'duplicate_distractors': [],
    'short_error_logic': [],
    'invalid_katex_question': [],
    'invalid_katex_answer': [],
    'invalid_katex_distractor': [],
    'unbraced_powers_distractor': [],
    'unbraced_powers_question': [],
    'unbraced_powers_answer': [],
    'clean_flawless': 0
}

BINARY_WORDS = {'да', 'нет', 'верно', 'неверно', 'true', 'false', 'является', 'не является', 'четная', 'нечетная'}

for r in rows:
    tid, qt, ql, ca, cal, dm_raw, ao, aol, at = r
    dm = _json_list(dm_raw)
    
    is_binary = str(ca).strip().lower() in BINARY_WORDS or str(cal).strip().lower().replace('$', '') in BINARY_WORDS
    min_dist_count = 1 if is_binary else 3
    
    task_flawed = False
    
    # 1. KaTeX в вопросе
    q_target = ql or qt or ''
    ok_k_q, err_k_q = validate_with_katex(q_target)
    if not ok_k_q:
        stats['invalid_katex_question'].append((tid, err_k_q))
        task_flawed = True
        
    # 2. KaTeX в ответе
    a_target = cal or ca or ''
    ok_k_a, err_k_a = validate_with_katex(a_target)
    if not ok_k_a:
        stats['invalid_katex_answer'].append((tid, err_k_a))
        task_flawed = True

    # 3. Наличие дистракторов
    if not dm:
        stats['missing_distractors'].append(tid)
        task_flawed = True
    elif len(dm) < min_dist_count:
        stats['less_than_3_distractors'].append((tid, len(dm), min_dist_count))
        task_flawed = True
        
    # 4. Проверка каждого дистрактора
    ans_clean = a_target.strip().replace('$', '').lower()
    seen_dist_vals = []
    
    for idx, d in enumerate(dm):
        if not isinstance(d, dict):
            task_flawed = True
            continue
        v = str(d.get('value') or '').strip()
        vl = str(d.get('value_latex') or v).strip()
        vl_clean = vl.replace('$', '').lower()
        err = str(d.get('error_logic') or d.get('explanation') or '').strip()
        
        # KaTeX дистрактора
        ok_k_d, err_k_d = validate_with_katex(vl)
        if not ok_k_d:
            stats['invalid_katex_distractor'].append((tid, idx, err_k_d))
            task_flawed = True
            
        # Равенство ответу
        if vl_clean == ans_clean or v.lower() == ans_clean:
            stats['distractor_equals_answer'].append((tid, idx, vl_clean))
            task_flawed = True
            
        # Длина логики ошибки
        if len(err) < 25:
            stats['short_error_logic'].append((tid, idx, err))
            task_flawed = True
            
        # Неэкранированные степени x^2 вместо x^{2}
        if re.search(r'\^[0-9a-zA-Z](?![0-9a-zA-Z{])', vl):
            stats['unbraced_powers_distractor'].append((tid, idx, vl))
            task_flawed = True
            
        seen_dist_vals.append(vl_clean)
        
    # Дубликаты дистракторов
    if len(seen_dist_vals) != len(set(seen_dist_vals)) and len(seen_dist_vals) > 1:
        stats['duplicate_distractors'].append((tid, seen_dist_vals))
        task_flawed = True
        
    if not task_flawed:
        stats['clean_flawless'] += 1

print("==================================================================")
print("📊 РЕЗУЛЬТАТЫ ГЛУБОКОГО АУДИТА ВСЕХ 35 198 ЗАДАЧ")
print("==================================================================\n")
print(f"✅ Абсолютно безупречных задач со 100% прохождением всех гейтов: {stats['clean_flawless']} ({stats['clean_flawless']*100/total:.2f}%)\n")

print("--- ОБНАРУЖЕННЫЕ ДЕТАЛЬНЫЕ ДЕФЕКТЫ ДЛЯ ПОЛНОГО УСТРАНЕНИЯ ---")
print(f"1. Ошибки KaTeX в вопросе                 : {len(stats['invalid_katex_question']):5d}")
print(f"2. Ошибки KaTeX в ответе                  : {len(stats['invalid_katex_answer']):5d}")
print(f"3. Ошибки KaTeX в дистракторах            : {len(stats['invalid_katex_distractor']):5d}")
print(f"4. Дистрактор совпадает с ответом (D = A) : {len(stats['distractor_equals_answer']):5d}")
print(f"5. Дубликаты среди дистракторов (D_i=D_j) : {len(stats['duplicate_distractors']):5d}")
print(f"6. Короткое описание ошибки (< 25 симв.)  : {len(stats['short_error_logic']):5d}")
print(f"7. Недостаточно дистракторов (< 3 шт.)    : {len(stats['less_than_3_distractors']):5d}")
print(f"8. Неэкранированные степени в дистракторах: {len(stats['unbraced_powers_distractor']):5d}")

# Сохраняем списки проблемных ID в json для прицельного исправления
with open('/tmp/flawed_tasks_audit.json', 'w', encoding='utf-8') as f:
    json.dump({
        'missing_distractors': stats['missing_distractors'],
        'less_than_3_distractors': [x[0] for x in stats['less_than_3_distractors']],
        'distractor_equals_answer': [x[0] for x in stats['distractor_equals_answer']],
        'duplicate_distractors': [x[0] for x in stats['duplicate_distractors']],
        'short_error_logic': [x[0] for x in stats['short_error_logic']],
        'invalid_katex_distractor': [x[0] for x in stats['invalid_katex_distractor']],
        'unbraced_powers_distractor': [x[0] for x in stats['unbraced_powers_distractor']]
    }, f, ensure_ascii=False, indent=2)

print("\n📦 Списки проблемных ID сохранены в /tmp/flawed_tasks_audit.json для автоматического устранения.")
