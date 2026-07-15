import psycopg2, psycopg2.extras, json, os, random

conn = psycopg2.connect(os.getenv('DATABASE_URL', 'postgresql://algo_user:algo_password@postgres:5432/algo_db'))
cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

# Separate dual_consensus_failed from verify_unresolved
cur.execute("""
    SELECT
        tt.exercise_number,
        t.answer_type,
        t.correct_answer,
        t.question_text,
        t.tags->>'verify_conflict' as verify_conflict,
        t.tags->>'dual_consensus_failed' as dual_consensus_failed,
        t.tags->>'answer_gemini_candidate' as ai_candidate
    FROM tasks_master t
    JOIN textbook_tasks tt ON t.id = tt.task_id
    WHERE t.toc_id >= 1015
    AND (t.distractor_meta IS NULL OR jsonb_array_length(t.distractor_meta) = 0)
    ORDER BY RANDOM()
    LIMIT 200
""")
tasks = cur.fetchall()

dc_failed = [t for t in tasks if t['dual_consensus_failed']]
vr_unresolved = [t for t in tasks if not t['dual_consensus_failed']]

print(f"=== ИТОГО В КАРАНТИНЕ (выборка 200) ===")
print(f"dual_consensus_failed: {len(dc_failed)} задач  ← РИСК: модели дали РАЗНЫЕ ответы")
print(f"verify_unresolved:     {len(vr_unresolved)} задач  ← НИЗКИЙ РИСК: просто формат не совпал")

print(f"\n=== SAMPLE: dual_consensus_failed (5 шт) ===")
for t in random.sample(dc_failed, min(5, len(dc_failed))):
    q = (t['question_text'] or '').strip()[:120].replace('\n', ' ')
    print(f"\nЗадача №{t['exercise_number']} [{t['answer_type']}]")
    print(f"  Вопрос: {q}")
    print(f"  Ответ учебника (OCR): {t['correct_answer']}")
    if t['ai_candidate']:
        print(f"  ИИ-кандидат (не совпал): {t['ai_candidate']}")

print(f"\n=== SAMPLE: verify_unresolved (3 шт) ===")
for t in random.sample(vr_unresolved, min(3, len(vr_unresolved))):
    q = (t['question_text'] or '').strip()[:120].replace('\n', ' ')
    print(f"\nЗадача №{t['exercise_number']} [{t['answer_type']}]")
    print(f"  Вопрос: {q}")
    print(f"  Ответ учебника (OCR): {t['correct_answer']}")
