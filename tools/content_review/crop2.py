import fitz, sys
d = fitz.open("/audit/" + (sys.argv[5] if len(sys.argv) > 5 else "vil5.pdf")); p = int(sys.argv[1]); pg = d[p]; r = pg.rect
x0,y0,x1,y1 = [float(v) for v in sys.argv[2].split(",")]
pg.get_pixmap(dpi=int(sys.argv[4]) if len(sys.argv)>4 else 300, clip=fitz.Rect(r.width*x0, r.height*y0, r.width*x1, r.height*y1)).save("/audit/v5png/"+sys.argv[3])
