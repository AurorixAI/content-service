from common import *
S='G10_S09_01'; X=x
SI=lambda r: sp.solve_univariate_inequality(r,X,relational=False)
s=SI(-2*X**2+5*X+3>=0); assert s==Interval(R(-1,2),3)
w1=SI(-2*X**2+5*X+3<=0); w2=SI(2*X**2+5*X+3<=0); w3=SI(2*X**2-5*X-3>=0)
assert w1==Union(Interval(-oo,R(-1,2)),Interval(3,oo)) and w3==w1
task(S,'C','Решите неравенство $-2x^{2}+5x+3\\geqslant0$.',settex(s),
 [(settex(w1),'Ученик разделил неравенство на $-1$, но не изменил знак неравенства: решал $2x^{2}-5x-3\\geqslant0$.'),
  (settex(w2),'Ученик при умножении на $-1$ изменил знак у первого слагаемого и знак неравенства, но не изменил знаки у $5x$ и $3$: решал $2x^{2}+5x+3\\leqslant0$.'),
  (settex(Interval.open(R(-1,2),3)),'Ученик верно нашёл промежуток между корнями, но взял строгие неравенства, хотя неравенство нестрогое.')])
save(S, expect=1)
