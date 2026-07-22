import psycopg2
import os

db_url = os.getenv('DATABASE_URL', 'postgresql://algo:algo_password@content-postgres:5432/algo_content')
conn = psycopg2.connect(db_url)
cur = conn.cursor()

task_ids = [
    'G10_TB_§1_1_1_2',
    'G10_TB_§1_1_2_2',
    'G10_TB_§39_39_1',
    'G10_TB_§14_14_37',
    'G10_TB_§35_35_21',
    'G10_TB_§27_26_13_2',
    'G10_TB_§17_17_4_а',
    'G10_TB_§1_1_1_1',
    'G10_TB_§17_17_4_б',
    'G10_TB_§14_14_38',
    'G10_TB_§17_17_3_а',
    'G10_TB_§1_1_17',
    'G10_TB_§1_1_2_1',
    'G10_TB_§35_35_16',
    'G10_TB_§3_3_1'
]

print(f"Starting deletion of {len(task_ids)} pending tasks...")

try:
    # 1. Delete from task_figure_refs
    cur.execute('''
        DELETE FROM task_figure_refs
        WHERE task_id = ANY(%s)
    ''', (task_ids,))
    refs_deleted = cur.rowcount
    print(f"Deleted {refs_deleted} rows from task_figure_refs.")

    # 2. Delete from textbook_tasks
    cur.execute('''
        DELETE FROM textbook_tasks
        WHERE task_id = ANY(%s)
    ''', (task_ids,))
    tb_tasks_deleted = cur.rowcount
    print(f"Deleted {tb_tasks_deleted} rows from textbook_tasks.")

    # 3. Delete from tasks_master
    cur.execute('''
        DELETE FROM tasks_master
        WHERE id = ANY(%s)
    ''', (task_ids,))
    master_deleted = cur.rowcount
    print(f"Deleted {master_deleted} rows from tasks_master.")

    conn.commit()
    print("Transaction successfully committed! The database is now perfectly clean.")
except Exception as e:
    conn.rollback()
    print(f"Error during deletion transaction, rolled back: {e}")
finally:
    conn.close()
