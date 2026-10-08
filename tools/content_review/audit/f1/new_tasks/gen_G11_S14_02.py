from common import *
from sympy import Interval, Union
S='G11_S14_02'; X=x
SI=lambda rel: sp.solve_univariate_inequality(rel,X,relational=False)
def dom_acos(u, extra=None):
    d=Intersection_(SI(u>=-1),SI(u<=1))
    if extra is not None: d=Intersection_(d,extra)
    return d
def Intersection_(a,b): return sp.Intersection(a,b)
def numeric_check(u,d,extra=None):
    """acos(u(x)) real  <=>  x in d, tested on a grid"""
    import math
    fu=sp.lambdify(X,u,'math')
    for i in range(-3000,3001):
        t=i/500
        try: uv=float(fu(t)); ok=(abs(uv)<=1+1e-12)
        except Exception: ok=False
        if extra is not None:
            ok=ok and (t in extra)
        inside = (t in d)
        if ok!=inside and abs(t)>1e-9 and abs(abs(uv if ok or isinstance(uv,float) else 0)-1)>1e-9: raise AssertionError((t,ok,inside))
# A1
u=X/3; d=dom_acos(u); assert d==Interval(-3,3); numeric_check(u,d)
task(S,'A','Найдите область определения функции $y=\\arccos\\dfrac{x}{3}$.',settex(d),
 [(settex(Interval(-1,1)),'Ученик применил условие $-1\\leqslant x\\leqslant1$ к самому $x$, не учтя, что под арккосинусом стоит $\\dfrac{x}{3}$.'),
  (settex(Interval(R(-1,3),R(1,3))),'Ученик умножил границы неравенства $-1\\leqslant\\dfrac{x}{3}\\leqslant1$ не на $3$, а разделил на $3$.'),
  (settex(Interval.open(-3,3)),'Ученик взял строгие неравенства, хотя $\\arccos(\\pm1)$ определён.')])
# A2
u=2*X-1; d=dom_acos(u); assert d==Interval(0,1); numeric_check(u,d)
w2=Interval(R(-1,2),R(1,2)); w3=Interval(0,2)
task(S,'A','Найдите область определения функции $y=\\arccos(2x-1)$.',settex(d),
 [(settex(Interval(-1,1)),'Ученик не учёл линейное выражение под арккосинусом и записал $-1\\leqslant x\\leqslant1$.'),
  (settex(w2),'Ученик решил $-1\\leqslant2x\\leqslant1$, забыв прибавить $1$ при переносе числа $-1$.'),
  (settex(w3),'Ученик прибавил $1$ ко всем частям, но не разделил на $2$: получил $0\\leqslant x\\leqslant 2$ (границы для $2x$).')])
# B1
u=3-2*X; d=dom_acos(u); assert d==Interval(1,2); numeric_check(u,d)
task(S,'B','Найдите область определения функции $y=\\arccos(3-2x)$.',settex(d),
 [(settex(Interval(-2,-1)),'Ученик разделил неравенство $-4\\leqslant-2x\\leqslant-2$ на $2$ вместо $-2$ и получил $-2\\leqslant x\\leqslant-1$.'),
  (settex(Interval(2,4)),'Ученик получил $2\\leqslant2x\\leqslant4$, но забыл разделить на $2$.'),
  (settex(Interval(-1,1)),'Ученик применил условие $-1\\leqslant x\\leqslant1$ к самому $x$, не учтя выражение $3-2x$.')])
# B2
u=X**2-1; d=dom_acos(u); assert d==Interval(-sqrt(2),sqrt(2)); numeric_check(u,d)
task(S,'B','Найдите область определения функции $y=\\arccos(x^{2}-1)$.',settex(d),
 [(settex(Interval(0,sqrt(2))),'Ученик из $x^{2}\\leqslant2$ взял только положительный корень, забыв про $-\\sqrt{2}\\leqslant x$.'),
  (settex(Union(Interval(-oo,-sqrt(2)),Interval(sqrt(2),oo))),'Ученик решил неравенство $x^{2}\\leqslant2$ как $x^{2}\\geqslant2$ (выбрал внешние промежутки).'),
  (settex(Interval(-1,1)),'Ученик решил $x^{2}\\leqslant1$, потеряв сдвиг: верхняя граница $x^{2}-1\\leqslant1$ даёт $x^{2}\\leqslant2$.')])
# B3
u=sqrt(X); d=dom_acos(u,Interval(0,oo)); assert d==Interval(0,1)
task(S,'B','Найдите область определения функции $y=\\arccos\\sqrt{x}$.',settex(d),
 [(settex(Interval(-1,1)),'Ученик применил условие $-1\\leqslant x\\leqslant1$ к $x$, не учтя ни корень, ни условие $x\\geqslant0$.'),
  (settex(Interval(0,oo)),'Ученик учёл только существование корня $x\\geqslant0$ и пропустил условие $\\sqrt{x}\\leqslant1$.'),
  (settex(Interval.open(0,1)),'Ученик исключил концы: при $x=0$ и $x=1$ имеем $\\arccos0$ и $\\arccos1$, они определены.')])
# C1
u=(X+1)/(X-1)
i1=SI(u<=1); i2=SI(u>=-1); d=Intersection_(i1,i2)
assert i1==Interval.open(-oo,1) and d==Interval(-oo,0)
assert i2==Union(Interval(-oo,0),Interval.open(1,oo))
task(S,'C','Найдите область определения функции $y=\\arccos\\dfrac{x+1}{x-1}$.',settex(d),
 [(settex(i1),'Ученик решил только неравенство $\\dfrac{x+1}{x-1}\\leqslant1$ и забыл про $\\dfrac{x+1}{x-1}\\geqslant-1$.'),
  (settex(i2),'Ученик решил только неравенство $\\dfrac{x+1}{x-1}\\geqslant-1$ и забыл про $\\dfrac{x+1}{x-1}\\leqslant1$.'),
  (settex(Interval(-1,1)),'Ученик применил условие $-1\\leqslant x\\leqslant1$ к самому $x$, а не к дроби под арккосинусом.')])
# C2
g=sp.sqrt(X**2-1); ex=Union(Interval(-oo,-1),Interval(1,oo))
d=Intersection_(dom_acos(X/2),ex); assert d==Union(Interval(-2,-1),Interval(1,2))
task(S,'C','Найдите область определения функции $y=\\arccos\\dfrac{x}{2}+\\sqrt{x^{2}-1}$.',settex(d),
 [(settex(Interval(-2,2)),'Ученик учёл только арккосинус и не наложил условие $x^{2}-1\\geqslant0$ для корня.'),
  (settex(Interval(1,2)),'Ученик решил $x^{2}\\geqslant1$ как $x\\geqslant1$, потеряв $x\\leqslant-1$.'),
  (settex(Union(Interval.open(-2,-1),Interval.open(1,2))),'Ученик взял строгие неравенства, хотя корень и арккосинус определены на концах промежутков.')])
save(S)
