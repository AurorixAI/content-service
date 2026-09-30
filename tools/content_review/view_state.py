import json, sys, types, re
rows = json.load(open("/audit/nested_after_state.json")); out = {}
if sys.argv[1] == "diag":
    from src.domain.task_display import build_diag_answer_options
    from src.domain.answer_evaluator import AnswerEvaluator
    ev = AnswerEvaluator()
    for t in rows:
        ns = types.SimpleNamespace(**t, sympy_solution=None, tags={})
        o, ol = build_diag_answer_options(ns, seed="sim:" + t["id"])
        if not o: out[t["id"]] = None; continue
        corr = [i for i, x in enumerate(o) if ev.evaluate(ns, x)[0] == 1.0]
        out[t["id"]] = dict(n=len(o), corr=corr, disp=list(ol or o), vals=o)
else:
    from src.api.router import _mc_choices
    for t in rows:
        t["task_id"] = t["id"]
        from src.api.router import _check_answer
        pairs = _mc_choices(t)
        out[t["id"]] = dict(n=len(pairs), corr=[i for i, (v, _) in enumerate(pairs) if _check_answer(v, t["correct_answer"])], disp=[d for _, d in pairs], vals=[v for v, _ in pairs])
json.dump(out, open(f"/audit/view_{sys.argv[1]}.json", "w"), ensure_ascii=False, indent=1)
print(sys.argv[1], len(out))
