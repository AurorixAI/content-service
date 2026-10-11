from common import *
S='G11_S02_02'; X=x
D=sp.Intersection(sp.solve_univariate_inequality(X**2-X-6>=0,X,relational=False),Interval(-oo,5)); assert D==Union(Interval(-oo,-2),Interval(3,5))
assert continuous_domain(sp.sqrt(X**2-X-6)+sp.sqrt(5-X),X,sp.S.Reals)==D
task(S,'C','Найдите область определения функции $y=\\sqrt{x^{2}-x-6}+\\sqrt{5-x}$.',settex(D),
 [(settex(Interval(-2,3)),'Ученик решил неравенство $x^{2}-x-6\\geqslant0$ как $x^{2}-x-6\\leqslant0$ (взял промежуток между корнями).'),
  (settex(Union(Interval(-oo,-2),Interval(3,oo))),'Ученик решил только первое неравенство и не учёл условие $5-x\\geqslant0$.'),
  (settex(Interval(-oo,5)),'Ученик учёл только условие $5-x\\geqslant0$ и не наложил условие $x^{2}-x-6\\geqslant0$.')])
save(S, expect=1)
