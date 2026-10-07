"""Build manifest n01-2026-10-07-w10: readability of task conditions + two known task errors.

Reads the local DB only; never writes to it. Usage (from content-service):
  CONTENT_REPAIR_DATABASE_URL=... [W10_SCRATCH=dir] python3 -m tools.content_review.build_w10_readability

Deterministic classes (applied to question_text AND question_latex independently with the same functions):
  label   a single sub-item label («b)», «а)», «1)», also «$b)$», «$b) expr$», «b.» in latex) right after the colon of a
          single-question task is removed (w8 handled only labels outside $...$ with identical form in both columns).
          Tasks with >=2 label candidates in a column are multi-part: left manual.
  hoist   enumeration label that got inside a math span («$1)26$», «$a) 1+x$») is moved out: «1) $26$». Only when the
          string has a surplus of «)» in its math (so a real closing parenthesis «$58)$» is never taken for a label).
  unit    unit glued to a superscript span («см$^{2}$», «м/с$^2$») -> «$\\text{см}^{2}$» (precedent: \\text{м}^{2} in bank).
  merge   one expression split into several math spans joined only by an operator («$26$ : $5{,}2$», «$x$ $+$ $5$»)
          -> one span «$26 : 5{,}2$».
  newline a line break inside an inline $...$ span (whitespace in math) -> single space.
  tail    a stray «;» or «,» at the very end of the condition is dropped.
Every changed string is verified: the visible text is unchanged except the intended normalization (canon diff),
$ parity and braces are balanced, KaTeX renders it (node tools/content_review/katex_check.js, no new errors).
Known errors: skill remap of the cube-surface-area tasks asking for the edge length.
"""
from __future__ import annotations

import collections
import json
import os
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, text

from tools.content_review import guarded_repair as gr

BATCH = "n01-source-repair-2026-10-07-w10"
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/content_repairs/n01-2026-10-07-w10.json"

MATH = re.compile(r"\$\$[\s\S]+?\$\$|\$[^$]+?\$")
LBL = r"(?:[а-яёА-ЯЁa-zA-Z]|\d{1,2})"
# «NN)» right after «digits:» is the end of a time («12:00)»), never a label (wave 11 fix, GEN_G6_S47_03_B_03)
PLAIN = re.compile(r"(?<![^\s:;,.])(?<!\d:)(" + LBL + r")\)(?=\s|$)")
SPAN_LABEL = re.compile(r"^\$\s*(" + LBL + r")\)\s*(.*?)\s*\$$", re.S)

SKILL_FIXES = {
    "G9_TB_10_130_2.1": "G8_S23_06",
    "G9_TB_10_130_2.2": "G8_S23_06",
}
SKILL_REASON = (
    "неверное отображение навыка: G9_S03_01 «Graph of y=ax^2 narrow» (построение графика y=ax^2, a>1) не соответствует "
    "задаче: графика нет, по заданной площади поверхности куба нужно найти ребро, то есть решить уравнение 6x^2=S")
SKILL_EVID = (
    "Площадь поверхности куба y=6x^2 (ключ задачи 1,29 см и 1,53 см сходится: sqrt(10/6)=1,29; sqrt(14/6)=1,53). "
    "Вопрос задачи: найти x по y, то есть решить неполное квадратное уравнение 6x^2=10 (приведение к виду x^2=c, "
    "отбор положительного корня). В банке это навык G8_S23_06 «Приведение к неполному квадратному» (активен, раздел "
    "G8_P23 «Неполные квадратные уравнения и их решение»; прецедент: G8_TB_42_1076.2, задача с физической формулой "
    "и выражением переменной, отнесена к G8_S23_06; описание навыка «Решите уравнение 3x² = 27»). Навыки G9_S03_* про "
    "построение графиков, G9_S05_05 про оптимизацию/максимум, не подходят.")


# ---------------------------------------------------------------- helpers
def mask(t: str) -> str:
    return MATH.sub(lambda m: "\x00" * len(m.group(0)), t)


