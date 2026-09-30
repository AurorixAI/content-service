import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
for t in ["tasks_master", "task_figure_refs", "task_figures", "textbook_tasks", "textbook_skill_map", "knowledge_hierarchy", "skill_prerequisites"]:
    c.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name=%s ORDER BY ordinal_position", (t,))
    print(t, [r[0] for r in c.fetchall()])
