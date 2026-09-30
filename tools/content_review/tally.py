import psycopg2, collections, re
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT count(*) FILTER (WHERE is_active), count(*) FILTER (WHERE NOT is_active), count(*) FROM tasks_master"); print("active/inactive/total", c.fetchone())
c.execute("""SELECT id, is_active, (SELECT array_agg(k) FROM jsonb_object_keys(COALESCE(tags,'{}'::jsonb)) k WHERE k LIKE 'content_repair::%'),
                    tags->>'deactivation_batch', tags->>'deactivated_by' FROM tasks_master""")
rows = c.fetchall()
touched = [r for r in rows if r[2]]
print("tasks with any repair tag:", len(touched), "| of them active:", sum(r[1] for r in touched))
def cat(b):
    b = b.split("::",1)[1]
    for pat, name in [("latex-l6b","LaTeX: десятичная запятая (L6b)"),("latex-l6g","LaTeX: tg/ctg, запятые (L6g)"),("latex-l6h","LaTeX: спорные запятые (L6h)"),
                      ("latex-l6e","LaTeX: символы (L6e)"),("latex","LaTeX: прочее (L1–L6f)"),("proof","Доказательства (шаг 7)"),("display","Отображение условий (шаг 5)"),
                      ("dups|dup-","Дубли"),("opt-|knio","Ключ и варианты"),("dm-|dmC|l6c|l6d","Дистракторы"),("ineq|trigineq","Неравенства"),("eq|trig","Уравнения / тригонометрия"),
                      ("arith|batchI|batch-i|calc|vilenkin","Арифметика / калькулятор"),("sample","Выборочная проверка 25.09"),("2026-09-23","Пакеты 23.09 (LaTeX-сбои, ключи SymPy, float)"),]:
        if re.search(pat, b): return name
    return "Прочее"
per = collections.Counter(); first = collections.Counter()
for r in touched:
    cats = {cat(b) for b in r[2]}
    for k in cats: per[k] += 1
print("\nЗадач по видам работ (задача может входить в несколько):")
for k, v in per.most_common(): print(f"  {v:6d}  {k}")
d = [r for r in rows if r[4] == 'claude-manual-review' or (r[3] or '').startswith('manual-review')]
print("\nОтключено мной обратимо:", len(d), "| сейчас неактивны:", sum(not r[1] for r in d))
c.execute("SELECT count(*) FROM tasks_master WHERE NOT is_active AND tags ? 'deactivated_reason'"); print("всего неактивных с причиной:", c.fetchone()[0])
c.execute("""SELECT count(DISTINCT id) FROM tasks_master, jsonb_object_keys(COALESCE(tags,'{}'::jsonb)) k
             WHERE k LIKE 'content_repair::%' AND (tags->k->'previous' ? 'correct_answer')"""); print("задач, где менялся ключ (correct_answer):", c.fetchone()[0])
c.execute("""SELECT count(DISTINCT id) FROM tasks_master, jsonb_object_keys(COALESCE(tags,'{}'::jsonb)) k
             WHERE k LIKE 'content_repair::%' AND (tags->k->'previous' ? 'question_text' OR tags->k->'previous' ? 'question_latex')"""); print("задач, где менялось условие:", c.fetchone()[0])
