from common import *
S='G10_S10_01'; X=x
a=sp.solve_univariate_inequality(2*X-1>3,X,relational=False); b=sp.solve_univariate_inequality(5-X>=-1,X,relational=False)
assert (a,b)==(Interval.open(2,oo),Interval(-oo,6)) and sp.Intersection(a,b)==Interval.Lopen(2,6)
task(S,'B','Решите систему неравенств $\\begin{cases}2x-1>3,\\\\ 5-x\\geqslant-1.\\end{cases}$',settex(Interval.Lopen(2,6)),
 [(settex(Interval(2,6)),'Ученик включил конец $2$, хотя первое неравенство строгое.'),
  (settex(Interval(-oo,oo)),'Ученик объединил решения неравенств, а для системы нужно найти их пересечение.'),
  (settex(Interval(6,oo)),'Ученик не изменил знак неравенства при делении на $-1$ во втором неравенстве: получил $x\\geqslant6$.')])
save(S, expect=1)
