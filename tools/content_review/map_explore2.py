import psycopg2
from collections import Counter
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
q = lambda s, *a: (c.execute(s, a), c.fetchall())[1]
print("toc rows:", q("SELECT count(*), count(mapped_skill_id), count(mapped_topic_id) FROM textbook_toc"))
print("sample:", q("SELECT id, level, number, title, mapped_skill_id, mapped_topic_id, mapping_confidence FROM textbook_toc WHERE mapped_skill_id IS NOT NULL LIMIT 3"))
print("mapped_skill level:", q("SELECT k.level, count(*) FROM textbook_toc tc JOIN knowledge_hierarchy k ON k.id=tc.mapped_skill_id GROUP BY 1"))
print("mapped_topic level:", q("SELECT k.level, count(*) FROM textbook_toc tc JOIN knowledge_hierarchy k ON k.id=tc.mapped_topic_id GROUP BY 1"))
# task skill vs toc mapped skill/topic: is task skill a descendant of toc topic?
rows = q("""SELECT t.id, t.skill_id, k.parent_id, p.parent_id, tc.mapped_skill_id, tc.mapped_topic_id
            FROM tasks_master t JOIN textbook_toc tc ON tc.id=t.toc_id JOIN knowledge_hierarchy k ON k.id=t.skill_id LEFT JOIN knowledge_hierarchy p ON p.id=k.parent_id WHERE t.is_active""")
cnt = Counter()
for tid, s, par, gpar, ms, mt in rows:
    anc = {s, par, gpar}
    cnt["skill==toc.skill" if s == ms else ("toc.topic in ancestors" if mt in anc or ms in anc else ("toc unmapped" if not ms and not mt else "MISMATCH"))] += 1
print(cnt)
print("no-skill tasks by source:", q("SELECT split_part(id,'_',1)||'_'||split_part(id,'_',2), count(*) FROM tasks_master WHERE is_active AND skill_id IS NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 12"))
