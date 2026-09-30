import json, re
exec(open("/audit/dup_locate.py").read().split("G = json.load")[0])
def rx(sig):
    parts = []
    for s in sig:
        s2 = re.escape(s).replace(",", "[,.]")
        s2 = re.sub(r"(\d)(?=(\d{3})+(?!\d))", r"\1[  ]?", s2) if len(s) > 4 and "," not in s else s2
        parts.append(r"(?<![\d,.])" + s2 + r"(?![\d])")
    return re.compile(r"[^\d]{0,25}?".join(parts), re.S)
def locate2(b, q):
    t = text(b)
    if not t: return None
    math = " ".join(re.findall(r"\$([^$]+)\$", q)) or q
    sig = nums(math)
    if len(sig) < 2: return {"sig": sig, "hits": "short"}
    tt = t.replace("{,}", ",").replace("\\,", "")
    hits = []
    for m in rx(sig).finditer(tt):
        hs = [h for h in HEAD.finditer(tt[:m.start()])]
        hits.append(hs[-1].group(1) if hs else "?")
    return {"sig": sig, "hits": hits}
G = json.load(open("/audit/dup_cls2.json"))
for g in G:
    b = g["book"][:8]
    if b in SRC: g["loc2"] = locate2(b, g["items"][0]["q"])
json.dump(G, open("/audit/dup_cls2.json", "w"), ensure_ascii=False, indent=0)
from collections import Counter
print(Counter((g["cls"], ("nosrc" if g.get("loc2") is None else "short" if g["loc2"]["hits"] == "short" else min(len(g["loc2"]["hits"]), 3))) for g in G))
