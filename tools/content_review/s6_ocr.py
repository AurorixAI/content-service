import sys
exec(open("/audit/dup_locate.py").read().split("G = json.load")[0])
T = text("a7585f33")
hs = list(HEAD.finditer(T))
for n in sys.argv[1].split(","):
    for i, h in enumerate(hs):
        if h.group(1) == n:
            print("=== OCR", n, ":", " ".join(T[h.end(): hs[i + 1].start() if i + 1 < len(hs) else h.end() + 700].split())[:700])
