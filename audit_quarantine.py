import psycopg2
from psycopg2.extras import DictCursor
import json
import os

conn = psycopg2.connect(os.getenv('DATABASE_URL', 'postgresql://algo_user:algo_password@postgres:5432/algo_db'))
cur = conn.cursor(cursor_factory=DictCursor)

# Count by distractor skip reason proxy - we can check logs or just look at answer types
# First, let's see breakdown by answer_type for quarantined tasks
cur.execute('''
    SELECT 
        answer_type,
        COUNT(*) as cnt
    FROM tasks_master 
    WHERE toc_id >= 1015
    AND (distractor_meta IS NULL OR jsonb_array_length(distractor_meta) = 0)
    GROUP BY answer_type
    ORDER BY cnt DESC
''')
print("=== Quarantined tasks breakdown by answer_type ===")
for row in cur.fetchall():
    print(f"  {row['answer_type']}: {row['cnt']}")

# Check if there are tasks where correct_answer contains something (not just empty)
cur.execute('''
    SELECT 
        COUNT(*) as has_answer,
        COUNT(CASE WHEN correct_answer IS NULL OR correct_answer = '' THEN 1 END) as no_answer
    FROM tasks_master 
    WHERE toc_id >= 1015
    AND (distractor_meta IS NULL OR jsonb_array_length(distractor_meta) = 0)
''')
row = cur.fetchone()
print(f"\n=== Answer presence in quarantined tasks ===")
print(f"  Has correct_answer: {row['has_answer'] - row['no_answer']}")
print(f"  Missing correct_answer: {row['no_answer']}")

# Sample 3 quarantined tasks to see what they look like
cur.execute('''
    SELECT t.id, t.answer_type, t.correct_answer, tt.exercise_number
    FROM tasks_master t
    JOIN textbook_tasks tt ON t.id = tt.task_id
    WHERE t.toc_id >= 1015
    AND (t.distractor_meta IS NULL OR jsonb_array_length(t.distractor_meta) = 0)
    ORDER BY RANDOM()
    LIMIT 5
''')
print(f"\n=== Sample quarantined tasks ===")
for row in cur.fetchall():
    print(f"  Ex.{row['exercise_number']} [{row['answer_type']}] → {row['correct_answer']}")
