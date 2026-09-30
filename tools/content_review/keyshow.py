import sys, psycopg2, re
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
for t in sys.argv[1].split('|'):
    c.execute("SELECT regexp_replace(question_latex,'\\s+',' ','g'), correct_answer_latex FROM tasks_master WHERE id=%s",(t,))
    q,k=c.fetchone(); print(t,'|',q[:300],'|K:',k[:400])
