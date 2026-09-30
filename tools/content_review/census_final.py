# -*- coding: utf-8 -*-
"""Whole-bank census of open defect classes (2026-09-25, for the owner report)."""
import json, re, collections, psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT count(*) FILTER (WHERE is_active), count(*) FILTER (WHERE NOT is_active) FROM tasks_master")
act, inact = c.fetchone()
print("active", act, "inactive", inact)
c.execute("""SELECT id, source_reference, answer_type, question_text, question_latex, correct_answer, correct_answer_latex,
                    answer_options, answer_options_latex, distractor_meta, tags FROM tasks_master WHERE is_active""")
rows = c.fetchall()
C = collections.Counter()
GENERIC = re.compile(r"^Типичная ошибка ученика", re.I)
SQRT_FRAC = re.compile(r"\\sqrt\{\\d?frac\{(\d+)\}\{(\d+)\}\}")
src_kind = collections.Counter()
for tid, src, at, qt, ql, ca, cal, ao, aol, dm, tags in rows:
    tags = tags or {}
    kind = "textbook" if "_TB_" in tid or tid.startswith(("G5_", "G6_", "G7_", "G8_", "G9_", "G10_", "G11_")) else "generated"
    src_kind[kind] += 1
    ds = [d for d in (dm or []) if isinstance(d, dict)]
    mc = isinstance(ao, list) and len(ao) >= 2
    C["mc" if mc else "open"] += 1
    if len(ds) == 0: C["no_distractors"] += 1
    if len(ds) == 1: C["one_distractor"] += 1
    if len(ds) == 2: C["two_distractors"] += 1
    if any(GENERIC.search(str(d.get("error_logic") or "")) for d in ds): C["generic_error_logic"] += 1
    if any(len(str(d.get("error_logic") or "")) < 15 for d in ds): C["empty_error_logic"] += 1
    if any(str(d.get("error_type")) == "ai_generated" for d in ds): C["ai_generated_distractors"] += 1
    if not (cal or "").strip(): C["no_key_latex"] += 1
    if not (ql or "").strip(): C["no_question_latex"] += 1
    if re.fullmatch(r"\s*(Доказано|Доказательство)\.?\s*", ca or ""): C["key_proved_bare"] += 1
    blob = " ".join([ql or "", cal or ""] + [str(d.get("value_latex") or "") for d in ds])
    for m in SQRT_FRAC.finditer(blob):
        a, b = int(m.group(1)), int(m.group(2))
        if int(a ** .5) ** 2 != a or int(b ** .5) ** 2 != b:
            C["sqrt_of_fraction_nonsquare"] += 1; break
    if re.search(r"(?i)назовите (два|любые|несколько)|приведите пример", ql or ""): C["open_ended_example"] += 1
    if "latex_attested_fields" in tags and "question" not in (tags.get("latex_attested_fields") or []) and (ql or "") != (qt or ""): C["question_latex_unattested_differs"] += 1
    if re.search(r"рис\.|рисун", ql or "", re.I): C["refers_to_figure"] += 1
print("by source:", dict(src_kind))
for k, v in sorted(C.items()): print(f"  {k}: {v}")
