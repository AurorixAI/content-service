import json, re
exec(open("/audit/dup_locate.py").read().split("G = json.load")[0])
T = text("69fc47e1")
# exercise blocks from OCR
blocks = {}
hs = list(HEAD.finditer(T))
for i, h in enumerate(hs):
    blocks.setdefault(h.group(1), T[h.end(): hs[i + 1].start() if i + 1 < len(hs) else h.end() + 1500])
R = json.load(open("/audit/tba_makarychev7.json"))
import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
out = {"same": [], "diff": [], "noocr": []}
for rec in R["mismatch"] + R["differ"]:
    c.execute("SELECT question_latex FROM tasks_master WHERE id=%s", (rec["id"],)); q = c.fetchone()[0]
    b = blocks.get(rec["ex"])
    if not b: out["noocr"].append(rec); continue
    sig = nums(" ".join(re.findall(r"\$([^$]+)\$", q)) or q)
    bn = [x.replace(".", ",") for x in NUM.findall(b.replace("{,}", ","))]
    hit = sum(1 for s in set(sig) if s in bn) / max(1, len(set(sig)))
    rec["q_full"] = " ".join(q.split())[:220]; rec["hit"] = round(hit, 2)
    (out["same"] if hit >= 0.8 else out["diff"]).append(rec)
json.dump(out, open("/audit/m7_dis.json", "w"), ensure_ascii=False, indent=0)
print({k: len(v) for k, v in out.items()})
