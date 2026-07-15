import psycopg2
import json
from src.core.config import get_settings

def has_russian_in_math(text: str) -> bool:
    if not text or '$' not in text:
        return False
    parts = text.split('$')
    # Every odd index part is inside dollar signs
    for i in range(1, len(parts), 2):
        if any('а' <= c <= 'я' or 'А' <= c <= 'Я' for c in parts[i]):
            return True
    return False

def has_sympy_leaks(text: str) -> bool:
    if not text:
        return False
    return any(op in text for op in ['&', '|', 'oo', '~'])

def main():
    conn = psycopg2.connect(get_settings().database_url)
    cur = conn.cursor()
    cur.execute('''
        SELECT tm.id, tm.correct_answer_latex, tm.distractor_meta FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE tb.class_level = 9 AND tm.is_active = true
    ''')
    
    total = 0
    ru_ans = 0
    sympy_ans = 0
    ru_dist = 0
    sympy_dist = 0
    empty_ans = 0
    empty_dist = 0
    
    matched_ids = []
    
    for tid, cal, dmeta_json in cur.fetchall():
        cal = cal or ""
        is_buggy = False
        
        # Check answer
        if not cal:
            empty_ans += 1
            is_buggy = True
        elif has_russian_in_math(cal):
            ru_ans += 1
            is_buggy = True
        elif has_sympy_leaks(cal):
            sympy_ans += 1
            is_buggy = True
            
        # Check distractors
        if dmeta_json:
            try:
                dmeta = json.loads(dmeta_json) if isinstance(dmeta_json, str) else dmeta_json
                has_empty = False
                has_ru = False
                has_sympy = False
                for d in dmeta:
                    if isinstance(d, dict):
                        val_latex = d.get("value_latex") or ""
                        if not val_latex:
                            has_empty = True
                        elif has_russian_in_math(val_latex):
                            has_ru = True
                        elif has_sympy_leaks(val_latex):
                            has_sympy = True
                if has_empty:
                    empty_dist += 1
                    is_buggy = True
                if has_ru:
                    ru_dist += 1
                    is_buggy = True
                if has_sympy:
                    sympy_dist += 1
                    is_buggy = True
            except Exception as e:
                pass
                
        if is_buggy:
            total += 1
            matched_ids.append(tid)
            
    print("Exact stats for Grade 9 active tasks:")
    print(f"Total buggy tasks needing backfill: {total}")
    print(f"- Empty/null answers: {empty_ans}")
    print(f"- Russian inside answer math mode: {ru_ans}")
    print(f"- SymPy leaks in answer: {sympy_ans}")
    print(f"- Empty/null distractor LaTeX: {empty_dist}")
    print(f"- Russian inside distractor math mode: {ru_dist}")
    print(f"- SymPy leaks in distractor: {sympy_dist}")
    print(f"Sample buggy IDs (first 10): {matched_ids[:10]}")

if __name__ == "__main__":
    main()
