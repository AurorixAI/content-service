from common import *
S='G10_S03_04'; X=x
f=X**2-4; g=X+2; assert sp.cancel(f/g)==X-2
T=lambda e,c: M(f'{sp.latex(e)},\\ {c}')
task(S,'A','Даны функции $f(x)=x^{2}-4$ и $g(x)=x+2$. Найдите $\\left(\\dfrac{f}{g}\\right)(x)$ и укажите, при каких $x$ она определена.',M(r'x-2,\ x\neq-2'),
 [(M(r'x-2,\ x\neq2'),'Ученик исключил корень числителя $x=2$ вместо корня знаменателя $x=-2$.'),
  (M(r'x-2,\ x\in\mathbb{R}'),'Ученик сократил дробь и забыл, что в исходной функции знаменатель $x+2$ не может быть равен нулю.'),
  (M(r'x+2,\ x\neq-2'),'Ученик разложил $x^{2}-4=(x-2)(x+2)$, но после сокращения оставил множитель $x+2$ вместо $x-2$.')])
f=sp.sqrt(X); g=X**2-4*X+3
D=sp.Intersection(Interval(0,oo),excl(1,3)); assert continuous_domain(f/g,X,sp.S.Reals)==D
task(S,'C','Даны функции $f(x)=\\sqrt{x}$ и $g(x)=x^{2}-4x+3$. Найдите область определения функции $\\left(\\dfrac{f}{g}\\right)(x)$.',settex(D),
 [(settex(Interval(0,oo)),'Ученик учёл только корень $x\\geqslant0$ и не исключил нули знаменателя $x=1$ и $x=3$.'),
  (settex(sp.Intersection(Interval(0,oo),excl(1))),'Ученик нашёл только один корень знаменателя $x=1$ и потерял $x=3$.'),
  (settex(excl(1,3)),'Ученик исключил нули знаменателя, но не учёл условие $x\\geqslant0$ для корня.')])
save(S, expect=2)
