"""Read-only: repair variables that slid into exponents, verify every key with SymPy.

A corrupted power is a LETTER base (not e) whose exponent group starts with an
integer followed by a letter and contains no + / - operators:
    a^{3b}^{3}  -> a^{3}b^{3}      (double superscript, raw fields)
    a^{3b^{3}}  -> a^{3}b^{3}      (nested, LaTeX fields)
    a^{4b^{8c^{12}}} -> a^{4}b^{8}c^{12}
    a^{3b}      -> a^{3}b          (single: only when the task proves it, see below)
Numeric bases (4^{x^{2}}) and exponents with operators (3x^{2}-10x+3) are never touched.

Verification of the repaired key, first that applies:
  identity   the question's expression (by the wording) equals the key
  parts      a) b) c) ... questions against a key split by ';'
  display    the repaired raw key equals an independent, already clean LaTeX key
A task that no method verifies goes to manual review; nothing is written here.
"""
import json
import random
import re

import psycopg2
from sympy import Rational, expand, simplify
from sympy.parsing.latex import parse_latex

FIELDS = ("question_text", "question_latex", "correct_answer", "correct_answer_latex",
          "answer_options", "answer_options_latex", "distractor_meta")


def _group_end(s, i):
    """Index of the brace closing the group opened at s[i] == '{'."""
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return j
    return -1


MONO = re.compile(r"-?\d+(?:[A-Za-z](?:\^\{[^{}+]*(?:\{[^{}]*\}[^{}+]*)*\}|\^-?\d)?)+")


def repair(s: str, split_single: bool) -> str:
    changed = True
    while changed:
        changed = False
        for m in re.finditer(r"(?<![A-Za-z\\])([A-Za-df-z])\^\{", s):  # letter base, not e, not a command
            open_i = m.end() - 1
            close_i = _group_end(s, open_i)
            if close_i < 0:
                continue
            inner = s[open_i + 1:close_i]
            if "+" in inner or re.search(r"(?<!\{)-(?!\d)", inner[1:]) or "\\" in inner:
                continue
            d = re.match(r"(-?\d+)([A-Za-z].*)$", inner, re.S)
            if not d:
                continue
            nested = "^" in d.group(2)
            double = s[close_i + 1:close_i + 2] == "^"
            if not (nested or double or split_single):
                continue
            if not MONO.fullmatch(inner):
                continue
            s = s[:open_i] + "{" + d.group(1) + "}" + d.group(2) + s[close_i + 1:]
            changed = True
            break
    return s


def to_sym(expr: str):
    e = expr.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac").replace("−", "-").replace("·", "\\cdot ")
    e = e.replace("\\left", "").replace("\\right", "").replace("\\,", " ")
    e = re.sub(r"(?<=\d)\{,\}(?=\d)", ".", e)
    e = re.sub(r"(?<=\d),(?=\d)", ".", e)
    sup = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
    e = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+", lambda m: "^{" + m.group(0).translate(sup) + "}", e)
    e = re.sub(r"(\d+)\s*\\frac\{(\d+)\}\{(\d+)\}", r"(\1+\\frac{\2}{\3})", e)
    e = re.sub(r"\s:\s", r" / ", e)
    e = re.sub(r"(?<![\\A-Za-z])([A-Za-z]+)\s*\(", lambda m: m.group(1) + "\\cdot (", e)
    return parse_latex(e)


def equal(e1, e2) -> bool:
    x, y = to_sym(e1), to_sym(e2)
    syms = sorted(x.free_symbols | y.free_symbols, key=str)
    rnd = random.Random(20260923)
    for _ in range(4):
        vals = {v: Rational(rnd.randint(2, 9), rnd.randint(2, 7)) for v in syms}
        a, b = complex(x.subs(vals).evalf()), complex(y.subs(vals).evalf())
        if abs(a - b) > 1e-9 * max(1.0, abs(a), abs(b)):
            return False
    return True


def blocks(text):
    return [b.strip() for b in re.findall(r"\$+([^$]+)\$+", text or "") if b.strip()]


