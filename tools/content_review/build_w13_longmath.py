"""Build manifest n01-2026-10-07-w13: prose written inside \\text{...} of a formula (cannot wrap on a phone).

Reads the local DB only; never writes to it. Usage (from content-service):
  CONTENT_REPAIR_DATABASE_URL=... [W13_SCRATCH=dir] python3 -m tools.content_review.build_w13_longmath

Why data and not frontend: KaTeX keeps a \\text{...} block (and its spaces) on one line, so «$\\text{Сумма и разность —
нечётные. ...}$» is a 60-character unbreakable word: it overflows a 320 px screen (up to 13x the width) and no scaling
helps. Long lists, systems, products and wide fractions are handled in algo-front (math-renderer.tsx: break
opportunities after top-level commas, \\quad, factor groups, long digit runs; math-fit.ts: <=15 % scale-down), so
they are NOT touched here. Rows whose choices fail guarded_repair.validate_choices (GEN_G5_S22_03_04,
ds_llm_3b114b8dde4b: dict options / unexplained distractors) cannot be repaired by this tool and are left as is.

Class «prose» (display columns only: question_latex/question_text, correct_answer_latex, answer_options_latex;
distractor_meta.value_latex is not touched: old rows break guarded_repair's mirror rule):
  a single-dollar span whose \\text{...} blocks hold >= 20 Cyrillic letters and that contains no other Cyrillic, no
  environment and no other command except spacing becomes ordinary text: the \\text{} blocks are unwrapped and each
  remaining non-text run (a number, «(0;0)») becomes its own short span; trailing «.,;:» of a run stay plain.
  «$\\text{книга } 5000 \\text{ сумов}$» -> «книга $5000$ сумов».
The raw graded columns (correct_answer, answer_options) are NEVER changed (answers are compared as strings by
exam-service/answer_check.py); the pair rule of guarded_repair is met by repeating the unchanged raw value.
Every changed string: visible text identical (canon diff), $ parity, braces, KaTeX (no new errors).
"""
from __future__ import annotations

import collections
import json
import os
import re
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, text

from tools.content_review import guarded_repair as gr
from tools.content_review.build_w10_readability import MATH, braces_ok, canon, katex_errors

BATCH = "n01-source-repair-2026-10-07-w13"
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/content_repairs/n01-2026-10-07-w13.json"

TEXT = re.compile(r"\\text\{([^{}]*)\}")
CYR = re.compile(r"[А-Яа-яЁё]")
MIN_CYR = 20


def convert_span(span: str) -> str | None:
    """'$\\text{...}...$' -> plain text with short math spans, or None when the span is not prose-in-math."""
    if not span.startswith("$") or span.startswith("$$"):
        return None
    body = span[1:-1]
    if "\\begin" in body or "\\\\" in body or "\n" in body:
        return None
    blocks = TEXT.findall(body)
    if sum(len(CYR.findall(b)) for b in blocks) < MIN_CYR:
        return None
    rest = TEXT.sub("\x00", body)
    if CYR.search(rest) or "\\" in "".join(blocks) or "$" in body:
        return None
    out = []
    for piece in re.split(r"(\x00)", rest):
        if piece == "\x00":
            out.append(blocks.pop(0))
            continue
        run = piece.strip()
        if not run:
            continue
        if re.search(r"\\(?!,)", run):          # any command other than a thin space: not a simple run
            return None
        lead = re.match(r"^[.,;:!?]+", run)
        if lead:
            out.append(lead.group(0))
            run = run[lead.end():].strip()
        tail = re.search(r"[.,;:!?]+$", run)
        punct = ""
        if tail and not re.search(r"\d[.,]$", run) or (tail and tail.group(0) in ".;:!?"):
            punct = tail.group(0)
            run = run[:tail.start()].strip()
        if run:
            out.append("$" + run + "$")
        out.append(punct)
    return "".join(out)


def convert(t: str) -> str:
    if not t or "\\text" not in t:
        return t
    pos, res = 0, []
    for m in MATH.finditer(t):
        c = convert_span(m.group(0))
        if c is not None:
            res.append(t[pos:m.start()])
            res.append(c)
            pos = m.end()
    res.append(t[pos:])
    return "".join(res)


def visible(t: str) -> str:
    return canon(t)


