import json, types, psycopg2
from src.domain.task_display import build_diag_answer_options
c = psycopg2.connect('postgresql://algo:algo_password@algo-content-db:5432/algo_content').cursor()
c.execute('SELECT id, answer_type, correct_answer, answer_options, answer_options_latex, distractor_meta, correct_answer_latex, question_text FROM tasks_master WHERE is_active')
for tid, at, ca, o, ol, dm, cal, qt in c.fetchall():
    t = types.SimpleNamespace(id=tid, answer_type=at, correct_answer=ca, answer_options=o or [], answer_options_latex=ol or [], distractor_meta=dm or [], correct_answer_latex=cal, question_text=qt, sympy_solution=None, tags={})
    if not build_diag_answer_options(t, seed='bank:' + tid)[0]: print(tid, at, len(dm or []))
