# -*- coding: utf-8 -*-
"""Compare bank keys with textbook answer sections.  Usage: tb_answers.py <book>
Parses the answer section (OCR markdown) into {exercise: {item: text}}, maps every active bank task of the book to its
exercise/item, and compares the book answer with the key: exact after normalisation, numerically (SymPy) when both
parse, else by the multiset of numbers. Output /audit/tba_<book>.json: match / mismatch (numeric) / differ (numbers) /
no_answer / unparsed."""
import glob, json, re, sys, random
sys.path.insert(0, "/audit")
import psycopg2
import sympy as sp
import nested_verify2 as nv
exec(open("/audit/simp_verify.py").read().split("c = psycopg2.connect")[0].split("import nested_verify2 as nv")[1])  # prep, fix_syms, real_roots

C = "/audit/cache/"
START = {"makarychev8": "Предметный указатель 303"}
BOOKS = {
 # tbid, answer files, item style ("num" | "let"), how to read exercise/item from the bank id/source
 "merzlyak10": ("e92457e0-c22d-4485-b838-6962ecd7413f", ["mistral_20d9886d2e80c0be_p33*.md", "mistral_20d9886d2e80c0be_p34*.md", "mistral_20d9886d2e80c0be_p35*.md"], "num"),
 "nikolsky11": ("3aeaf6a8-3b03-4b74-beb6-9a282b6749f1", ["mistral_193dfa3a536d5264_p44*.md", "mistral_193dfa3a536d5264_p45*.md", "mistral_193dfa3a536d5264_p46*.md"], "let"),
 "vilenkin6": ("351a95c1-5208-4ae9-8323-6d7dd5e8bb82", ["gemini_a1977d3a58a1e322_p281-283.md", "gemini_a1977d3a58a1e322_p284-288.md"], "let"),
 "makarychev9": ("5a9f7fea-1394-4141-9d58-015972e83acc", ["mistral_2301917bac643c6d_p237-256.md"], "let"),
 "alimov9": ("2aa7af81-af13-42f9-a26b-e7e6bebaa4e6", ["mistral_41259fd910215fe8_p221-240.md"], "num"),
 "makarychev8": ("b8f4a2c1-3d5e-4f60-9182-3456789abcde", ["gemini_089fcd51f29aa95a_p295-321.md", "gemini_089fcd51f29aa95a_p309-309.md", "gemini_089fcd51f29aa95a_p31[0-9]-*.md"], "let"),
 "makarychev7": ("69fc47e1-7f72-4e79-9bf4-9ee6fb7e9b7f", ["mak7_answers.txt"], "let"),
 "vilenkin5": ("184640af-64e7-47af-a974-8b8112e6ffb2", ["vil5_answers.txt"], "let"),
 "nelin11": ("1b758c3d-9d0d-41f6-ad0b-dcf3c3872a75", ["nelin_answers.txt"], "num"),
}
LET = "абвгдежзиклмн"
book = sys.argv[1]
tbid, pats, style = BOOKS[book]
texts, seen = [], set()
for p in pats:
    for f in sorted(glob.glob(C + p)) + sorted(glob.glob("/audit/" + p)):
        t = open(f).read()
        if t[:300] in seen: continue
        seen.add(t[:300])
        if book in START and START[book] in t: t = t[t.index(START[book]):]
        texts.append(t.replace("&gt;", ">").replace("&lt;", "<").replace("**", ""))

# exercise headings «16.6.» / «1490.» accepted only in increasing order (filters «= 3.» sentence ends)
HEAD = re.compile(r"(?<![\d,.])(\d{1,2}\.\d{1,3})\.(?=\s)") if book in ("merzlyak10", "nikolsky11", "nelin11") else re.compile(r"(?<![\d,.$])(\d{1,4})\.(?=\s)")
def keynum(s):
    return tuple(int(x) for x in s.split("."))
def parse(text):
    entries, prev, last = {}, None, None
    for m in HEAD.finditer(text):
        n = m.group(1)
        k = keynum(n) if "." in n else (int(n),)
        if prev is not None and not (k > prev and (len(k) != len(prev) or k[0] - prev[0] <= 3 or len(k) == 1 and k[0] - prev[0] <= (300 if book == 'alimov9' else 60))):
            continue
        if last is not None:
            entries[last[0]] = text[last[1]:m.start()]
        last, prev = (n, m.end()), k
    if last: entries[last[0]] = text[last[1]:last[1] + 800]
    return entries
entries = {}
for t in texts:
    for k, v in parse(t).items(): entries.setdefault(k, v)

ITEM = re.compile(r"(?:(?<=\s)|^|(?<=;)|(?<=\.))\s*([1-9]\d?|[а-иa-e]|6)\)\s*")
def items(body):
    def ok(m):
        pre = body[:m.start()]
        bal = pre.count("(") + pre.count("[") - pre.count(")") - pre.count("]")
        lab = m.group(1)
        if style == "let" and lab.isdigit() and lab != "6": return False
        return bal <= 0
    out, marks = {}, [m for m in ITEM.finditer(body) if ok(m)]
    for i, m in enumerate(marks):
        lab = m.group(1)
        if style == "let":
            lab = {"a": "а", "6": "б", "e": "е", "b": "б", "c": "с"}.get(lab, lab)
            if lab.isdigit():  # numbered items in a lettered book: keep number
                pass
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        out[lab] = body[m.end():end].strip().rstrip(";.").strip()
    if not marks:
        out[""] = body.strip().rstrip(";.").strip()
    return out
