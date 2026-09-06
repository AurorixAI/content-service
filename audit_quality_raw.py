import psycopg2
from psycopg2.extras import DictCursor
import json
import os

conn = psycopg2.connect(os.getenv('DATABASE_URL', 'postgresql://algo_user:algo_password@postgres:5432/algo_db'))
cur = conn.cursor(cursor_factory=DictCursor)

cur.execute('''
    SELECT t.distractor_meta 
    FROM tasks_master t 
    WHERE t.toc_id IN (1015, 1016)
    AND t.distractor_meta IS NOT NULL 
    AND jsonb_array_length(t.distractor_meta) > 0
    LIMIT 2
''')
tasks = cur.fetchall()

for t in tasks:
    print(json.dumps(t['distractor_meta'], indent=2, ensure_ascii=False))
