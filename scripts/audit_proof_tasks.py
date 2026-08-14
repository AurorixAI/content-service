import psycopg2, json

conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
cur = conn.cursor()

# Все задачи с текстовым доказательством в ответе
cur.execute("""
    SELECT id, question_text, correct_answer, correct_answer_latex, answer_type, distractor_meta
    FROM tasks_master
    WHERE (
        lower(correct_answer) LIKE '%доказательство%'
        OR lower(correct_answer) LIKE '%докажем%'
        OR lower(correct_answer) LIKE '%нужно показать%'
        OR lower(correct_answer) LIKE '%построим%'
        OR lower(correct_answer) LIKE '%постройте%'
        OR lower(correct_answer) LIKE '%по определению%'
        OR lower(correct_answer) LIKE '%рассмотрим%'
    )
    ORDER BY id;
""")
all_proof = cur.fetchall()
print(f"Всего задач с текстовым доказательством в ответе: {len(all_proof)}\n")

# Категории
proof_with_distractors = []
proof_no_distractors = []
proof_wrong_type = []

for tid, q, a, al, at, dm_raw in all_proof:
    dm = []
    if dm_raw:
        try:
            dm = json.loads(dm_raw) if isinstance(dm_raw, str) else dm_raw
        except:
            pass
    if not isinstance(dm, list):
        dm = []
    
    has_distractors = len(dm) > 0

    if has_distractors:
        proof_with_distractors.append((tid, q, a, at, dm))
    else:
        proof_no_distractors.append((tid, q, a, at))
    
    if at != 'text':
        proof_wrong_type.append((tid, at, a[:60]))

print(f"1. С дистракторами (подозрительно): {len(proof_with_distractors)}")
print(f"   Примеры:")
for tid, q, a, at, dm in proof_with_distractors[:5]:
    print(f"   • {tid} | type={at}")
    print(f"     A: {a[:80]}")
    print(f"     D: {[d.get('value', '') for d in dm if isinstance(d, dict)]}")

print(f"\n2. Без дистракторов (ожидаемо):     {len(proof_no_distractors)}")
print(f"   Примеры:")
for tid, q, a, at in proof_no_distractors[:3]:
    print(f"   • {tid} | type={at}")
    print(f"     A: {a[:80]}")

print(f"\n3. Неверный answer_type (не text):  {len(proof_wrong_type)}")
for tid, at, a in proof_wrong_type[:5]:
    print(f"   • {tid} | type={at} | A: {a}")
