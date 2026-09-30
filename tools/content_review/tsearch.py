import fitz, sys, re
d = fitz.open("/audit/" + sys.argv[1]); print(sys.argv[1], len(d), "pages; text chars p10:", len(d[10].get_text()))
for pat in sys.argv[2:]:
    hits = [i for i in range(len(d)) if re.search(pat, d[i].get_text())]
    print(pat, hits[:10])
