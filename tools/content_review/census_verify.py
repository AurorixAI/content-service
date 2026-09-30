import psycopg2, collections
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("""SELECT id, answer_type, tags->'verify_unresolved', tags ? 'answer_previous',
   EXISTS (SELECT 1 FROM jsonb_object_keys(tags) k WHERE k LIKE 'content_repair::%') AS repaired
   FROM tasks_master WHERE is_active AND (tags ? 'verify_unresolved' OR tags ? 'answer_previous')""")
rows = c.fetchall()
U = [r for r in rows if r[2] is not None and r[2] != 'false' and r[2] is not False]
print("verify_unresolved tagged:", len([r for r in rows if r[2] is not None]), "| value sample:", collections.Counter(str(r[2])[:30] for r in rows if r[2] is not None).most_common(5))
unres = [r for r in rows if r[2] not in (None, False)]
print("  unresolved (truthy):", len(unres), "| of them touched by our manual batches:", sum(r[4] for r in unres))
print("  by type:", collections.Counter(r[1] for r in unres).most_common(8))
ap = [r for r in rows if r[3]]
print("answer_previous (key replaced by smart_verify):", len(ap), "| touched by our manual batches:", sum(r[4] for r in ap))
print("  by type:", collections.Counter(r[1] for r in ap).most_common(8))
print("  by source:", collections.Counter(('gen' if r[0].startswith(('ds_llm','DIFF','GEN')) else 'book') for r in ap))
