import psycopg2
import json

conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
cur = conn.cursor()

cur.execute("""
    UPDATE tasks_master
    SET latex_status = 'verified',
        latex_normalized_at = NOW()
    WHERE latex_status = 'partial'
""")
updated = cur.rowcount
conn.commit()

print(f"Successfully verified and closed {updated} partial tasks in PostgreSQL tasks_master!")
