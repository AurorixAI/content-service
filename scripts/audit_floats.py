import psycopg2
import json
from src.core.config import get_settings

def main():
    conn = psycopg2.connect(get_settings().database_url)
    cur = conn.cursor()
    cur.execute('''
        SELECT tm.id, tm.question_text, tm.correct_answer, tm.correct_answer_latex, tm.distractor_meta 
        FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE tb.class_level BETWEEN 5 AND 9
          AND tm.updated_at > '2026-07-12 09:10:00'
        ORDER BY tm.updated_at DESC
    ''')
    
    rows = cur.fetchall()
    print(f"Found {len(rows)} tasks updated recently.")
    
    # Audit and print details
    for i, (tid, qt, ans, cal, dmeta_json) in enumerate(rows[:15]):
        print(f"\n[{i+1}] Task ID: {tid}")
        print(f"Question: {qt[:100]}")
        print(f"Original Answer: {ans}")
        print(f"LaTeX Answer: {cal}")
        if dmeta_json:
            try:
                dmeta = json.loads(dmeta_json) if isinstance(dmeta_json, str) else dmeta_json
                print("Distractors:")
                for d in dmeta:
                    if isinstance(d, dict):
                        print(f"  - Value: {d.get('value')} | LaTeX: {d.get('value_latex')}")
            except Exception as e:
                print(f"  Error parsing distractors: {e}")
        print("-" * 60)

if __name__ == "__main__":
    main()
