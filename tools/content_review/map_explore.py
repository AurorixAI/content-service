import psycopg2
from collections import Counter
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
q = lambda s, *a: (c.execute(s, a), c.fetchall())[1]
print("active tasks:", q("SELECT count(*), count(skill_id), count(toc_id) FROM tasks_master WHERE is_active"))
print("skill level of task skills:", q("SELECT k.level, count(*) FROM tasks_master t JOIN knowledge_hierarchy k ON k.id=t.skill_id WHERE t.is_active GROUP BY 1"))
print("skill inactive:", q("SELECT count(*) FROM tasks_master t JOIN knowledge_hierarchy k ON k.id=t.skill_id WHERE t.is_active AND NOT k.is_active"))
print("skill missing:", q("SELECT count(*) FROM tasks_master t LEFT JOIN knowledge_hierarchy k ON k.id=t.skill_id WHERE t.is_active AND t.skill_id IS NOT NULL AND k.id IS NULL"))
print("textbook_skill_map rows:", q("SELECT count(*), count(DISTINCT toc_id), count(DISTINCT skill_id), string_agg(DISTINCT role, ',') FROM textbook_skill_map"))
# grade mismatch: task prefix grade vs skill grade
rows = q("SELECT t.id, t.skill_id, k.class_level_start, k.class_level_end FROM tasks_master t JOIN knowledge_hierarchy k ON k.id=t.skill_id WHERE t.is_active")
import re
mm = Counter()
for t, s, a, b in rows:
    m = re.match(r"(?:G|DIFF_G|GEN_G)(\d+)", t); sg = re.match(r"G(\d+)", s or "")
    if m and sg and int(m.group(1)) != int(sg.group(1)): mm[(int(m.group(1)), int(sg.group(1)))] += 1
print("task grade != skill grade:", sum(mm.values()), mm.most_common(12))
# toc consistency: task.toc_id -> skills mapped to that toc
rows = q("""SELECT t.id, t.skill_id, t.toc_id, array_agg(m.skill_id) FROM tasks_master t JOIN textbook_skill_map m ON m.toc_id=t.toc_id
           WHERE t.is_active GROUP BY t.id, t.skill_id, t.toc_id""")
inmap = sum(1 for r in rows if r[1] in r[3]); print("tasks with toc mapped:", len(rows), "skill ∈ toc skills:", inmap)
