import psycopg2, json, re, sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.pipeline.deepseek_client import call_deepseek, get_deepseek_model, parse_json_response

conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
cur = conn.cursor()

cur.execute("""
    SELECT id, question_text, correct_answer, distractor_meta, answer_type
    FROM tasks_master
    WHERE trim(correct_answer) IN ('Доказательство', 'доказательство', 'Доказательство.', 'доказательство.')
    ORDER BY id;
""")
rows = cur.fetchall()

SYSTEM = """Ты — математик-эксперт. Для задачи типа «Докажите тождество» тебе нужно определить:
1. Правая часть тождества (correct_answer) — краткое математическое выражение-результат, которое доказывается.
2. Тип ответа (answer_type): если задача — «Докажите тождество $A = B$», то correct_answer = $B$ (правая часть), answer_type = 'expression'. Если задача — «Докажите неравенство / докажите что...» без явной числовой правой части, correct_answer = 'Доказательство', answer_type = 'text'.

Верни JSON:
{"correct_answer": "...", "correct_answer_latex": "...", "answer_type": "expression|text"}"""

fixed = 0
kept = 0

for tid, q, ca, dm_raw, at in rows:
    dm = json.loads(dm_raw) if isinstance(dm_raw, str) and dm_raw else (dm_raw or [])
    if not isinstance(dm, list): dm = []
    
    # Определяем по дистракторам: если они короткие выражения -> Кат. А
    d0 = dm[0] if dm and isinstance(dm[0], dict) else {}
    d0_val = str(d0.get('value_latex') or d0.get('value') or '')
    
    if len(d0_val) > 80:
        # Категория В — рассуждения, структура педагогически корректна
        kept += 1
        print(f"✅ КАТ.В (OK) {tid}: дистракторы — неверные рассуждения")
        continue
    
    # Категория А — нужно извлечь правую часть тождества из вопроса
    # Ищем паттерн "= РЕЗУЛЬТАТ" в конце выражения в вопросе
    # Паттерн: что-то = что-то
    match = re.search(r'=\s*(.{3,60}?)[\$\s]*(?:\.|$)', q.replace('\n', ' '))
    
    prompt = f"""ЗАДАЧА: {q}

Правая часть тождества (correct_answer) — это конкретный математический результат из условия (например: $\\tg\\alpha$, $\\sqrt{2}$, $4\\sin^2\\left(\\frac{{\\alpha-\\beta}}{{2}}\\right)$, $1$).

Верни JSON: {{"correct_answer": "...", "correct_answer_latex": "...", "answer_type": "expression"}}"""
    
    try:
        res = call_deepseek(prompt, system_prompt=SYSTEM, model=get_deepseek_model(), temperature=0.0)
        parsed = parse_json_response(res)
        if parsed and isinstance(parsed, dict) and parsed.get('correct_answer'):
            new_ca = parsed['correct_answer']
            new_cal = parsed.get('correct_answer_latex') or f"${new_ca}$"
            new_at = parsed.get('answer_type', 'expression')
            
            # Обновляем answer_options_latex тоже
            dm_vals = [d.get('value_latex') or d.get('value') for d in dm if isinstance(d, dict)]
            new_aol = [new_cal] + dm_vals
            
            cur.execute("""
                UPDATE tasks_master
                SET correct_answer = %s,
                    correct_answer_latex = %s,
                    answer_type = %s,
                    answer_options_latex = %s,
                    updated_at = NOW()
                WHERE id = %s;
            """, (new_ca, new_cal, new_at, json.dumps(new_aol, ensure_ascii=False), tid))
            conn.commit()
            fixed += 1
            print(f"✨ КАТ.А ИСПРАВЛЕНА {tid}: '{ca}' -> '{new_ca}'")
        else:
            print(f"⚠️ Не удалось извлечь RHS для {tid}")
    except Exception as e:
        print(f"❌ Ошибка для {tid}: {e}")

print(f"\n=== ИТОГ ===")
print(f"✅ Педагогически корректных (Кат.В): {kept}")
print(f"✨ Исправлено тождеств (Кат.А):      {fixed}")
