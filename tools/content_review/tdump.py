import fitz, sys, re
d = fitz.open("/audit/" + sys.argv[1])
for p in sys.argv[2].split(","):
    t = d[int(p)].get_text(); i = t.find(sys.argv[3]) if len(sys.argv) > 3 else 0
    print("=== page", p); print(t[max(0, i - 50): i + int(sys.argv[4]) if len(sys.argv) > 4 else 1500])
