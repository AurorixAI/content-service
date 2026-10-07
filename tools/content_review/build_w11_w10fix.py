"""Build manifest n01-2026-10-07-w11: corrective repairs for regressions found by the independent check of wave 10.

Reads the local DB only; never writes to it. Usage (from content-service):
  CONTENT_REPAIR_DATABASE_URL=... python3 -m tools.content_review.build_w11_w10fix

Fixes:
  restore  GEN_G6_S47_03_B_03 question_latex: wave 10 removed «00)» of «время 12:00)» as if it were a label
           (the label regex in build_w10_readability.py is fixed too: «NN)» right after «digits:» is a time).
           The «00)» is restored; question_text of the same task was already correct.
  unitspan «$18$ $\\text{м}^{2}$» (number and unit in two spans separated by a space; the line may wrap between
           them, and the legacy text renderer drops the space: «18м2») -> one span «$18\\,\\text{м}^{2}$».
           Applied to question_text and question_latex of every active task, any «$<quantity>$ $\\text{<unit>}^{k}$».
Every changed string is verified: canon diff (only «\\,» and the space between the spans), $ parity, braces,
KaTeX (node tools/content_review/katex_check.js, no new errors).
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

BATCH = "n01-source-repair-2026-10-07-w11"
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/content_repairs/n01-2026-10-07-w11.json"

RESTORE_ID = "GEN_G6_S47_03_B_03"
RESTORE_OLD = "принято время 12: отмечена точка"
RESTORE_NEW = "принято время 12:00) отмечена точка"

UNIT_SPAN = re.compile(r"^\$\\text\{[^{}]*\}\^\{?\d+\}?\$$")
GAP = re.compile(r"^[ \t ]+$")


def restore(latex: str) -> str:
    assert latex.count(RESTORE_OLD) == 1, "unexpected current text"
    return latex.replace(RESTORE_OLD, RESTORE_NEW)


def unit_span(t: str) -> str:
    """'$18$ $\\text{м}^{2}$' -> '$18\\,\\text{м}^{2}$' (first span: a quantity, i.e. no text, ends with a digit/letter/})."""
    spans = list(MATH.finditer(t))
    out, pos, i = [], 0, 0
    while i < len(spans) - 1:
        a, b = spans[i], spans[i + 1]
        body = a.group(0)[1:-1].rstrip()
        if (not a.group(0).startswith("$$") and UNIT_SPAN.match(b.group(0)) and GAP.match(t[a.end():b.start()])
                and body and (body[-1].isalnum() or body[-1] == "}") and "\\text" not in body
                and not re.search(r"[А-Яа-яЁё]", body) and a.start() >= pos):
            out.append(t[pos:a.start()])
            out.append("$" + body + "\\," + b.group(0)[1:])
            pos = b.end()
            i += 2
        else:
            i += 1
    out.append(t[pos:])
    return "".join(out)


def entry(row: dict, changes: dict, reason: str, evidence: str) -> dict:
    changes = {**changes, "question_text": changes.get("question_text", row["question_text"]),
               "question_latex": changes.get("question_latex", row["question_latex"])}
    e = {"id": row["id"], "before_sha256": gr.fingerprint(row), "reason": reason, "evidence": evidence,
         "changes": changes}
    gr.validate_entry(e)
    e["after_sha256"] = gr.fingerprint(gr.candidate(row, e, BATCH))
    return e


R_RESTORE = ("восстановлена потерянная волной 10 часть условия «12:00)»: «00)» после двоеточия принято за метку "
             "подпункта и удалено, скобка «(в минутах, где за $0$ принято время 12:00)» осталась открытой")
E_RESTORE = ("Текст до волны 10 (резервная копия n01-w10-local.json) и question_text этой же задачи содержат "
             "«время $12$:$00)$ отмечена точка»; восстановлено ровно «12:00)». Остальное условие, ключ, варианты "
             "и дистракторы не менялись; проверка KaTeX без ошибок.")
R_UNIT = ("число и единица измерения в степени записаны одной формулой через тонкий пробел "
          "($18$ $\\text{м}^{2}$ -> $18\\,\\text{м}^{2}$): между ними нет разрыва строки, "
          "а устаревший текстовый рендер не склеивает их в «18м2»")
E_UNIT = ("Нормализация записи условия без изменения смысла: видимый текст не меняется, кроме пробела между числом "
          "и единицей (он заменён тонким пробелом внутри формулы); одинаковая функция применена к question_text и "
          "question_latex; ключ, варианты и дистракторы не менялись; проверка KaTeX без новых ошибок.")


def main() -> None:
    engine = create_engine(os.environ["CONTENT_REPAIR_DATABASE_URL"])
    scratch = Path(tempfile.mkdtemp())
    with engine.connect() as conn:
        ids = [r[0] for r in conn.execute(text("SELECT id FROM tasks_master WHERE is_active ORDER BY id"))]
        rows = {}
        for i in range(0, len(ids), 1000):
            rows.update({r["id"]: r for r in gr._load(conn, ids[i:i + 1000], False)})
    plans, classes = {}, {}
    for tid in ids:
        row = rows[tid]
        new = {c: row[c] or "" for c in ("question_text", "question_latex")}
        cl = set()
        if tid == RESTORE_ID:
            new["question_latex"] = restore(new["question_latex"])
            cl.add("restore")
        for c in new:
            u = unit_span(new[c])
            if u != new[c]:
                new[c] = u
                cl.add("unitspan")
        changes = {c: v for c, v in new.items() if v != (row[c] or "")}
        if not changes:
            continue
        for c, v in changes.items():
            if v.count("$") % 2 or not braces_ok(v):
                raise SystemExit(f"invalid {tid} {c}")
            if cl == {"unitspan"} and canon(v) != canon(row[c]):
                raise SystemExit(f"canon changed {tid} {c}")
        plans[tid], classes[tid] = changes, cl
    before_s = {t: [rows[t][c] or "" for c in ch] for t, ch in plans.items()}
    after_s = {t: list(ch.values()) for t, ch in plans.items()}
    bad = katex_errors(after_s, scratch) - katex_errors(before_s, scratch)
    if bad:
        raise SystemExit(f"new KaTeX errors: {sorted(bad)[:5]}")
    repairs, stats = [], collections.Counter()
    for tid in sorted(plans):
        cl = classes[tid]
        reasons = [r for k, r in (("restore", R_RESTORE), ("unitspan", R_UNIT)) if k in cl]
        evid = [e for k, e in (("restore", E_RESTORE), ("unitspan", E_UNIT)) if k in cl]
        repairs.append(entry(rows[tid], plans[tid], "; ".join(reasons), " ".join(evid)))
        stats.update(cl)
        for c in plans[tid]:
            stats[c] += 1
    manifest = {"batch": BATCH, "mode": "in_place_owner_requested", "source_checked_at": "2026-10-07T00:00:00Z",
                "student_data_included": False, "repairs": repairs}
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(OUT)
    print("entries:", len(repairs), dict(stats))


if __name__ == "__main__":
    main()
