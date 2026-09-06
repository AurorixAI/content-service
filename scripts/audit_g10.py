import psycopg2
from psycopg2.extras import DictCursor
import json
import os
import re

db_url = os.getenv('DATABASE_URL', 'postgresql://algo:algo_password@content-postgres:5432/algo_content')
conn = psycopg2.connect(db_url)
cur = conn.cursor(cursor_factory=DictCursor)

textbook_id = 'e92457e0-c22d-4485-b838-6962ecd7413f'

print("--- Running Grade 10 Database Quality Audit ---")

# 1. Core Metrics
cur.execute('''
    SELECT 
        COUNT(*) as total_tasks,
        SUM(CASE WHEN tm.question_latex IS NULL OR tm.question_latex = '' THEN 1 ELSE 0 END) as empty_questions,
        SUM(CASE WHEN tm.correct_answer IS NULL OR tm.correct_answer = '' THEN 1 ELSE 0 END) as empty_answers,
        SUM(CASE WHEN tm.verification_status = 'verified' THEN 1 ELSE 0 END) as verified_tasks,
        SUM(CASE WHEN tm.verification_status = 'pending' THEN 1 ELSE 0 END) as pending_tasks
    FROM tasks_master tm
    JOIN textbook_toc toc ON toc.id = tm.toc_id
    WHERE toc.textbook_id = %s
''', (textbook_id,))
core = cur.fetchone()

print(f"Total tasks: {core['total_tasks']}")
print(f"Empty questions: {core['empty_questions']}")
print(f"Empty answers: {core['empty_answers']}")
print(f"Verified tasks: {core['verified_tasks']}")
print(f"Pending tasks: {core['pending_tasks']}")

# 2. Re-verified breakdown
cur.execute('''
    SELECT 
        SUM(CASE WHEN tm.tags ->> 'reverified_by' = 'deepseek_school' AND NOT (tm.tags -> 'sympy_verified')::boolean THEN 1 ELSE 0 END) as verified_by_deepseek_only,
        SUM(CASE WHEN (tm.tags -> 'sympy_verified')::boolean THEN 1 ELSE 0 END) as sympy_verified,
        SUM(CASE WHEN tm.tags ->> 'reverified_by' IS NOT NULL THEN 1 ELSE 0 END) as total_reverified
    FROM tasks_master tm
    JOIN textbook_toc toc ON toc.id = tm.toc_id
    WHERE toc.textbook_id = %s AND tm.verification_status = 'verified'
''', (textbook_id,))
verification = cur.fetchone()
print(f"Total reverified: {verification['total_reverified']}")
print(f"SymPy verified (direct matching): {verification['sympy_verified']}")
print(f"DeepSeek school verified (advanced): {verification['verified_by_deepseek_only']}")

# 3. Corrections vs Matches
cur.execute('''
    SELECT 
        COUNT(*) as corrected_count
    FROM tasks_master tm
    JOIN textbook_toc toc ON toc.id = tm.toc_id
    WHERE toc.textbook_id = %s AND tm.verification_status = 'verified' AND (tm.tags ->> 'corrected_school_answer')::boolean = true
''', (textbook_id,))
corrections = cur.fetchone()
print(f"Textbook corrections made: {corrections['corrected_count']}")

# 4. Invalid tasks and errors in pending
cur.execute('''
    SELECT 
        SUM(CASE WHEN (tm.tags ->> 'invalid_task')::boolean = true THEN 1 ELSE 0 END) as invalid_tasks,
        SUM(CASE WHEN tm.tags ->> 'verification_failed_reason' IS NOT NULL THEN 1 ELSE 0 END) as failed_tasks
    FROM tasks_master tm
    JOIN textbook_toc toc ON toc.id = tm.toc_id
    WHERE toc.textbook_id = %s AND tm.verification_status = 'pending'
''', (textbook_id,))
pending_breakdown = cur.fetchone()
print(f"Invalid tasks (missing graphic): {pending_breakdown['invalid_tasks']}")
print(f"Failed verification tasks: {pending_breakdown['failed_tasks']}")

# 5. Distractor JSON integrity
cur.execute('''
    SELECT tm.id, tm.distractor_meta
    FROM tasks_master tm
    JOIN textbook_toc toc ON toc.id = tm.toc_id
    WHERE toc.textbook_id = %s
''', (textbook_id,))
tasks = cur.fetchall()

invalid_distractor_jsons = 0
for t in tasks:
    meta = t['distractor_meta']
    if meta is not None:
        try:
            if isinstance(meta, str):
                json.loads(meta)
        except Exception:
            invalid_distractor_jsons += 1

print(f"Invalid distractor JSONs: {invalid_distractor_jsons}")

# 6. Syntax Checks (Leaks & Bad Symbols in math blocks)
sympy_leaks = 0
russian_in_math = 0

# Check raw fields for sympy characters & unescaped Russian text inside $...$
for t in tasks:
    # We can check LaTeX field using regex
    cur.execute('SELECT question_latex, correct_answer_latex FROM tasks_master WHERE id = %s', (t['id'],))
    latex_data = cur.fetchone()
    ql = latex_data['question_latex'] or ''
    al = latex_data['correct_answer_latex'] or ''
    
    # Check for raw SymPy symbols like &, ~, | (avoiding TikZ parameters or case blocks)
    # A raw SymPy leak usually has spaces or is clearly out of LaTeX context
    for s in [ql, al]:
        # Simple heuristic check for raw SymPy leak characters
        if ' & ' in s or ' ~ ' in s or ' | ' in s:
            sympy_leaks += 1
            
        # Check for unescaped Russian text inside $...$
        # Find all $...$ math blocks
        math_blocks = re.findall(r'\$(.*?)\$', s)
        for mb in math_blocks:
            # If a block has cyrillic characters and does not have \text{...} or \operatorname{...} wrapping them
            cyrillic = re.findall(r'[а-яА-ЯёЁ]', mb)
            if cyrillic:
                # Basic check: if the cyrillic characters are not inside a \text{...} block
                clean_mb = mb
                # Remove \text{...} blocks
                clean_mb = re.sub(r'\\text\{.*?\}', '', clean_mb)
                clean_mb = re.sub(r'\\operatorname\{.*?\}', '', clean_mb)
                if re.findall(r'[а-яА-ЯёЁ]', clean_mb):
                    russian_in_math += 1
                    break

print(f"SymPy syntax leaks: {sympy_leaks}")
print(f"Illegal Russian letters inside math blocks: {russian_in_math}")

conn.close()
