# -*- coding: utf-8 -*-
"""Notation-only fixes inside $...$ of LaTeX display columns, and a canonical form used by the write gate."""
import re
UNI = [("°", r"^{\circ}"), ("∈", r"\in"), ("∉", r"\notin"), ("∪", r"\cup"), ("∩", r"\cap"), ("∅", r"\varnothing"), ("∞", r"\infty"),
       ("π", r"\pi"), ("φ", r"\varphi"), ("α", r"\alpha"), ("β", r"\beta"), ("γ", r"\gamma"), ("≤", r"\le"), ("≥", r"\ge"), ("≠", r"\ne"),
       ("−", "-"), ("·", r"\cdot"), ("×", r"\times"), ("²", "^{2}"), ("³", "^{3}")]
FN = {"sin": r"\sin", "cos": r"\cos", "tg": r"\operatorname{tg}", "ctg": r"\operatorname{ctg}", "tan": r"\operatorname{tg}", "cot": r"\operatorname{ctg}",
      "arcsin": r"\arcsin", "arccos": r"\arccos", "arctg": r"\operatorname{arctg}", "arcctg": r"\operatorname{arcctg}",
      "log": r"\log", "ln": r"\ln", "lg": r"\lg", "max": r"\max", "min": r"\min"}
GREEK = {"alpha": r"\alpha", "beta": r"\beta", "varphi": r"\varphi", "phi": r"\varphi", "pi": r"\pi"}

def _cmd(c, nxt):
    return c + (" " if c.startswith("\\") and c[-1].isalpha() and nxt[:1].isalnum() else "")

def fix_math(m):
    m = re.sub(r"<=", r"\\le ", m); m = re.sub(r">=", r"\\ge ", m)
    out = []
    for i, ch in enumerate(m):
        rep = dict(UNI).get(ch)
        out.append(_cmd(rep, m[i + 1:i + 2]) if rep else ch)
    m = "".join(out)
    protect = re.compile(r"\\(operatorname|mathrm|text|mbox)\{[^{}]*\}")
    def sub_words(seg):
        def r(mo):
            w = mo.group(0)
            rep = FN.get(w) or GREEK.get(w)
            return _cmd(rep, seg[mo.end():mo.end() + 1]) if rep else w
        return re.sub(r"(?<![\\a-zA-Z])(arcsin|arccos|arctg|arcctg|varphi|alpha|beta|phi|sin|cos|tg|ctg|tan|cot|log|ln|lg|max|min|pi)(?![a-zA-Z])", r, seg)
    pieces, last = [], 0
    for mo in protect.finditer(m):
        pieces.append(sub_words(m[last:mo.start()])); pieces.append(mo.group(0)); last = mo.end()
    pieces.append(sub_words(m[last:]))
    m = re.sub(r"\s+\}", "}", "".join(pieces))
    for ch, bb in (("ℕ", "N"), ("ℤ", "Z"), ("ℚ", "Q"), ("ℝ", "R")):
        m = m.replace(ch, "\\mathbb{" + bb + "}")
    m = re.sub(r"\\in\s*([NZQR])(?![a-zA-Z])", lambda mo: "\\in \\mathbb{" + mo.group(1) + "}", m)
    m = m.replace("±", "\\pm ")
    m = re.sub(r"(?<![\^_\w}.,{\\])(\\pi|\d+)\s*/\s*(\d+)(?![\d.,])", lambda mo: "\\dfrac{" + mo.group(1) + "}{" + mo.group(2) + "}", m)
    m = re.sub(r"(?:\\ |\s)+\^\{\\circ\}", lambda _: "^{\\circ}", m)
    m = re.sub(r"\^\{\\circ\}\s*C(?![a-zA-Z])", lambda _: "^{\\circ}\\mathrm{C}", m)
    return m

def fix(s):
    if not isinstance(s, str) or "$" not in s:
        return s
    parts = s.replace("$$", "\x00").split("$")
    for i in range(1, len(parts), 2):
        parts[i] = fix_math(parts[i])
    return "$".join(parts).replace("\x00", "$$")

CANON = [("varnothing", "∅"), ("emptyset", "∅"), ("infty", "∞"), ("notin", "∉"), ("circ", "°"), ("cup", "∪"), ("cap", "∩"), ("cdot", "·"), ("times", "×"),
         ("leq", "≤"), ("geq", "≥"), ("neq", "≠"), ("le", "≤"), ("ge", "≥"), ("ne", "≠"), ("varphi", "φ"), ("phi", "φ"), ("alpha", "α"), ("beta", "β"),
         ("gamma", "γ"), ("pi", "π"), ("in", "∈"), ("tan", "tg"), ("cot", "ctg")]
def canon(s):
    s = re.sub(r"\\(?:operatorname|mathrm)\{([^{}]*)\}", lambda mo: mo.group(1), str(s or ""))
    s = re.sub(r"\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}", lambda mo: mo.group(1) + "/" + mo.group(2), s)
    s = str(s).replace("$", "").replace("\\operatorname", "").replace("\\mathrm", "").replace("\\mathbb", "").replace("\\", "")
    for ch, bb in (("ℕ", "N"), ("ℤ", "Z"), ("ℚ", "Q"), ("ℝ", "R"), ("±", "pm")):
        s = s.replace(ch, bb)
    s = re.sub(r"[\s{}]", "", s).replace("<=", "≤").replace(">=", "≥").replace("−", "-").replace("²", "^2").replace("³", "^3")
    for a, b in CANON:
        s = s.replace(a, b)
    return s.replace("^°", "°")
