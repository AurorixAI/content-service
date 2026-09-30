# Content-based reconciliation with a textbook answer section (PDF text layer). Usage: content_recon.py <tbid8> <pdf> <answers_start_page>
import sys, re, json, fitz, psycopg2
from collections import defaultdict
tb8, pdf, astart = sys.argv[1], sys.argv[2], int(sys.argv[3])
d = fitz.open("/audit/" + pdf)
body = "\n".join(d[i].get_text() for i in range(0, astart)); ans = "\n".join(d[i].get_text() for i in range(astart, len(d)))
NUM = re.compile(r"\d+(?:[.,]\d+)?")
def normnum(s): return re.sub(r"(?<=\d)[  ](?=\d{3}\b)", "", s.replace("{,}", ",").replace("\\,", "").replace("\\ ", ""))
def nums(s):
    s = normnum(s); s = re.sub(r"\^\{?(\d+)\}?", r" \1 ", s)
    return [x.replace(".", ",") for x in NUM.findall(s)]
HEAD = re.compile(r"(?m)^\s*(\d{1,4})\.\s")
# answers: every "N." followed by text up to next "M." with M plausible
AH = re.compile(r"(?<![\d,])(\d{1,4})\.(?=\s)")
entries = defaultdict(list); hs = list(AH.finditer(ans))
for i, h in enumerate(hs):
    entries[h.group(1)].append(ans[h.end(): hs[i + 1].start() if i + 1 < len(hs) else h.end() + 400])
bn = [(m.start(), m.group().replace(".", ",")) for m in NUM.finditer(normnum(body))]
bvals = [v for _, v in bn]; btxt = normnum(body)
def locate(sig):
    n = len(sig); hits = []
    if n < 2: return None
    for i in range(len(bvals) - n + 1):
        if bvals[i:i + n] == sig:
            pos = bn[i][0]; hh = [h for h in HEAD.finditer(btxt[:pos])]
            if hh: hits.append(hh[-1].group(1))
    hits = set(hits)
    return hits.pop() if len(hits) == 1 else None
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex FROM tasks_master WHERE is_active AND source_reference LIKE %s", (tb8 + "%",))
res = {"located_with_answer": 0, "consistent": 0, "cand": [], "not_located": 0, "no_answer": 0}
for tid, q, k in c.fetchall():
    math = " ".join(re.findall(r"\$([^$]+)\$", q or "")) or (q or "")
    ex = locate(nums(math))
    if not ex: res["not_located"] += 1; continue
    if ex not in entries: res["no_answer"] += 1; continue
    res["located_with_answer"] += 1
    kn = nums(k or "")
    if not kn: continue
    ok = any(all(v in nums(e) for v in set(kn)) for e in entries[ex])
    if ok: res["consistent"] += 1
    else: res["cand"].append(dict(id=tid, ex=ex, q=" ".join((q or "").split())[:200], k=k, book=[" ".join(e.split())[:220] for e in entries[ex]]))
json.dump(res, open(f"/audit/crecon_{tb8}.json", "w"), ensure_ascii=False, indent=0)
print({k: (len(v) if isinstance(v, list) else v) for k, v in res.items()})
