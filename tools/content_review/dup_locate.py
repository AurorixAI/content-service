# For each strict duplicate group: find where the task's number sequence occurs in the textbook text and under which exercise header.
import json, re, glob, fitz
CACHE = "/cache/"; TB = "/tb/"
SRC = {"4b19752a": ("pdf", "7_grade/Алгебра 7 класс.pdf"), "47167115": ("pdf", "5_grade/matematika_5_rus_2_chast_2020_www.idum.uz.pdf"),
       "5630a994": ("pdf", "5_grade/matematika_1qism_5_rus.pdf"), "0fd78e9c": ("pdf", "10_grade/www.idum.uz__Algebra_10_rus_2022.pdf"),
       "1b758c3d": ("pdf", "11_grade/1623502226_algebra_-11kl__nelin-dolgova_2011-448s-ukraina.pdf"),
       "351a95c1": ("md", "gemini_a1977d3a58a1e322"), "a7585f33": ("md", "gemini_a487a6874264fe88"), "e8f3a1b2": ("md", "gemini_6b3811f14fbcf07f"),
       "b8f4a2c1": ("md", "gemini_089fcd51f29aa95a"), "5a9f7fea": ("md", "mistral_2301917bac643c6d"), "2aa7af81": ("md", "mistral_41259fd910215fe8"),
       "e92457e0": ("md", "mistral_20d9886d2e80c0be"), "3aeaf6a8": ("md", "mistral_193dfa3a536d5264"), "69fc47e1": ("md", "gemini_3f80601724dac95d")}
def pnum(m): return int(re.search(r"_p(\d+)", m).group(1))
_t = {}
def text(b):
    if b in _t: return _t[b]
    kind, ref = SRC.get(b, (None, None)); t = ""
    if kind == "md":
        seen = set()
        for f in sorted(glob.glob(CACHE + ref + "_p*.md"), key=pnum):
            x = open(f).read()
            if x[:200] in seen: continue
            seen.add(x[:200]); t += "\n" + x
    elif kind == "pdf":
        d = fitz.open(TB + ref); t = "\n".join(p.get_text() for p in d)
    _t[b] = t; return t
NUM = re.compile(r"\d+(?:[.,]\d+)?")
def nums(s):
    s = s.replace("{,}", ",").replace("\\,", "").replace("\\ ", "")
    s = re.sub(r"(?<=\d) (?=\d{3}\b)", "", s)
    s = re.sub(r"\^\{?(\d+)\}?", r" \1 ", s)
    return [x.replace(".", ",") for x in NUM.findall(s)]
HEAD = re.compile(r"(?m)^\s*(?:\*\*)?(\d{1,2}\.\d{1,3}|\d{1,4})\.(?:\*\*)?(?=\s)")
def locate(b, q):
    t = text(b)
    if not t: return None
    math = " ".join(re.findall(r"\$([^$]+)\$", q)) or q
    sig = nums(math)
    if len(sig) < 3: return {"sig": sig, "hits": "short"}
    toks = [(m.start(), m.group().replace(".", ",")) for m in NUM.finditer(re.sub(r"(?<=\d) (?=\d{3}\b)", "", t.replace("{,}", ",").replace("\\,", "")))]
    vals = [v for _, v in toks]; hits = []
    n = len(sig)
    for i in range(len(vals) - n + 1):
        if vals[i:i + n] == sig:
            pos = toks[i][0]; hs = [h for h in HEAD.finditer(t[:pos])]
            hits.append(hs[-1].group(1) if hs else "?")
    return {"sig": sig, "hits": hits}
G = json.load(open("/audit/dup_strict.json")); out = []
for gr in G:
    b = gr["book"][:8]
    res = locate(gr["book"][:8], gr["items"][0]["q"]) if b in SRC else None
    out.append(dict(gr, loc=res))
json.dump(out, open("/audit/dup_located.json", "w"), ensure_ascii=False, indent=0)
from collections import Counter
cnt = Counter()
for o in out:
    r = o["loc"]
    if r is None: cnt["no text source"] += 1
    elif r["hits"] == "short": cnt["too few numbers"] += 1
    else: cnt[f"{min(len(r['hits']),3)} hits"] += 1
print(cnt)