ANS = {n: items(b) for n, b in entries.items()}

def norm(s):
    s = (s or "").replace("$", "").replace("\\left", "").replace("\\right", "").replace("\\dfrac", "\\frac").replace("{,}", ",")
    s = s.replace("\\leqslant", "\\le").replace("\\geqslant", "\\ge").replace("\\leq", "\\le").replace("\\geq", "\\ge")
    s = s.replace("\\operatorname{tg}", "\\tan").replace("\\operatorname{ctg}", "\\cot").replace("\\tg", "\\tan").replace("\\ctg", "\\cot").replace("tg", "\\tan").replace("ctg", "\\cot")
    s = re.sub(r"\s+", "", s).replace("\\\\", "\\").rstrip(".;,").lower()
    s = s.replace("\\,", "").replace("\\cdot", "").replace("\\mathbb{z}", "z").replace("\\mathbb{r}", "r").replace("\\mathbb{n}", "n")
    s = re.sub(r"(?<![a-z\\])[nkml](?![a-z])", "k", s)          # series parameter n/k/m/l
    s = re.sub(r"^[a-z]\\in", "", s); s = re.sub(r"^[a-z]=", "", s)
    s = re.sub(r"\((\d*\\?[a-z]+)\)", r"\1", s)                 # sin(2a) → sin2a
    s = s.replace("{", "").replace("}", "").replace("^\\circ", "°")
    return s
def nums(s):
    s = (s or "").replace("{,}", ",")
    return sorted(round(float(x.replace(",", ".")), 6) for x in re.findall(r"\d+(?:,\d+)?", re.sub(r"\\frac\{(\d+)\}\{(\d+)\}", r" \1 \2 ", s)))
def numeq(a, b):
    try:
        ea = a.replace("$", "").strip().rstrip(".;"); eb = b.replace("$", "").strip().rstrip(".;")
        if re.search(r"[А-Яа-яЁё;]", ea + eb) or "=" in ea + eb: return None
        X, Y = real_roots(fix_syms(nv.to_sym(prep(ea)))), real_roots(fix_syms(nv.to_sym(prep(eb))))
        syms = sorted(X.free_symbols | Y.free_symbols, key=str); r = random.Random(3)
        for _ in range(3):
            v = {s: sp.Rational(r.randint(2, 9), r.randint(2, 7)) for s in syms}
            a1, b1 = complex(sp.N(X.subs(v))), complex(sp.N(Y.subs(v)))
            if abs(a1 - b1) > 1e-7 * max(1, abs(a1), abs(b1)): return False
        return True
    except Exception:
        return None

def locate(tid, src):
    loc = (src or "").split("::", 1)[-1]
    last = loc.split(":")[-1].strip()
    parts = last.split(".")
    # «25.3.1» → ex 25.3, item 1 ; «6.58.3» → 6.58 / 3 ; «1490» + id suffix ; «206.1» → 206 / 1
    if book in ("merzlyak10", "nikolsky11"):
        if len(parts) >= 3: ex, it = parts[0] + "." + parts[1], parts[2]
        elif len(parts) == 2: ex, it = parts[0] + "." + parts[1], ""
        else: return None, None
    else:
        ex = parts[0]; it = parts[1] if len(parts) > 1 else ""
        if not it:
            m = re.search(r"\.(\d+|[а-я])$", tid)
            it = m.group(1) if m else ""
    if it.isdigit() and style == "let": it = LET[int(it) - 1] if int(it) <= len(LET) else it
    return ex, it

db = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
db.execute("SELECT id, source_reference, correct_answer_latex, correct_answer, left(question_latex,160) FROM tasks_master WHERE is_active AND source_reference LIKE %s", (tbid + "%",))
res = {"match": [], "mismatch": [], "differ": [], "no_answer": 0, "unparsed": 0, "same_nums": []}
for tid, src, cal, ca, q in db.fetchall():
    ex, it = locate(tid, src)
    a = ANS.get(ex or "")
    if not a:
        res["no_answer"] += 1; continue
    bt = a.get(it) if it else (a.get("") or (list(a.values())[0] if len(a) == 1 else None))
    if bt is None:
        res["no_answer"] += 1; continue
    key = cal or ca or ""
    rec = {"id": tid, "ex": ex, "it": it, "book": bt[:160], "key": key[:160], "q": q}
    if norm(bt) == norm(key):
        res["match"].append(tid); continue
    ne = numeq(bt, key)
    if ne is True: res["match"].append(tid); continue
    if ne is False: res["mismatch"].append(rec); continue
    if nums(bt) == nums(key): res["same_nums"].append(tid); continue
    res["differ"].append(rec)
json.dump(res, open(f"/audit/tba_{book}.json", "w"), ensure_ascii=False, indent=1)
print(book, "exercises parsed:", len(ANS), {k: (v if isinstance(v, int) else len(v)) for k, v in res.items()})
