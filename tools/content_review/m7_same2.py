import json, re
exec(open("/audit/dup_locate.py").read().split("G = json.load")[0])
T = text("69fc47e1")
hs = list(HEAD.finditer(T)); blocks = {}
for i, h in enumerate(hs): blocks.setdefault(h.group(1), T[h.end(): hs[i + 1].start() if i + 1 < len(hs) else h.end() + 1500])
S = json.load(open("/audit/m7_self.json"))
out = []
for o in S:
    b = blocks.get(o["ex"])
    if not b: continue
    sig = nums(" ".join(re.findall(r"\$([^$]+)\$", o["q"])) or o["q"])
    bn = [x.replace(".", ",") for x in NUM.findall(b.replace("{,}", ","))]
    hit = sum(1 for s in set(sig) if s in bn) / max(1, len(set(sig)))
    if hit >= 0.6: out.append(dict(o, hit=round(hit, 2), ocr=" ".join(b.split())[:600]))
json.dump(out, open("/audit/m7_same2.json", "w"), ensure_ascii=False, indent=0)
print(len(out), "of", len(S))
for i, o in enumerate(out):
    print(f"{i}. {o['id']} [{o['v'][:12]}] hit={o['hit']} Q: {o['q'][-120:]}\n   KEY: {o['key'][:70]} | FREE BOOK: {json.dumps(o['book'], ensure_ascii=False)[:150]}")
