import re, psycopg2, collections
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='tasks_master'")
cols=[r[0] for r in c.fetchall()]; print([x for x in cols if re.search('image|figure|pic|media|asset|svg', x)])
c.execute(r"SELECT id, correct_answer FROM tasks_master WHERE is_active AND correct_answer ~ '^\s*(Доказано|Доказательство)\.?\s*$'"); print("bare proof:", c.fetchall())
c.execute("SELECT id, answer_type, left(question_latex,120), left(correct_answer,60) FROM tasks_master WHERE is_active AND COALESCE(jsonb_array_length(CASE WHEN jsonb_typeof(distractor_meta)='array' THEN distractor_meta END),0)=0"); print("no distractors:", c.fetchall())
imgcol = [x for x in cols if re.search('image|figure', x)]
if imgcol:
    col = imgcol[0]
    c.execute(f"SELECT count(*), count(*) FILTER (WHERE {col} IS NOT NULL AND {col}::text NOT IN ('null','[]','{{}}','')) FROM tasks_master WHERE is_active AND question_latex ~* '(рис\\.|рисун)'"); print("figure tasks / with image:", c.fetchone())
c.execute("SELECT count(*) FROM tasks_master WHERE is_active AND question_latex ~* '(рис\\.|рисун)'"); print("figure refs:", c.fetchone())
c.execute("SELECT id, left(question_latex,110) FROM tasks_master WHERE is_active AND question_latex ~* '(рис\\.|рисун)' LIMIT 6"); [print('  ',r) for r in c.fetchall()]
c.execute("SELECT answer_type, count(*) FROM tasks_master WHERE is_active GROUP BY 1 ORDER BY 2 DESC"); print(c.fetchall())
c.execute("SELECT key, count(*) FROM tasks_master, jsonb_object_keys(COALESCE(tags,'{}'::jsonb)) key WHERE is_active AND (key ILIKE '%verif%' OR key ILIKE '%checked%' OR key ILIKE 'answer_previous%') GROUP BY 1 ORDER BY 2 DESC LIMIT 15"); print(c.fetchall())
