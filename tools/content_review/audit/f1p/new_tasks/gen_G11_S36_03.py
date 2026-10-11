from common import *
S='G11_S36_03'; X=x
key=2*sp.sin(sp.sqrt(X))-2*sp.sqrt(X)*sp.cos(sp.sqrt(X))
assert sp.simplify(sp.diff(key,X)-sp.sin(sp.sqrt(X)))==0
w1=sp.sin(sp.sqrt(X))-sp.sqrt(X)*sp.cos(sp.sqrt(X)); w2=2*sp.sin(sp.sqrt(X))+2*sp.sqrt(X)*sp.cos(sp.sqrt(X)); w3=-2*sp.cos(sp.sqrt(X))
for w in (w1,w2,w3): assert sp.simplify(sp.diff(w,X)-sp.sin(sp.sqrt(X)))!=0
Fm=lambda e: M(sp.latex(e).replace(r'\frac',r'\dfrac')+'+C')
task(S,'C','Найдите $\\displaystyle\\int\\sin\\sqrt{x}\\,dx$. Используйте замену $t=\\sqrt{x}$, а затем интегрирование по частям.',M(r'2\sin\sqrt{x}-2\sqrt{x}\cos\sqrt{x}+C'),
 [(M(r'\sin\sqrt{x}-\sqrt{x}\cos\sqrt{x}+C'),'Ученик потерял множитель $2$ из замены $dx=2t\\,dt$.'),
  (M(r'2\sin\sqrt{x}+2\sqrt{x}\cos\sqrt{x}+C'),'Ученик ошибся в знаке при интегрировании по частям: $\\int t\\sin t\\,dt=-t\\cos t+\\int\\cos t\\,dt$.'),
  (M(r'-2\cos\sqrt{x}+C'),'Ученик заменил $\\sqrt{x}$ на $t$, но не учёл множитель $2t$ в $dx=2t\\,dt$ и проинтегрировал $2\\sin t$.')])
save(S, expect=1)
