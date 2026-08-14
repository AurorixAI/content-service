import psycopg2
import json
import re

conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
cur = conn.cursor()

cur.execute("""
    SELECT id, question_text, correct_answer, correct_answer_latex, distractor_meta, answer_options, answer_options_latex
    FROM tasks_master
    WHERE verification_status = 'verified';
""")
rows = cur.fetchall()
total_verified = len(rows)

missing_dmeta = 0
not_enough_dist = 0
duplicate_dist = 0
dist_equals_answer = 0
short_error_logic = 0
generic_error_logic = 0
invalid_latex = 0
perfect_distractors = 0

GENERIC_PHRASES = [
    'ошибка в расчете', 'ошибка в вычислениях', 'неправильный ответ',
    'случайная ошибка', 'неверный вариант', 'ошибка ученика'
]

samples = []

for r in rows:
    tid, qt, ca, cal, dm_raw, ao, aol = r
    
    if isinstance(dm_raw, str):
        try:
            dm = json.loads(dm_raw)
        except Exception:
            dm = []
    elif isinstance(dm_raw, list):
        dm = dm_raw
    else:
        dm = []
        
    if not dm:
        missing_dmeta += 1
        continue
        
    # Проверка количества
    is_binary = str(ca).strip().lower() in {'да', 'нет', 'верно', 'неверно', 'true', 'false'}
    min_count = 1 if is_binary else 3
    if len(dm) < min_count:
        not_enough_dist += 1
        
    ans_clean = str(cal or ca or '').strip().replace('$', '')
    dist_vals = []
    has_issue = False
    
    for idx, d in enumerate(dm):
        if not isinstance(d, dict):
            continue
        v = str(d.get('value') or '').strip()
        vl = str(d.get('value_latex') or v).strip().replace('$', '')
        err = str(d.get('error_logic') or d.get('explanation') or '').strip()
        
        # 1. Равенство ответу
        if vl.lower() == ans_clean.lower() or v.lower() == ans_clean.lower():
            dist_equals_answer += 1
            has_issue = True
            
        # 2. Длина error_logic
        if len(err) < 25:
            short_error_logic += 1
            has_issue = True
            
        # 3. Шаблонность error_logic
        if any(gp in err.lower() for gp in GENERIC_PHRASES) and len(err) < 40:
            generic_error_logic += 1
            has_issue = True
            
        # 4. Проверка скобок LaTeX
        if vl.count('{') != vl.count('}') or vl.count('(') != vl.count(')'):
            invalid_latex += 1
            has_issue = True
            
        dist_vals.append(vl.lower())
        
    # 5. Дубликаты среди дистракторов
    if len(dist_vals) != len(set(dist_vals)) and len(dist_vals) > 1:
        duplicate_dist += 1
        has_issue = True
        
    if not has_issue and len(dm) >= min_count:
        perfect_distractors += 1
        if len(samples) < 5:
            samples.append((tid, qt, ca, dm))

print("==================================================================")
print("🔍 ГЛУБОКИЙ АУДИТ КАЧЕСТВА ДИСТРАКТОРОВ И ERROR_LOGIC")
print("==================================================================\n")
print(f"Всего проверено верифицированных задач: {total_verified}\n")

print("--- 1. СТАТИСТИКА ПРОХОЖДЕНИЯ ГЕЙТОВ ---")
print(f"  • Идеально соответствуют всем гейтам : {perfect_distractors:5d} ({perfect_distractors*100/total_verified:.2f}%)")
print(f"  • Задач без дистракторов             : {missing_dmeta:5d} ({missing_dmeta*100/total_verified:.2f}%)")
print(f"  • Недостаточно дистракторов (<3)     : {not_enough_dist:5d} ({not_enough_dist*100/total_verified:.2f}%)")
print(f"  • Совпадение дистрактора с ответом   : {dist_equals_answer:5d} ({dist_equals_answer*100/total_verified:.2f}%)")
print(f"  • Дублирование между дистракторами   : {duplicate_dist:5d} ({duplicate_dist*100/total_verified:.2f}%)")
print(f"  • Короткое описание (<25 символов)   : {short_error_logic:5d} ({short_error_logic*100/total_verified:.2f}%)")
print(f"  • Шаблонное описание ошибки          : {generic_error_logic:5d} ({generic_error_logic*100/total_verified:.2f}%)")
print(f"  • Ошибки скобок в LaTeX дистракторов : {invalid_latex:5d} ({invalid_latex*100/total_verified:.2f}%)")

print("\n--- 2. РЕАЛЬНЫЕ ПРИМЕРЫ ДИСТРАКТОРОВ И ПЕДАГОГИЧЕСКОЙ ЛОГИКИ ОШИБОК ---")
for tid, qt, ca, dm in samples:
    print(f"\n📌 ЗАДАЧА [{tid}]")
    print(f"  Условие: {qt[:90]}...")
    print(f"  Правильный ответ: {ca}")
    print("  Дистракторы и логика ошибок:")
    for idx, d in enumerate(dm):
        val = d.get('value_latex') or d.get('value')
        err = d.get('error_logic') or d.get('explanation')
        print(f"    [{idx+1}] Вариант: {val}")
        print(f"        Ошибка: {err}")