def canon(s: str) -> str:
    s = re.sub(r"\\text\b|\\mathrm\b", "", s)
    for a, b in ((r"\cdot", "·"), (r"\times", "×"), (r"\leq", "≤"), (r"\le", "≤"), (r"\geq", "≥"),
                 (r"\ge", "≥"), ("−", "-"), ("–", "-"), (r"\ ", ""), (r"\,", "")):
        s = s.replace(a, b)
    s = re.sub(r"[\s${}\\]", "", s)
    return s.rstrip(";,")


def braces_ok(t: str) -> bool:
    for m in MATH.finditer(t):
        s = re.sub(r"\\[{}]", "", m.group(0))
        if s.count("{") != s.count("}"):
            return False
    return True


# ---------------------------------------------------------------- steps
def hoist(t: str) -> str:
    """'$1)26$' -> '1) $26$', '$b)$' -> 'b)'. A span is skipped when the text before it has an unclosed '('
    (then its ')' is a real closing parenthesis: '(координату $x)$', '(5626 : $58)$')."""
    spans = [m for m in MATH.finditer(t) if not m.group(0).startswith("$$")]
    labs = [m for m in spans if SPAN_LABEL.match(m.group(0))]
    if not labs:
        return t
    plain_masked = PLAIN.sub(lambda m: m.group(0)[:-1] + " ", t)     # '1) ' enumeration labels are not parentheses
    out, pos = [], 0
    for m in labs:
        before = plain_masked[:m.start()]
        if before.count("(") - before.count(")") > 0:
            continue
        lm = SPAN_LABEL.match(m.group(0))
        body = lm.group(2)
        if re.search(r"(?:^|\s)(?:\\quad\s*)?" + LBL + r"\)(?=\s|\\)", body):      # more labels inside: A) .. B) ..
            continue
        out.append(t[pos:m.start()])
        out.append(lm.group(1) + ")" + (" $" + body + "$" if body else ""))
        pos = m.end()
    out.append(t[pos:])
    return "".join(out)


def cands(t: str) -> list:
    return list(PLAIN.finditer(mask(t)))


def after_colon(t: str, m) -> bool:
    return t[:m.start()].rstrip(" \t\n").endswith(":")


def remove_label(t: str, m) -> str:
    pre, post = t[:m.start()], t[m.end():]
    ps = post.lstrip(" \t")
    if ps.startswith("\n"):
        pre = pre.rstrip(" \t")
        post = ps[1:] if (pre == "" or pre.endswith("\n")) else ps
    else:
        post = ps
        if pre.endswith(":") and post:
            pre += " "
    new = pre + post
    st = new.rstrip()
    if st and mask(st)[-1] in ";,":
        new = st[:-1].rstrip()
    return new


def strip_remnant(t: str, lab: str) -> str | None:
    """latex remnant of the label after the colon: 'б. $..$', '$9$ $..$'. None if absent."""
    m = re.search(r":([ \t\n]*)(?:" + re.escape(lab) + r"\.|\$" + re.escape(lab) + r"\$)(?=[ \t\n]+\S)[ \t\n]*", t)
    if not m:
        return None
    return t[:m.start()] + ": " + t[m.end():]


UNITS = r"(?:Вт/м|г/см|кг/м|м/с|км|дм|см|мм|м|с)"
UNIT_SUP = re.compile(r"(?<![А-Яа-яЁёA-Za-z/])(" + UNITS + r")\$\^\{?(\d)\}?\$")


def unit_sup(t: str) -> str:
    mk = mask(t)

    def f(m):
        if mk[m.start()] == "\x00":
            return m.group(0)
        return "$\\text{" + m.group(1) + "}^{" + m.group(2) + "}$"
    return UNIT_SUP.sub(f, t)


OPS = {":": ":", "+": "+", "=": "=", "<": "<", ">": ">", "≤": r"\le", "≥": r"\ge", "×": r"\times", "·": r"\cdot",
       "-": "-", "−": "-", "–": "-"}
