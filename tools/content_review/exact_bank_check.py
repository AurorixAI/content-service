import json, re, types, psycopg2
from collections import Counter
from src.domain.task_display import build_diag_answer_options
from src.domain.answer_evaluator import AnswerEvaluator
safe = lambda s: re.sub(r'[\s$]', '', str(s or '')).replace('\\dfrac', '\\frac')
c = psycopg2.connect('postgresql://algo:algo_password@algo-content-db:5432/algo_content').cursor()
c.execute('SELECT id, answer_type, correct_answer, answer_options, answer_options_latex, distractor_meta, correct_answer_latex, question_text FROM tasks_master WHERE is_active')
ev = AnswerEvaluator(); st = Counter(); lists = {'twin': [], 'dup': [], 'none': [], 'multi': []}
for tid, at, ca, o, ol, dm, cal, qt in c.fetchall():
    t = types.SimpleNamespace(id=tid, answer_type=at, correct_answer=ca, answer_options=o or [], answer_options_latex=ol or [], distractor_meta=dm or [], correct_answer_latex=cal, question_text=qt, sympy_solution=None, tags={})
    opts, lat = build_diag_answer_options(t, seed='bank:' + tid)
    if not opts: st['open'] += 1; continue
    shown = [safe(l or v) for v, l in zip(opts, lat)]
    g = [ev.evaluate(t, str(v))[0] == 1.0 for v in opts]
    if sum(g) == 0: st['none'] += 1; lists['none'].append(tid)
    if sum(g) > 1: st['multi'] += 1; lists['multi'].append(tid)
    if len(set(shown)) != len(shown): st['dup'] += 1; lists['dup'].append(tid)
    if any((not x) and s == safe(cal or ca) for s, x in zip(shown, g)): st['twin'] += 1; lists['twin'].append(tid)
print(dict(st)); json.dump(lists, open('/audit/exact_bank_lists.json', 'w'), ensure_ascii=False)
