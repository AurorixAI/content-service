import psycopg2, json, re

conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
cur = conn.cursor()

# Находим все задачи где correct_answer = 'Доказательство' (буквально)
cur.execute("""
    SELECT id, question_text, correct_answer, correct_answer_latex, distractor_meta, answer_type
    FROM tasks_master
    WHERE trim(correct_answer) IN ('Доказательство', 'доказательство', 'Доказательство.', 'доказательство.')
    ORDER BY id;
""")
rows = cur.fetchall()
print(f"Задач с ответом буквально 'Доказательство': {len(rows)}\n")

# Признак Категории А (ответ = правая часть тождества):
# Дистракторы — это ЧИСЛА или ВЫРАЖЕНИЯ (короткие, математические), не рассуждения
# Признак Категории В (ответ = правильное рассуждение):
# Дистракторы — длинные тексты или цепочки рассуждений

cat_a = []  # тождества — нужно извлечь RHS из вопроса
cat_b = []  # доказательства-рассуждения — всё нормально, просто лейбл

for tid, q, ca, cal, dm_raw, at in rows:
    dm = json.loads(dm_raw) if isinstance(dm_raw, str) and dm_raw else (dm_raw or [])
    if not isinstance(dm, list) or not dm:
        cat_b.append((tid, q, ca, cal, dm))
        continue
    # Смотрим на длину значения первого дистрактора
    d0 = dm[0] if isinstance(dm[0], dict) else {}
    d0_val = str(d0.get('value_latex') or d0.get('value') or '')
    # Если дистрактор длинный (>80 симв.) — это рассуждение (кат. В)
    if len(d0_val) > 80:
        cat_b.append((tid, q, ca, cal, dm))
    else:
        cat_a.append((tid, q, ca, cal, dm))

print(f"Категория А (тождества, нужна правая часть): {len(cat_a)}")
for tid, q, ca, cal, dm in cat_a[:5]:
    print(f"  • {tid}: {q[:80]}")
    
print(f"\nКатегория В (рассуждения-доказательства, структура ОК): {len(cat_b)}")
for tid, q, ca, cal, dm in cat_b[:5]:
    print(f"  • {tid}: {q[:80]}")
