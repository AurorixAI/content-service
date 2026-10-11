from common import *
S='G10_S03_07'; X=x
dom=lambda e: continuous_domain(e,X,sp.S.Reals)
f=X+2; g=sp.sqrt(X)
D=Interval.open(0,oo); assert dom(f/g)==D
task(S,'A','Даны функции $f(x)=x+2$ и $g(x)=\\sqrt{x}$. Найдите область определения функции $\\left(\\dfrac{f}{g}\\right)(x)$.',settex(D),
 [(settex(Interval(0,oo)),'Ученик учёл только существование корня $x\\geqslant0$ и не исключил $x=0$, при котором знаменатель равен нулю.'),
  (settex(Interval.open(-2,oo)),'Ученик приравнял к нулю числитель $x+2$ вместо знаменателя и исключил $x=-2$, не учтя условие $x>0$.'),
  (settex(excl(0)),'Ученик исключил только $x=0$ и не учёл, что корень определён лишь при $x\\geqslant0$.')])
f=sp.sqrt(X-1); g=X-3
D=Union(Interval.Ropen(1,3),Interval.open(3,oo)); assert dom(f/g)==D
task(S,'B','Даны функции $f(x)=\\sqrt{x-1}$ и $g(x)=x-3$. Найдите область определения функции $\\left(\\dfrac{f}{g}\\right)(x)$.',settex(D),
 [(settex(Interval(1,oo)),'Ученик учёл корень $x\\geqslant1$, но не исключил $x=3$, где знаменатель $g(x)=x-3$ равен нулю.'),
  (settex(Union(Interval.open(1,3),Interval.open(3,oo))),'Ученик решил неравенство $x-1\\geqslant0$ как строгое и потерял точку $x=1$.'),
  (settex(excl(3)),'Ученик исключил только $x=3$ и не учёл условие $x-1\\geqslant0$.')])
f=1/sp.sqrt(X+1); g=sp.sqrt(3-X)
D=Interval.Lopen(-1,3); assert dom(f*g)==D
task(S,'C','Даны функции $f(x)=\\dfrac{1}{\\sqrt{x+1}}$ и $g(x)=\\sqrt{3-x}$. Найдите область определения функции $(f\\cdot g)(x)$.',settex(D),
 [(settex(Interval(-1,3)),'Ученик включил $x=-1$, при котором $\\sqrt{x+1}=0$ стоит в знаменателе.'),
  (settex(Interval.open(-1,3)),'Ученик решил неравенство $3-x\\geqslant0$ как строгое и потерял точку $x=3$.'),
  (settex(Interval(-oo,3)),'Ученик учёл только корень $\\sqrt{3-x}$ и не наложил на $x$ условие $x+1>0$ для первой функции.')])
save(S, expect=3)
