import json, sys, types
rows = json.load(open("/audit/nested_after_state.json")); bad = 0
if sys.argv[1] == "diag":
    from src.domain.task_display import build_diag_answer_options
    from src.domain.answer_evaluator import AnswerEvaluator
    ev = AnswerEvaluator()
    for t in rows:
        ns = types.SimpleNamespace(**t, sympy_solution=None, tags={})
        o, _ = build_diag_answer_options(ns, seed="sim:" + t["id"])
        if o and sum(ev.evaluate(ns, x)[0] == 1.0 for x in o) != 1: bad += 1; print("DIAG BAD", t["id"])
else:
    from src.api.router import _build_mc_options, _check_answer
    from src.domain.print_package import print_choice_options
    from src.domain.print_pdf import _is_key_option
    for t in rows:
        t["task_id"] = t["id"]; o = _build_mc_options(t, shuffle=True, seed="sim"); p = print_choice_options(t)
        if (o and sum(_check_answer(x, t["correct_answer"]) for x in o) != 1) or (p and sum(_is_key_option(x, t["correct_answer"], t["correct_answer_latex"] or "") for x in p) != 1):
            bad += 1; print("EXAM BAD", t["id"])
print(sys.argv[1], "checked", len(rows), "bad", bad)
