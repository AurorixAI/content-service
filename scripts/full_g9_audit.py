import psycopg2, os
import psycopg2.extras

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

# ─── 1. Total tasks by paragraph (toc_id) ───────────────────────────────────
cur.execute('''
    SELECT 
        toc.id as toc_id,
        toc.title,
        COUNT(*) as total,
        SUM(CASE WHEN tm.distractor_meta IS NOT NULL AND jsonb_array_length(tm.distractor_meta) >= 3 THEN 1 ELSE 0 END) as has_distractors,
        SUM(CASE WHEN tm.tags->>'quarantine_v3_verified' = 'true' OR tm.tags->>'smart_verify_status' IN ('confirmed','ai_consensus_override') THEN 1 ELSE 0 END) as verified,
        SUM(CASE WHEN tm.tags->>'quarantine_v3_needs_review' = 'true' THEN 1 ELSE 0 END) as in_review,
        SUM(CASE WHEN tm.tags->>'quarantine_v3_sympy_proven' = 'true' THEN 1 ELSE 0 END) as sympy_proven,
        SUM(CASE WHEN tm.answer_type = 'text' OR tm.answer_type = 'open_text' THEN 1 ELSE 0 END) as text_type,
        SUM(CASE WHEN tm.question_text ILIKE '%не дано%' OR tm.question_text ILIKE '%не указано%' THEN 1 ELSE 0 END) as ocr_garbage
    FROM tasks_master tm
    JOIN textbook_toc toc ON toc.id = tm.toc_id
    WHERE tm.toc_id >= 1015
    GROUP BY toc.id, toc.title
    ORDER BY toc.id
''')
para_rows = [dict(r) for r in cur.fetchall()]

# ─── 2. Overall summary ───────────────────────────────────────────────────────
cur.execute('''
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN tm.distractor_meta IS NOT NULL AND jsonb_array_length(tm.distractor_meta) >= 3 THEN 1 ELSE 0 END) as has_distractors,
        SUM(CASE WHEN tm.distractor_meta IS NOT NULL AND jsonb_array_length(tm.distractor_meta) >= 1 THEN 1 ELSE 0 END) as has_any_distractors,
        SUM(CASE WHEN tm.tags->>'quarantine_v3_sympy_proven' = 'true' THEN 1 ELSE 0 END) as sympy_proven,
        SUM(CASE WHEN tm.tags->>'quarantine_v3_needs_review' = 'true' THEN 1 ELSE 0 END) as in_review,
        SUM(CASE WHEN tm.tags->>'quarantine_v3_verified' = 'true' THEN 1 ELSE 0 END) as q3_verified,
        SUM(CASE WHEN tm.tags->>'smart_verify_status' IN ('confirmed','ai_consensus_override') THEN 1 ELSE 0 END) as smart_verified,
        SUM(CASE WHEN tm.question_text ILIKE '%не дано%' OR tm.question_text ILIKE '%не указано%' THEN 1 ELSE 0 END) as ocr_garbage,
        SUM(CASE WHEN length(tm.question_text) < 40 AND tm.question_text NOT ILIKE '%не дано%' AND tm.question_text NOT ILIKE '%=%' AND tm.question_text NOT ILIKE '%<%' THEN 1 ELSE 0 END) as short_q
    FROM tasks_master tm
    WHERE tm.toc_id >= 1015
''')
summary = dict(cur.fetchone())

# ─── 3. Distractor quality breakdown ─────────────────────────────────────────
cur.execute('''
    SELECT 
        answer_type,
        COUNT(*) as total,
        SUM(CASE WHEN distractor_meta IS NOT NULL AND jsonb_array_length(distractor_meta) >= 3 THEN 1 ELSE 0 END) as good_distractors,
        SUM(CASE WHEN distractor_meta IS NULL OR jsonb_array_length(distractor_meta) = 0 THEN 1 ELSE 0 END) as no_distractors
    FROM tasks_master
    WHERE toc_id >= 1015
    GROUP BY answer_type
    ORDER BY total DESC
''')
distractor_by_type = [dict(r) for r in cur.fetchall()]

# ─── 4. Skills coverage ───────────────────────────────────────────────────────
cur.execute('''
    SELECT 
        COUNT(*) as total_tasks,
        SUM(CASE WHEN tm.tags->'skill_ids' IS NOT NULL AND jsonb_array_length(tm.tags->'skill_ids') > 0 THEN 1 ELSE 0 END) as has_skills,
        SUM(CASE WHEN tm.tags->'skills' IS NOT NULL AND jsonb_array_length(tm.tags->'skills') > 0 THEN 1 ELSE 0 END) as has_skills_alt
    FROM tasks_master tm
    WHERE tm.toc_id >= 1015
''')
skills = dict(cur.fetchone())

# ─── 5. Check para 31 specifically (most problematic, being re-digitized) ─────
cur.execute('''
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN tm.distractor_meta IS NOT NULL AND jsonb_array_length(tm.distractor_meta) >= 3 THEN 1 ELSE 0 END) as has_distractors,
        SUM(CASE WHEN tm.tags->>'quarantine_v3_needs_review' = 'true' THEN 1 ELSE 0 END) as in_review,
        SUM(CASE WHEN tm.question_text ILIKE '%не дано%' OR tm.question_text ILIKE '%не указано%' THEN 1 ELSE 0 END) as ocr_garbage,
        SUM(CASE WHEN tm.tags->>'quarantine_v3_sympy_proven' = 'true' THEN 1 ELSE 0 END) as sympy_proven
    FROM tasks_master tm
    WHERE tm.toc_id = 1046
''')
para31 = dict(cur.fetchone())

import json
result = {
    'summary': summary,
    'para_rows': para_rows,
    'distractor_by_type': distractor_by_type,
    'skills': skills,
    'para31': para31
}
with open('/app/data/full_audit.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print('Done')