GAP_OP = re.compile(r"^([ \t]*)([:+=<>≤≥×·\-−–])([ \t]*)$")
GAP_OP_NL = re.compile(r"^([ \t\n]*)([+=<>≤≥×·])([ \t\n]*)$")
CHAIN = re.compile(r"(?:^|[\s$])\\to(?:[\s$]|$)|arrow|ftarrow")
OP_ONLY = re.compile(r"^\$\s*([:+=<>≤≥×·\-−–]|\\cdot|\\times|\\div)\s*\$$")


def _op_math(o: str) -> str:
    return OPS.get(o, o)


def merge(t: str) -> str:
    for _ in range(20):
        spans = [m for m in MATH.finditer(t)]
        done = False
        for i in range(len(spans) - 1):
            a, b = spans[i], spans[i + 1]
            if a.group(0).startswith("$$") or b.group(0).startswith("$$"):
                continue
            if "\\begin" in a.group(0) or "\\begin" in b.group(0):
                continue
            if CHAIN.search(a.group(0)) or CHAIN.search(b.group(0)):      # «цепочка вычислений» with arrows: manual
                continue
            gap = t[a.end():b.start()]
            # three spans: A  $op$  B
            if i + 2 < len(spans) and gap.strip(" \t\n") == "" and OP_ONLY.match(b.group(0)):
                c = spans[i + 2]
                gap2 = t[b.end():c.start()]
                if (not c.group(0).startswith("$$") and gap2.strip(" \t\n") == "" and gap and gap2
                        and "\\begin" not in c.group(0)):
                    op = OP_ONLY.match(b.group(0)).group(1)
                    op = op if op.startswith("\\") else _op_math(op)
                    new = "$" + a.group(0)[1:-1].strip() + " " + op + " " + c.group(0)[1:-1].strip() + "$"
                    t = t[:a.start()] + new + t[c.end():]
                    done = True
                    break
            g = GAP_OP.match(gap) or GAP_OP_NL.match(gap)
            if not g:
                continue
            pre, op, post = g.groups()
            if op == ":" and "\n" in gap:
                continue
            if op in "-−–":
                if not (pre and post):
                    continue
            elif bool(pre) != bool(post):
                continue
            if op == ":" and not pre:
                new = "$" + a.group(0)[1:-1].strip() + "{:}" + b.group(0)[1:-1].strip() + "$"     # 14:00, 1:2
            else:
                new = "$" + a.group(0)[1:-1].strip() + " " + _op_math(op) + " " + b.group(0)[1:-1].strip() + "$"
            t = t[:a.start()] + new + t[b.end():]
            done = True
            break
        if not done:
            return t
    return t


def newline_in_span(t: str) -> str:
    def f(m):
        s = m.group(0)
        if s.startswith("$$") or "\n" not in s:
            return s
        return re.sub(r"[ \t]*\n[ \t]*", " ", s)
    return MATH.sub(f, t)


def tail(t: str) -> str:
    st = t.rstrip()
    if st and mask(st)[-1] in ";,":
        return st[:-1].rstrip()
    return t


