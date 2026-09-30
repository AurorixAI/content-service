import fitz, sys
d = fitz.open("/audit/vil5.pdf")
for p in sys.argv[1].split(","):
    pg = d[int(p)]; pg.get_pixmap(dpi=110).save(f"/audit/v5png/p{p}.png")
