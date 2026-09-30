import fitz, sys
f = sys.argv[1]; d = fitz.open("/audit/" + f); ps = [int(x) for x in sys.argv[2].split(",")]
W, H = 300, 420; cols = 4; rows = (len(ps) + cols - 1) // cols
out = fitz.open(); pg = out.new_page(width=W * cols, height=H * rows)
for i, p in enumerate(ps):
    r = fitz.Rect((i % cols) * W, (i // cols) * H, (i % cols + 1) * W, (i // cols + 1) * H)
    pg.show_pdf_page(r, d, p, clip=fitz.Rect(0, 0, d[p].rect.width, d[p].rect.height * 0.35))
pg.get_pixmap(dpi=110).save("/audit/v5png/" + sys.argv[3])
