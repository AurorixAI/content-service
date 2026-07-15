import psycopg2
from psycopg2.extras import DictCursor
import json
import os

conn = psycopg2.connect(os.getenv('DATABASE_URL', 'postgresql://algo_user:algo_password@postgres:5432/algo_db'))
cur = conn.cursor(cursor_factory=DictCursor)

cur.execute('''
    SELECT id, number, title, page_start, page_end 
    FROM textbook_toc 
    WHERE textbook_id = '5a9f7fea-1394-4141-9d58-015972e83acc'
    AND number IS NOT NULL
    ORDER BY id
''')
tocs = cur.fetchall()
print([t['number'] for t in tocs])
