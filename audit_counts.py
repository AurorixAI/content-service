import psycopg2
from psycopg2.extras import DictCursor
import json
import os

conn = psycopg2.connect(os.getenv('DATABASE_URL', 'postgresql://algo_user:algo_password@postgres:5432/algo_db'))
cur = conn.cursor(cursor_factory=DictCursor)

# Get total tasks processed in this batch (toc_ids for 9th grade algebra, which start around 1015)
# Or we can just count all tasks in textbook_tasks joined with tasks_master created today.
# Since this DB is local, let's just query by toc_id between 1015 and 1050
cur.execute('''
    SELECT 
        COUNT(*) as total_tasks,
        SUM(CASE WHEN distractor_meta IS NULL OR jsonb_array_length(distractor_meta) = 0 THEN 1 ELSE 0 END) as distractor_failed,
        SUM(CASE WHEN correct_answer IS NULL OR correct_answer = '' THEN 1 ELSE 0 END) as answer_empty
    FROM tasks_master 
    WHERE toc_id >= 1015
''')
res = cur.fetchone()

print(f"Total tasks: {res['total_tasks']}")
print(f"Failed distractors (in quarantine): {res['distractor_failed']}")
print(f"Empty answers (broken latex/JSON): {res['answer_empty']}")
