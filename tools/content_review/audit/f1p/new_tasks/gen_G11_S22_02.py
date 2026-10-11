from common import *
S='G11_S22_02'; X=x
f=sp.acos(2*X); d=sp.diff(f,X); key=-2/sp.sqrt(1-4*X**2); assert sp.simplify(d-key)==0
Fm=lambda e: M(sp.latex(e).replace(r'\frac',r'\dfrac'))
w1=-1/sp.sqrt(1-4*X**2); w2=2/sp.sqrt(1-4*X**2); w3=-2/sp.sqrt(1-2*X**2)
assert not any(sp.simplify(d-w)==0 for w in (w1,w2,w3))
task(S,'B','Найдите производную функции $y=\\arccos 2x$.',Fm(key),
 [(Fm(w1),'Ученик применил формулу $(\\arccos u)\'=-\\dfrac{1}{\\sqrt{1-u^{2}}}$, но не умножил на производную внутренней функции $u\'=2$.'),
  (Fm(w2),'Ученик потерял знак минус в формуле производной арккосинуса.'),
  (Fm(w3),'Ученик возвёл в квадрат только $x$, а не всё выражение $2x$: $1-2x^{2}$ вместо $1-(2x)^{2}$.')])
save(S, expect=1)
