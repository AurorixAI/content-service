import json, random, psycopg2
C = json.load(open("/audit/class_scan.json")); random.seed(3)
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
for k in ("mixed_as_division", "letter_key", "split_decimal_in_question"):
    print("=====", k)
    for tid in random.sample(C[k], 8):
        c.execute("SELECT left(question_latex,170), left(correct_answer,60) FROM tasks_master WHERE id=%s", (tid,))
        q, a = c.fetchone(); print(" ", tid, "|", " ".join(q.split()), "|| K:", a)
