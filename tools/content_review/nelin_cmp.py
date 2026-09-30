# Nelin 11: map bank tasks to the answer section (PDF text layer, garbled formulas) and flag tasks whose key numbers
# do not contain the book's numbers. Output nelin_cmp.json (flag / ok / no_answer).
import json, re, psycopg2
B = json.load(open("/audit/nelin_blocks.json"))
def exercises(body):
    out, marks = {}, list(re.finditer(r"(?:(?<=\s)|^)(\d{1,2})\.\s", body))
    prev = 0; keep = []
    for m in marks:
        n = int(m.group(1))
        if n > prev and n - prev <= 6: keep.append(m); prev = n
    for i, m in enumerate(keep):
        out[m.group(1)] = body[m.end(): keep[i + 1].start() if i + 1 < len(keep) else len(body)]
    return out
def items(body):
    marks = list(re.finditer(r"(?:(?<=\s)|^)(\d{1,2})\)\s", body))
    if not marks: return {"": body}
    return {m.group(1): body[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(body)] for i, m in enumerate(marks)}
ANS = {k: {e: items(b) for e, b in exercises(v).items()} for k, v in B.items()}
def nums(s):
    s = s.replace(",", ".")
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s)]
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, source_reference, correct_answer_latex, left(question_latex, 200) FROM tasks_master WHERE is_active AND source_reference LIKE '1b758c3d%%'")
res = {"flag": [], "ok": 0, "no_answer": 0}
for tid, src, key, q in c.fetchall():
    loc = src.split("::", 1)[1]
    sec, _, ex = loc.partition(":")
    sec = sec.replace("§", "").strip()
    e, _, it = ex.strip().partition(".")
    a = ANS.get(sec, {}).get(e)
    if not a: res["no_answer"] += 1; continue
    bt = a.get(it) if it else a.get("", " ".join(a.values()))
    if bt is None: res["no_answer"] += 1; continue
    bn, kn = nums(bt), nums((key or "").replace("{,}", ","))
    if bn and all(any(abs(x - y) < 1e-9 for y in kn) for x in bn): res["ok"] += 1; continue
    res["flag"].append({"id": tid, "loc": loc, "q": q, "key": (key or "")[:200], "book": bt[:200]})
json.dump(res, open("/audit/nelin_cmp.json", "w"), ensure_ascii=False, indent=1)
print({k: (v if isinstance(v, int) else len(v)) for k, v in res.items()})
