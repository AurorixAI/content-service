"""exact_bank_check logic applied to the w15 manifest (no DB): run inside the diagnostic-service image.
Expect {} : every task shows its options, exactly one is graded correct, none duplicates on screen."""
import json, re, types, sys
from collections import Counter
from src.domain.task_display import build_diag_answer_options
from src.domain.answer_evaluator import AnswerEvaluator
safe = lambda s: re.sub(r'[\s$]', '', str(s or '')).replace('\\dfrac', '\\frac')
rows = json.load(open(sys.argv[1]))['new_tasks']
ev = AnswerEvaluator(); st = Counter(); lists = {}
for r in rows:
    t = types.SimpleNamespace(id=r['id'], answer_type=r['answer_type'], correct_answer=r['correct_answer'], answer_options=r['answer_options'],
        answer_options_latex=r['answer_options_latex'], distractor_meta=r['distractor_meta'], correct_answer_latex=r['correct_answer_latex'],
        question_text=r['question_text'], sympy_solution=None, tags={})
    opts, lat = build_diag_answer_options(t, seed='bank:' + t.id)
    if not opts: st['open'] += 1; lists.setdefault('open', []).append(t.id); continue
    shown = [safe(l or v) for v, l in zip(opts, lat)]
    g = [ev.evaluate(t, str(v))[0] == 1.0 for v in opts]
    cats = [ev.evaluate(t, str(v))[1] for v in opts]
    if len(opts) != 4: st['not4'] += 1; lists.setdefault('not4', []).append(t.id)
    if sum(g) != 1: st['key_count'] += 1; lists.setdefault('key_count', []).append(t.id)
    if len(set(shown)) != len(shown): st['dup'] += 1; lists.setdefault('dup', []).append(t.id)
    if sorted(cats) != ['correct', 'distractor', 'distractor', 'distractor']: st['cats'] += 1; lists.setdefault('cats', []).append(t.id)
print(dict(st), json.dumps(lists)[:500], 'checked', len(rows))