# ---------------------------------------------------------------- per task
def process(row: dict):
    """Return (changes, classes, info) or None."""
    cols = {"question_text": row["question_text"] or "", "question_latex": row["question_latex"] or ""}
    orig = dict(cols)
    ok = {c: cols[c].count("$") % 2 == 0 and braces_ok(cols[c]) for c in cols}
    classes: set = set()
    notes: dict = {}
    cur = dict(cols)

    def step(name, fn, columns=None):
        for c in (columns or cur):
            if not ok[c] or not cur[c]:
                continue
            new = fn(cur[c])
            if new != cur[c]:
                if canon(new) != canon(cur[c]):
                    notes.setdefault("canon_fail", []).append((name, c))
                    continue
                cur[c] = new
                classes.add(name)

    step("hoist", hoist)
    # ---- label (joint)
    tt, lt = cur["question_text"], cur["question_latex"]
    tc = [m for m in cands(tt) if True]
    lc = [m for m in cands(lt) if True]
    t_ac = [m for m in tc if after_colon(tt, m)]
    l_ac = [m for m in lc if after_colon(lt, m)]
    notes["label_found"] = bool(t_ac or l_ac)
    if (t_ac or l_ac) and all(ok.values()):
        single_t = len(tc) == 1 and len(t_ac) == 1
        single_l = len(lc) == 1 and len(l_ac) == 1
        none_t, none_l = len(tc) == 0, len(lc) == 0
        new_t, new_l = tt, lt
        good = False
        if single_t and single_l and tc[0].group(1) == lc[0].group(1):
            new_t, new_l, good = remove_label(tt, tc[0]), remove_label(lt, lc[0]), True
        elif single_t and none_l:
            nl = strip_remnant(lt, tc[0].group(1))
            lab = tc[0].group(1)
            if nl is not None:
                new_t, new_l, good = remove_label(tt, tc[0]), nl, True
            elif not re.search(r":[ \t\n]*" + re.escape(lab) + r"[.)$\s]", lt):
                new_t, good = remove_label(tt, tc[0]), True     # latex already without the label
        elif none_t and single_l:
            new_l, good = remove_label(lt, lc[0]), True
        if good:
            lab = (tc[0] if single_t else lc[0]).group(1)
            for c, new in (("question_text", new_t), ("question_latex", new_l)):
                if new == cur[c]:
                    continue
                ccur = canon(cur[c])
                ok_diff = False
                for lc_ in (lab + ")", lab + ".", lab):
                    for mm in re.finditer(re.escape(lc_), ccur):
                        if ccur[:mm.start()] + ccur[mm.end():] == canon(new):
                            ok_diff = True
                            break
                    if ok_diff:
                        break
                if (not ok_diff or len(new) < 10 or new.count("$") % 2 or new.rstrip().endswith(":")
                        or not braces_ok(new)):
                    notes.setdefault("label_invalid", []).append(c)
                    continue
                cur[c] = new
                classes.add("label")
        else:
            notes["label_manual"] = "multi" if (len(tc) >= 2 or len(lc) >= 2) else "other"
    step("unit", unit_sup)
    step("merge", merge)
    step("newline", newline_in_span)
    step("tail", tail)
    changes = {c: cur[c] for c in cols if cur[c] != orig[c]}
    if not changes:
        return None
    for c in changes:
        if changes[c].count("$") % 2 or not braces_ok(changes[c]):
            return ("invalid", c)
    return changes, classes, notes


def entry(row: dict, changes: dict, reason: str, evidence: str) -> dict:
    if "question_text" in changes or "question_latex" in changes:
        changes = {**changes, "question_text": changes.get("question_text", row["question_text"]),
                   "question_latex": changes.get("question_latex", row["question_latex"])}
    e = {"id": row["id"], "before_sha256": gr.fingerprint(row), "reason": reason,
         "evidence": evidence, "changes": changes}
    gr.validate_entry(e)
    after = gr.candidate(row, e, BATCH)
    e["after_sha256"] = gr.fingerprint(after)
    return e


def katex_errors(strings: dict, scratch: Path) -> set:
    p = scratch / "kx_in.json"
    p.write_text(json.dumps(strings, ensure_ascii=False))
    r = subprocess.run(["node", str(ROOT / "tools/content_review/katex_check.js"), str(p)],
                       capture_output=True, text=True, cwd=ROOT)
    return {ln.split(" | ")[0] for ln in r.stdout.splitlines() if " | " in ln}


