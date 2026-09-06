import psycopg2, os, json
import psycopg2.extras

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

# 1. Overall summary — all grade 9 tasks (toc_id >= 1011 where tasks exist)
cur.execute('''
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN distractor_meta IS NOT NULL AND jsonb_array_length(distractor_meta) >= 3 THEN 1 ELSE 0 END) as distractors_3plus,
        SUM(CASE WHEN distractor_meta IS NOT NULL AND jsonb_array_length(distractor_meta) >= 1 THEN 1 ELSE 0 END) as distractors_any,
        SUM(CASE WHEN distractor_meta IS NULL OR jsonb_array_length(distractor_meta) = 0 THEN 1 ELSE 0 END) as no_distractors,
        SUM(CASE WHEN tags->>'quarantine_v3_sympy_proven' = 'true' THEN 1 ELSE 0 END) as sympy_proven,
        SUM(CASE WHEN tags->>'quarantine_v3_needs_review' = 'true' THEN 1 ELSE 0 END) as in_review,
        SUM(CASE WHEN tags->>'quarantine_v3_verified' = 'true' THEN 1 ELSE 0 END) as q3_verified,
        SUM(CASE WHEN tags->>'smart_verify_status' IN ('confirmed','ai_consensus_override') THEN 1 ELSE 0 END) as smart_verified,
        SUM(CASE WHEN question_text ILIKE '%не дано%' OR question_text ILIKE '%не указано%' THEN 1 ELSE 0 END) as ocr_garbage_a,
        SUM(CASE WHEN length(question_text) < 40 AND question_text NOT ILIKE '%=%' AND question_text NOT ILIKE '%не дано%' AND question_text NOT ILIKE '%Реши%' AND question_text NOT ILIKE '%Найди%' AND question_text NOT ILIKE '%Вычисл%' AND question_text NOT ILIKE '%Упрост%' AND question_text NOT ILIKE '%Докаж%' THEN 1 ELSE 0 END) as ocr_garbage_b
    FROM tasks_master tm
    WHERE tm.toc_id >= 1011
''')
summary = dict(cur.fetchone())

# 2. Per-paragraph breakdown
cur.execute('''
    SELECT 
        toc.id as toc_id,
        toc.title,
        toc.number,
        COUNT(*) as total,
        SUM(CASE WHEN tm.distractor_meta IS NOT NULL AND jsonb_array_length(tm.distractor_meta) >= 3 THEN 1 ELSE 0 END) as distractors_ok,
        SUM(CASE WHEN tm.distractor_meta IS NULL OR jsonb_array_length(tm.distractor_meta) = 0 THEN 1 ELSE 0 END) as no_distractors,
        SUM(CASE WHEN tm.tags->>'quarantine_v3_needs_review' = 'true' THEN 1 ELSE 0 END) as in_review,
        SUM(CASE WHEN tm.tags->>'quarantine_v3_sympy_proven' = 'true' THEN 1 ELSE 0 END) as sympy_proven,
        SUM(CASE WHEN tm.question_text ILIKE '%не дано%' OR tm.question_text ILIKE '%не указано%' THEN 1 ELSE 0 END) as ocr_garbage
    FROM tasks_master tm
    JOIN textbook_toc toc ON toc.id = tm.toc_id
    WHERE tm.toc_id >= 1011
    GROUP BY toc.id, toc.title, toc.number
    ORDER BY toc.id
''')
paras = [dict(r) for r in cur.fetchall()]

# 3. Para 31 = toc_id 1054
cur.execute('''
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN distractor_meta IS NOT NULL AND jsonb_array_length(distractor_meta) >= 3 THEN 1 ELSE 0 END) as distractors_ok,
        SUM(CASE WHEN tags->>'quarantine_v3_needs_review' = 'true' THEN 1 ELSE 0 END) as in_review,
        SUM(CASE WHEN question_text ILIKE '%не дано%' OR question_text ILIKE '%не указано%' THEN 1 ELSE 0 END) as ocr_garbage,
        SUM(CASE WHEN tags->>'quarantine_v3_sympy_proven' = 'true' THEN 1 ELSE 0 END) as sympy_proven,
        SUM(CASE WHEN tags->>'quarantine_v3_verified' = 'true' THEN 1 ELSE 0 END) as verified,
        MAX(updated_at) as last_update
    FROM tasks_master
    WHERE toc_id = 1054
''')
para31 = dict(cur.fetchone())

# 4. distractor quality by answer_type
cur.execute('''
    SELECT 
        answer_type,
        COUNT(*) as total,
        SUM(CASE WHEN distractor_meta IS NOT NULL AND jsonb_array_length(distractor_meta) >= 3 THEN 1 ELSE 0 END) as distractors_ok,
        SUM(CASE WHEN distractor_meta IS NULL OR jsonb_array_length(distractor_meta) = 0 THEN 1 ELSE 0 END) as no_distractors
    FROM tasks_master WHERE toc_id >= 1011
    GROUP BY answer_type ORDER BY total DESC
''')
by_type = [dict(r) for r in cur.fetchall()]

# 5. Skills
cur.execute('''
    SELECT 
        COUNT(*) as total_tasks,
        SUM(CASE WHEN tm.tags->'skill_ids' IS NOT NULL THEN 1 ELSE 0 END) as has_skill_ids,
        COUNT(DISTINCT toc.mapped_skill_id) FILTER (WHERE toc.mapped_skill_id IS NOT NULL) as toc_skill_mappings
    FROM tasks_master tm
    JOIN textbook_toc toc ON toc.id = tm.toc_id
    WHERE tm.toc_id >= 1011
''')
skills_data = dict(cur.fetchone())

result = {
    'summary': summary,
    'paras': paras,
    'para31': para31,
    'by_type': by_type,
    'skills': skills_data
}
with open('/app/data/full_audit2.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2, default=str)
print('Done')
