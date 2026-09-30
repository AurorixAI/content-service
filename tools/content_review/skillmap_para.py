import psycopg2, re
from collections import Counter, defaultdict
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, name_ru FROM knowledge_hierarchy"); NM = dict(c.fetchall())
c.execute("""SELECT t.id, t.skill_id, split_part(t.source_reference,'::',1), split_part(split_part(t.source_reference,'::',2),':',1), t.toc_id
             FROM tasks_master t WHERE t.is_active AND t.skill_id IS NOT NULL AND t.source_reference IS NOT NULL""")
P = defaultdict(Counter)
for tid, sk, b, para, toc in c.fetchall(): P[(b[:8], para)][sk] += 1
print("paragraph groups:", len(P), "distinct (paragraph, skill) pairs:", sum(len(v) for v in P.values()))
single = [(k, v) for k, v in P.items() if sum(v.values()) >= 8]
print("paragraphs with ≥8 tasks:", len(single), "| where one skill has ≥80% of tasks:", sum(1 for k, v in single if v.most_common(1)[0][1] / sum(v.values()) >= .8))
for key in [("b8f4a2c1", "50"), ("e92457e0", "§ 42"), ("0fd78e9c", "§ 42"), ("2aa7af81", "20")]:
    if key in P: print(key, [(s, n, NM.get(s, "")[:40]) for s, n in P[key].most_common(5)])
# where did the sampled wrong ones come from
for t in ["G8_TB_50_1222.4.2", "G10_TB_§42_42_19_4", "G10_TB_§37_37_3_2", "G6_TB_7_285"]:
    c.execute("SELECT source_reference, skill_id FROM tasks_master WHERE id=%s", (t,)); s, sk = c.fetchone()
    b, para = s.split("::")[0][:8], s.split("::")[1].split(":")[0]
    v = P[(b, para)]; print(t, "|", s, "| paragraph skills:", [(x, n, NM.get(x, "")[:35]) for x, n in v.most_common(4)], "total", sum(v.values()))