REASON = {
    "label": "убрана метка подпункта после двоеточия в условии одиночной задачи",
    "hoist": "метка перечисления «N)» вынесена из формулы ($1)26$ -> 1) $26$)",
    "unit": "единица измерения, приклеенная к степенному фрагменту (см$^{2}$), записана внутри формулы ($\\text{см}^{2}$)",
    "merge": "одно выражение, разбитое на несколько формул ($26$ : $5{,}2$), собрано в одну формулу",
    "newline": "перенос строки внутри формулы заменён пробелом",
    "tail": "убран висячий знак «;»/«,» в конце условия",
}


def main() -> None:
    engine = create_engine(os.environ["CONTENT_REPAIR_DATABASE_URL"])
    scratch = Path(os.environ.get("W10_SCRATCH") or tempfile.mkdtemp())
    with engine.connect() as conn:
        ids = [r[0] for r in conn.execute(text("SELECT id FROM tasks_master WHERE is_active ORDER BY id"))]
        rows = {}
        for i in range(0, len(ids), 1000):
            rows.update({r["id"]: r for r in gr._load(conn, ids[i:i + 1000], False)})
        valid_skills = {r[0] for r in conn.execute(text("SELECT id FROM knowledge_hierarchy WHERE is_active"))}
    plans, invalid = {}, []
    found = collections.Counter()
    manual = collections.Counter()
    manual_ex = collections.defaultdict(list)
    for tid in ids:
        row = rows[tid]
        res = process(row)
        t_all = (row["question_text"] or "") + "\x01" + (row["question_latex"] or "")
        # found counters (per task)
        if UNIT_SUP.search(t_all):
            found["unit"] += 1
        if re.search(r"\$\s*(?:" + LBL + r")\)\S", t_all):
            found["hoist"] += 1
        if merge(row["question_text"] or "") != (row["question_text"] or "") or merge(
                row["question_latex"] or "") != (row["question_latex"] or ""):
            found["merge"] += 1
        if any(not m.group(0).startswith("$$") and "\n" in m.group(0) for m in MATH.finditer(t_all)):
            found["newline"] += 1
        if any(mask(c.rstrip())[-1:] in (";", ",") and c.strip() for c in t_all.split("\x01")):
            found["tail"] += 1
        if re.search(r"\$[ \t\n]*\$", t_all) is not None and re.search(r"\$[ \t\n]+\$", t_all):
            manual["merge: spans separated by whitespace only (no operator)"] += 1
            if len(manual_ex["merge: spans separated by whitespace only (no operator)"]) < 3:
                manual_ex["merge: spans separated by whitespace only (no operator)"].append(tid)
        for c in (row["question_text"] or "", row["question_latex"] or ""):
            mk = mask(c.rstrip())
            if mk.endswith(")") and mk.count(")") > mk.count("("):
                manual["tail: unmatched ')' at end"] += 1
                if len(manual_ex["tail: unmatched ')' at end"]) < 3:
                    manual_ex["tail: unmatched ')' at end"].append(tid)
                break
        if res is None:
            continue
        if res[0] == "invalid":
            invalid.append((tid, res[1]))
            continue
        changes, classes, notes = res
        plans[tid] = (changes, classes, notes)
        if notes.get("label_found") and "label" not in classes:
            manual["label: multi-part or non-standard"] += 1
            if len(manual_ex["label: multi-part or non-standard"]) < 3:
                manual_ex["label: multi-part or non-standard"].append(tid)
    # label found / manual outside changed tasks (no change at all)
    for tid in ids:
        if tid in plans:
            continue
        row = rows[tid]
        tt, lt = row["question_text"] or "", row["question_latex"] or ""
        if any(after_colon(s, m) for s in (hoist(tt), hoist(lt)) for m in cands(s)):
            manual["label: multi-part or non-standard"] += 1
            if len(manual_ex["label: multi-part or non-standard"]) < 3:
                manual_ex["label: multi-part or non-standard"].append(tid)
    for tid, (changes, classes, notes) in plans.items():
        if notes.get("label_found"):
            found["label"] += 1
    for tid in ids:
        if tid not in plans:
            row = rows[tid]
            tt, lt = row["question_text"] or "", row["question_latex"] or ""
            if any(after_colon(s, m) for s in (hoist(tt), hoist(lt)) for m in cands(s)):
                found["label"] += 1
    # merge-found: tasks where merge applied or blocked
    # ---- skill fixes
    for tid, skill in SKILL_FIXES.items():
        assert skill in valid_skills and rows[tid]["is_active"], tid
        plans.setdefault(tid, ({}, set(), {}))
    # ---- KaTeX gate (no new errors)
    before_s, after_s = {}, {}
    for tid, (changes, classes, notes) in plans.items():
        for c, v in changes.items():
            before_s.setdefault(tid, []).append(rows[tid][c] or "")
            after_s.setdefault(tid, []).append(v)
    eb = katex_errors(before_s, scratch)
    ea = katex_errors(after_s, scratch)
    # katex_check prints per id; tasks whose before already failed are not compared at fragment level
    bad = ea - eb
    for tid in bad:
        plans.pop(tid, None)
        invalid.append((tid, "katex"))
    repairs, stats, examples = [], collections.Counter(), collections.defaultdict(list)
    for tid in sorted(plans):
        changes, classes, notes = plans[tid]
        row = rows[tid]
        reasons = [REASON[c] for c in ("label", "hoist", "unit", "merge", "newline", "tail") if c in classes]
        evid = []
        if classes:
            evid.append("Нормализация записи условия без изменения смысла: видимый текст (после снятия разметки $, {}, "
                        "\\text) совпадает с исходным, кроме намеренно убранной метки или висячего знака; одинаковые "
                        "функции применены к question_text и question_latex; ключ, варианты и дистракторы не менялись; "
                        "проверка KaTeX без новых ошибок.")
        if tid in SKILL_FIXES:
            changes = {**changes, "skill_id": SKILL_FIXES[tid]}
            reasons.append(SKILL_REASON)
            evid.append(SKILL_EVID)
        e = entry(row, changes, "; ".join(reasons), " ".join(evid))
        repairs.append(e)
        for c in classes:
            stats[c] += 1
            if len(examples[c]) < 60:
                examples[c].append(tid)
        if tid in SKILL_FIXES:
            stats["skill"] += 1
    manifest = {"batch": BATCH, "mode": "in_place_owner_requested", "source_checked_at": "2026-10-07T00:00:00Z",
                "student_data_included": False, "repairs": repairs}
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(OUT)
    print("entries:", len(repairs), "invalid/dropped:", len(invalid), invalid[:5])
    print("class: found / fixed")
    for c in ("label", "hoist", "unit", "merge", "newline", "tail"):
        print(f"  {c}: {found[c]} / {stats[c]}")
    print("manual:", dict(manual), {k: v for k, v in manual_ex.items()})
    random.seed(10)
    by_id = {e["id"]: e for e in repairs}
    for c in ("label", "hoist", "unit", "merge", "newline", "tail"):
        print(f"--- {c}")
        for tid in random.sample(examples[c], min(5, len(examples[c]))):
            ch = by_id[tid]["changes"]
            col = "question_latex" if ch.get("question_latex") != rows[tid]["question_latex"] else "question_text"
            b, a = rows[tid][col] or "", ch[col]
            # show the first differing window
            i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
            print(f"  {tid} [{col}] {b[max(0, i - 30):i + 50]!r} -> {a[max(0, i - 30):i + 50]!r}")
    if os.environ.get("W10_SCRATCH"):
        Path(scratch, "w10_after.json").write_text(json.dumps(
            {e["id"]: [e["changes"].get("question_text"), e["changes"].get("question_latex")] for e in repairs},
            ensure_ascii=False))
        Path(scratch, "w10_before.json").write_text(json.dumps(
            {e["id"]: [rows[e["id"]]["question_text"], rows[e["id"]]["question_latex"]] for e in repairs},
            ensure_ascii=False))


if __name__ == "__main__":
    main()
