import fitz, sys
f = sys.argv[2] if len(sys.argv) > 2 else "vil5.pdf"; d = fitz.open("/audit/" + f)
for p in sys.argv[1].split(","):
    d[int(p)].get_pixmap(dpi=int(sys.argv[3]) if len(sys.argv) > 3 else 110).save(f"/audit/v5png/{f[:4]}_p{p}.png")
