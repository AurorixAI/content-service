# For unresolved groups: print the book text block under each copy's exercise number, so the item can be checked by eye.
import json, re, sys
exec(open("/audit/dup_locate.py").read().split("G = json.load")[0])
G = json.load(open("/audit/dup_cls2.json"))
def block(b, ex):
    t = text(b)
    if not t: return None
    for m in HEAD.finditer(t):
        if m.group(1) == ex:
            nxt = HEAD.search(t, m.end())
            return " ".join(t[m.start(): (nxt.start() if nxt else m.end() + 600)][:700].split())
    return None
def exnum(loc):
    last = (loc or "").split(":")[-1].strip(); p = last.split(".")
    return ".".join(p[:2]) if (len(p) >= 3 or (len(p) == 2 and not p[1].isdigit())) and p[0].isdigit() and b8 in ("3aeaf6a8", "e92457e0") else p[0]
out = []
for g in G:
    h = (g.get("loc2") or {}).get("hits"); b8 = g["book"][:8]
    unresolved = g["cls"] == "diff_ex" and not (isinstance(h, list) and len(h) >= 1)
    if not unresolved: continue
    print("#####", b8, " || ".join(f'{x["id"]} [{x["loc"]}]' for x in g["items"]))
    print("  TASK:", g["items"][0]["q"][:200])
    for x in g["items"]:
        e = exnum(x["loc"]); bl = block(b8, e) if b8 in SRC else None
        print(f"  BOOK {e}:", (bl or "— нет текста —")[:420])
