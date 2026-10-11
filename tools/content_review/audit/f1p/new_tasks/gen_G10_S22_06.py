from common import *
S='G10_S22_06'; X=x; pi=sp.pi
f=2*sp.sin(X/2)-sqrt(3)
zs=[2*pi/3,4*pi/3]; assert all(sp.simplify(f.subs(X,z))==0 for z in zs)
assert min(z for z in [2*pi/3,4*pi/3]) == 2*pi/3 and sp.simplify(f.subs(X,pi/3))!=0
w1=pi/3; w2=4*pi/3; w3=pi/6
assert all(sp.simplify(f.subs(X,w))!=0 for w in (w1,w3)) and sp.simplify(f.subs(X,w2))==0
T=lambda v: M(tex(v))
task(S,'B','Найдите наименьший положительный нуль функции $y=2\\sin\\dfrac{x}{2}-\\sqrt{3}$.',T(2*pi/3),
 [(T(pi/3),'Ученик решил $\\sin\\dfrac{x}{2}=\\dfrac{\\sqrt{3}}{2}$, получил $\\dfrac{x}{2}=\\dfrac{\\pi}{3}$ и записал это значение как нуль, не умножив на $2$.'),
  (T(4*pi/3),'Ученик взял второй положительный нуль: $\\dfrac{x}{2}=\\dfrac{2\\pi}{3}$, а наименьший получается из $\\dfrac{x}{2}=\\dfrac{\\pi}{3}$.'),
  (T(pi/6),'Ученик поделил $\\dfrac{\\pi}{3}$ на $2$ вместо умножения при переходе от $\\dfrac{x}{2}$ к $x$.')])
save(S, expect=1)