def identity_expr(q):
    bs = [b for b in blocks(q) if not re.fullmatch(r"[a-z]\s*(=|\\ge|\\geq|\\le|\\leq|>|<)\s*-?[\d.,{}]+", b)]
    if not bs:
        return None
    low = q.lower()
    if re.search(r"произведение одночленов|перемножьте", low) and len(bs) >= 2:
        return "\\cdot ".join(f"({b})" for b in bs)
    if len(bs) >= 2 and re.search(r"\$\s*:\s*\$", q):
        return f"({bs[-2]})/({bs[-1]})"
    if len(bs) >= 2 and " и " in q:
        if "сумм" in low:
            return f"({bs[-2]})+({bs[-1]})"
        if "разност" in low:
            return f"({bs[-2]})-({bs[-1]})"
    if re.search(r"в виде (квадрата|куба|степени)|знаменатель дроби к виду|преобразуйте|выполните деление|представьте в виде дроби", low):
        return bs[-1]
    return max(bs, key=len)


def verify(q, key, clean_key):
    """Return the method that proves `key`, or None."""
    k = blocks(key) or [key]
    try:
        e = identity_expr(q)
        if e is not None and equal(e, k[0]):
            return "identity"
    except Exception:
        pass
    parts = re.split(r"\s[а-г]\)\s", " " + q)
    kparts = [p.strip() for p in re.split(r";", (blocks(key) or [key])[0]) if p.strip()]
    if len(parts) - 1 == len(kparts) >= 2:
        try:
            if all(equal(max(blocks(p) or [p], key=len), kp) for p, kp in zip(parts[1:], kparts)):
                return "parts"
        except Exception:
            pass
    if clean_key and clean_key != key:
        try:
            if equal((blocks(key) or [key])[0], (blocks(clean_key) or [clean_key])[0]) and len(blocks(key)) == len(blocks(clean_key)):
                return "display"
        except Exception:
            pass
    return None


def walk(v, fn):
    if isinstance(v, str):
        return fn(v)
    if isinstance(v, list):
        return [walk(x, fn) for x in v]
    if isinstance(v, dict):
        return {k: walk(x, fn) for k, x in v.items()}
    return v


if __name__ == "__main__":
    conn = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content")
    cur = conn.cursor()
    cur.execute(f"SELECT id, {', '.join(FIELDS)} FROM tasks_master WHERE is_active ORDER BY id")
    out = {"verified": {}, "review": {}, "untouched_legit": []}
    for row in cur.fetchall():
        tid, rec = row[0], dict(zip(FIELDS, row[1:]))
        if all(walk(rec[k], lambda s: repair(s, True)) == rec[k] for k in FIELDS):
            continue  # no corrupted power anywhere in this task
        chosen = None
        for split_single in (False, True):
            new = {k: walk(rec[k], lambda s, sp=split_single: repair(s, sp)) for k in FIELDS}
            if all(new[k] == rec[k] for k in FIELDS):
                continue
            q = new["question_latex"] or new["question_text"]
            ok_latex = verify(q, new["correct_answer_latex"] or new["correct_answer"], None)
            ok_raw = verify(new["question_text"] or q, new["correct_answer"], new["correct_answer_latex"])
            if ok_latex or ok_raw:
                chosen = (split_single, ok_latex or ok_raw, new)
                break
        entry = {"q": rec["question_latex"] or rec["question_text"], "key": rec["correct_answer"],
                 "key_latex": rec["correct_answer_latex"]}
        if chosen is None:
            new = {k: walk(rec[k], lambda s: repair(s, False)) for k in FIELDS}
            entry["repaired_key_latex"] = new["correct_answer_latex"]
            out["review"][tid] = entry
        else:
            split_single, method, new = chosen
            entry.update({"split_single": split_single, "method": method,
                          "changed": [k for k in FIELDS if new[k] != rec[k]]})
            out["verified"][tid] = entry
    json.dump(out, open("/audit/nested_verify2.json", "w"), ensure_ascii=False, indent=1)
    from collections import Counter
    print("verified:", len(out["verified"]), dict(Counter(v["method"] for v in out["verified"].values())),
          "| with single splits:", sum(v["split_single"] for v in out["verified"].values()))
    print("review:", len(out["review"]))

