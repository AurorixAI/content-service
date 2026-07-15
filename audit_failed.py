import psycopg2
import json
from src.core.config import get_settings

def main():
    conn = psycopg2.connect(get_settings().database_url)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, answer_type, correct_answer, tags->>'smart_verify_error', tags->>'answer_gemini_candidate', question_text
        FROM tasks_master 
        WHERE id LIKE 'G9_%'
          AND tags->>'smart_verify_status' = 'failed_at_sympy'
        ORDER BY id
    """)
    res = cur.fetchall()
    print(f"Fetched {len(res)} tasks")
    
    with open("/app/failed_tasks.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    conn.close()

if __name__ == "__main__":
    main()
