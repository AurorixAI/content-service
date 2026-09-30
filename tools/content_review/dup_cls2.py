import json, re
from collections import Counter
G = json.load(open("/audit/dup_located.json"))
LAT = {"a": "а", "b": "б", "c": "в", "d": "г", "e": "д", "f": "е", "g": "ж"}
CYR = "абвгдежзиклмн"
def key(loc):
    last = (loc or "").split(":")[-1].strip()
    p = last.split(".")
    if len(p) >= 3 or (len(p) == 2 and not p[-1].isdigit()):
        ex, it = ".".join(p[:-1]), p[-1]
    else: ex, it = last, ""
    it = LAT.get(it, it)
    if it.isdigit() and ex.count(".") >= 1: it = CYR[int(it) - 1] if 0 < int(it) <= len(CYR) else it
    return ex, it
cls = Counter(); out = []
for g in G:
    ks = {key(x["loc"]) for x in g["items"]}
    exs = {k[0] for k in ks}
    c = "same_loc" if len(ks) == 1 else ("same_ex_diff_item" if len(exs) == 1 else "diff_ex")
    if g["book"] == "gen": c = "generated"
    g["cls"] = c; cls[(g["book"][:8], c)] += 1; out.append(g)
json.dump(out, open("/audit/dup_cls2.json", "w"), ensure_ascii=False, indent=0)
for k, v in sorted(cls.items()): print(k, v)
