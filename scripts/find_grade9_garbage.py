import os
import re
import json
import psycopg2
from src.core.config import get_settings

def is_garbage(qt: str, ans: str) -> tuple[bool, str]:
    qt_clean = re.sub(r"\s+", " ", qt).strip()
    ans_clean = re.sub(r"\s+", " ", ans).strip()
    
    if not qt_clean:
        return True, "Empty question"
    
    # 1. Answer in question text directly (complete overlap)
    if ans_clean and ans_clean.lower() in qt_clean.lower():
        # But wait, some text-based proof questions might contain it, e.g. "Докажите тождество..."
        # If question is "Докажите тождество..." and answer is "Тождество верно", it's fine.
        if "докажите" in qt_clean.lower() or "свойства функции" in qt_clean.lower() or "тождество" in qt_clean.lower():
            return False, ""
            
        # Check if the question text after colon or space is just the answer
        if ":" in qt_clean:
            tail = qt_clean.split(":", 1)[-1].strip()
            # Remove units like м., см., кг.
            tail_clean = re.sub(r"\s*(м|см|дм|мм|кг|г|л|°)\.?$", "", tail, flags=re.I).strip()
            ans_no_units = re.sub(r"\s*(м|см|дм|мм|кг|г|л|°)\.?$", "", ans_clean, flags=re.I).strip()
            if tail_clean == ans_no_units or tail_clean == f"a) {ans_no_units}" or tail_clean == f"б) {ans_no_units}" or tail_clean == f"в) {ans_no_units}" or tail_clean == f"г) {ans_no_units}":
                return True, f"Answer is the question tail after colon: '{tail}'"
        
        # If the question is extremely short and just contains the answer
        if len(qt_clean) < 30 and (ans_clean in qt_clean or re.sub(r"\D", "", ans_clean) in qt_clean):
            # Check if it's a valid simple prompt
            if not any(word in qt_clean.lower() for word in ["найдите", "решите", "вычислите", "упростите"]):
                return True, f"Short question containing answer: '{qt_clean}'"

    # 2. Nonsense math stubs
    # E.g. "Решите неравенство: a) [-7; 6]" or "Решите неравенство: a) (-11; -4) ∪ (1; +∞)"
    if "неравенство" in qt_clean.lower() and ":" in qt_clean:
        tail = qt_clean.split(":", 1)[-1].strip()
        # If the tail is already an interval, that's nonsense (you solve inequalities, not intervals)
        if re.match(r"^[a-zA-Z\s\)]*[\[\()]-?\d+.*[\]\)]$", tail):
            return True, f"Nonsense inequality tail (interval instead of expression): '{tail}'"
            
    # 3. Missing condition placeholders
    if any(p in qt_clean.lower() for p in ["не дано", "нет условия", "не указано", "без условия"]):
        return True, "Contains missing condition placeholder"
        
    return False, ""

def main():
    conn = psycopg2.connect(get_settings().database_url)
    cur = conn.cursor()
    
    # Query all tasks for Grade 9
    cur.execute("""
        SELECT tm.id, tm.question_text, tm.correct_answer, tm.is_active
        FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE tb.class_level = 9
        ORDER BY tm.id
    """)
    rows = cur.fetchall()
    
    garbage_tasks = []
    for tid, qt, ans, is_active in rows:
        garbage, reason = is_garbage(qt or "", ans or "")
        if garbage:
            garbage_tasks.append({
                "id": tid,
                "question": qt,
                "answer": ans,
                "is_active": is_active,
                "reason": reason
            })
            
    print(f"Total Grade 9 tasks: {len(rows)}")
    print(f"Found garbage tasks: {len(garbage_tasks)}")
    print(json.dumps(garbage_tasks, ensure_ascii=False, indent=2))
    
    # Deactivate them
    for t in garbage_tasks:
        cur.execute("UPDATE tasks_master SET is_active = false WHERE id = %s", (t["id"],))
    conn.commit()
    print("Successfully deactivated all garbage tasks!")

if __name__ == "__main__":
    main()
