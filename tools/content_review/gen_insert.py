# Usage: gen_insert.py <name> [--execute]   — verify and insert new generated tasks from gen_<name>.py (list G)
import sys, json, re, importlib.util, psycopg2
from sympy import simplify, sympify
name = sys.argv[1]; EXE = "--execute" in sys.argv
spec = importlib.util.spec_from_file_location("g", f"/audit/gen_{name}.py"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
IRT = {"A": -1.0, "B": 0.5, "C": 1.5}
nrm = lambda s: re.sub(r"[\s$]|\\,", "", str(s)).replace("\\dfrac", "\\frac").replace("{,}", ",").lower()
conn = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content"); c = conn.cursor()
c.execute("SELECT id, question_latex FROM tasks_master WHERE is_active"); bankq = {nrm(q): t for t, q in c.fetchall()}
c.execute("SELECT id FROM knowledge_hierarchy WHERE is_active"); skills = {r[0] for r in c.fetchall()}
errs, rows, used = [], [], {}
for i, t in enumerate(m.G):
    tag = f"#{i} {t['skill']}"
    try: ok = bool(t["check"]())
    except Exception as e: ok = False; errs.append(f"{tag}: check raised {e}")
    if ok is not True: errs.append(f"{tag}: KEY CHECK FAILED")
    if t["skill"] not in skills: errs.append(f"{tag}: unknown skill")
    vals = [nrm(t["k"])] + [nrm(d) for d, _ in t["ds"]]
    if len(set(vals)) != len(vals): errs.append(f"{tag}: option strings not distinct")
    if t.get("vals"):
        v = t["vals"]
        for j in range(1, len(v)):
            if simplify(sympify(v[j]) - sympify(v[0])) == 0: errs.append(f"{tag}: distractor {j} equals key in value")
    if len(t["ds"]) < (1 if t["k"] in ("да", "нет") else 2): errs.append(f"{tag}: too few distractors")
    if nrm(t["q"]) in bankq: errs.append(f"{tag}: same statement already in bank ({bankq[nrm(t['q'])]})")
    for d, e in t["ds"]:
        if not e.startswith("Ученик"): errs.append(f"{tag}: explanation style")
    # id
    key = (t["skill"], t["diff"]); used[key] = used.get(key, 0)
    while True:
        used[key] += 1; tid = f"GEN_{t['skill']}_{t['diff']}_{used[key]:02d}"
        c.execute("SELECT 1 FROM tasks_master WHERE id=%s", (tid,))
        if not c.fetchone(): break
    dm = [{"value": d, "value_latex": d, "error_type": "manual_generated", "plausibility": 0.7, "error_logic": e, "error_logic_latex": e, "explanation": e, "explanation_latex": e} for d, e in t["ds"]]
    opts = [t["k"]] + [d for d, _ in t["ds"]]
    tags = {"generated_by": "claude-manual-2026-09-26", "batch": f"gen-{name}", "answer_locked": True, "choices_complete": True, "verified_by": "sympy-check+manual", "reason": "навык имел < 3 подходящих задач"}
    rows.append((tid, t["skill"], t["q"], t["q"], t["atype"], t["k"], t["k"], json.dumps(opts, ensure_ascii=False), json.dumps(opts, ensure_ascii=False),
                 t["diff"], IRT[t["diff"]], json.dumps(dm, ensure_ascii=False), json.dumps(tags, ensure_ascii=False)))
print("tasks", len(m.G), "errors", len(errs)); [print("  ", e) for e in errs]
if errs: sys.exit(1)
for r in rows:
    c.execute("""INSERT INTO tasks_master (id, skill_id, question_text, question_latex, answer_type, correct_answer, correct_answer_latex, answer_options, answer_options_latex,
                 difficulty, irt_discrimination, irt_difficulty, irt_guessing, distractor_meta, is_active, cognitive_load, verification_status, source_type, tags, is_star, task_category)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,1.0,%s,0.0,%s::jsonb,TRUE,'apply','verified','ai_generated',%s::jsonb,FALSE,'standard')""", r)
print("inserted" if EXE else "[DRY RUN] would insert", len(rows), ":", ", ".join(r[0] for r in rows[:6]), "…")
conn.commit() if EXE else conn.rollback()
