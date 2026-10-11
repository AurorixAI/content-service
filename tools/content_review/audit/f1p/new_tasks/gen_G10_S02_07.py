from common import *
S='G10_S02_07'; X=x
dom=lambda e: continuous_domain(e,X,sp.S.Reals)
f=sp.sqrt(6-2*X)/(X+1)
D=Union(Interval.Ropen(-oo,-1),Interval.open(-1,3)) if False else Union(Interval.open(-oo,-1),Interval.Lopen(-1,3)) 
D=sp.Intersection(Interval(-oo,3),excl(-1)); assert dom(f)==D
task(S,'C','Найдите область определения функции $y=\\dfrac{\\sqrt{6-2x}}{x+1}$.',settex(D),
 [(settex(Interval(-oo,3)),'Ученик учёл только корень $6-2x\\geqslant0$ и не исключил $x=-1$, при котором знаменатель равен нулю.'),
  (settex(Interval(3,oo)),'Ученик при решении неравенства $-2x\\geqslant-6$ не изменил знак неравенства.'),
  (settex(excl(-1)),'Ученик исключил только $x=-1$ и не учёл условие $6-2x\\geqslant0$ для корня.')])
save(S, expect=1)