def entry(row: dict, changes: dict, reason: str, evidence: str) -> dict:
    # guarded_repair needs raw+display together; the raw graded value is repeated unchanged.
    if "question_latex" in changes or "question_text" in changes:
        changes = {**changes, "question_text": changes.get("question_text", row["question_text"]),
                   "question_latex": changes.get("question_latex", row["question_latex"])}
    if "correct_answer_latex" in changes:
        changes = {**changes, "correct_answer": row["correct_answer"]}
    if "answer_options_latex" in changes:
        changes = {**changes, "answer_options": row["answer_options"]}
    e = {"id": row["id"], "before_sha256": gr.fingerprint(row), "reason": reason, "evidence": evidence,
         "changes": changes}
    gr.validate_entry(e)
    e["after_sha256"] = gr.fingerprint(gr.candidate(row, e, BATCH))
    return e


REASON = ("проза («Сумма и разность — нечётные…») записана внутри \\text{} формулы: KaTeX держит такой блок "
          "на одной строке, он в разы шире экрана 320 px; текст выведен из формулы, числа остались формулами")
EVIDENCE = ("Видимый текст не меняется (сравнение канонизированных строк до/после), меняются только отображаемые "
            "столбцы (…_latex); сырые столбцы correct_answer/answer_options, проверяемые как строки в "
            "exam-service/answer_check.py, не тронуты; ключ, варианты и дистракторы не менялись; "
            "проверка KaTeX без новых ошибок.")


def main() -> None:
    engine = create_engine(os.environ["CONTENT_REPAIR_DATABASE_URL"])
    scratch = Path(os.environ.get("W13_SCRATCH") or tempfile.mkdtemp())
    with engine.connect() as conn:
        ids = [r[0] for r in conn.execute(text("SELECT id FROM tasks_master WHERE is_active ORDER BY id"))]
        rows = {}
        for i in range(0, len(ids), 1000):
            rows.update({r["id"]: r for r in gr._load(conn, ids[i:i + 1000], False)})
    plans: dict[str, dict] = {}
    for tid in ids:
        row = rows[tid]
        ch = {}
        for col in ("question_text", "question_latex", "correct_answer_latex"):
            v = row[col] or ""
            n = convert(v)
            if n != v:
                ch[col] = n
        opts = row["answer_options_latex"]
        if isinstance(opts, list) and all(isinstance(o, str) for o in opts):
            n = [convert(o) for o in opts]
            if n != opts:
                ch["answer_options_latex"] = n
        if ch:
            plans[tid] = ch
    before_s, after_s = {}, {}
    for tid, ch in plans.items():
        for col, v in ch.items():
            old = rows[tid][col]
            olds = old if isinstance(old, list) else [old or ""]
            news = v if isinstance(v, list) else [v]
            for a, b in zip(olds, news):
                if a != b:
                    if b.count("$") % 2 or not braces_ok(b) or visible(a) != visible(b):
                        raise SystemExit(f"visible text changed {tid} {col}: {a[:60]!r} -> {b[:60]!r}")
        before_s[tid] = [s for col, v in ch.items() for s in
                         (rows[tid][col] if isinstance(rows[tid][col], list) else [rows[tid][col] or ""])
                         if isinstance(s, str)]
        after_s[tid] = [s for col, v in ch.items() for s in (v if isinstance(v, list) else [v]) if isinstance(s, str)]
    bad = katex_errors(after_s, scratch) - katex_errors(before_s, scratch)
    if bad:
        raise SystemExit(f"new KaTeX errors: {sorted(bad)[:5]}")
    repairs, stats, refused = [], collections.Counter(), {}
    for tid in sorted(plans):
        e = entry(rows[tid], plans[tid], REASON, EVIDENCE)
        try:  # guarded_repair re-validates choices of every row that repeats a raw column; old rows may not pass
            gr.validate_choices(gr.candidate(rows[tid], e, BATCH))
        except ValueError as exc:
            refused[tid] = str(exc)
            continue
        repairs.append(e)
        stats.update(plans[tid].keys())
    if refused:
        print("not repairable by guarded_repair (left as is):", refused)
    manifest = {"batch": BATCH, "mode": "in_place_owner_requested", "source_checked_at": "2026-10-07T00:00:00Z",
                "student_data_included": False, "repairs": repairs}
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(OUT)
    print("entries:", len(repairs), dict(stats))


if __name__ == "__main__":
    main()
