from common import *
S='G11_S39_03'; X=x; n_=sp.Symbol('n',positive=True)
I=lambda f,a,b: sp.integrate(f,(X,a,b))
def trap(f,a,b,n):
    h=R(b-a,n) if all(isinstance(t,int) for t in (a,b)) else (b-a)/n
    return h/2*(f.subs(X,a)+2*sum(f.subs(X,a+i*h) for i in range(1,n))+f.subs(X,b))
def lrect(f,a,b,n):
    h=R(b-a,n); return h*sum(f.subs(X,a+i*h) for i in range(n))
# A1
f=X**2; ex=I(f,0,2); ap=trap(f,0,2,2); err=abs(ap-ex); assert (ex,ap,err)==(R(8,3),3,R(1,3))
task(S,'A','Интеграл $\\displaystyle\\int_{0}^{2}x^{2}\\,dx$ вычислили приближённо по формуле трапеций с $n=2$ отрезками и получили $3$. Найдите абсолютную погрешность приближения (точное значение интеграла найдите по формуле Ньютона — Лейбница).',M(tex(err)),
 [(M(tex(err/ex)),'Ученик вычислил относительную погрешность $\\dfrac{|3-\\frac{8}{3}|}{\\frac{8}{3}}$ вместо абсолютной.'),
  (M(tex(ex-ap)),'Ученик вычислил разность точного и приближённого значений и не взял модуль: абсолютная погрешность неотрицательна.'),
  (M(tex(ap+ex)),'Ученик сложил приближённое и точное значения вместо вычитания.')])
# A2
f=X; ex=I(f,0,4); ap=lrect(f,0,4,2); err=abs(ex-ap); assert (ex,ap,err)==(8,4,4)
w1=abs(ex-sum(f.subs(X,i*2) for i in range(2)))   # без множителя h
assert w1==6
task(S,'A','Интеграл $\\displaystyle\\int_{0}^{4}x\\,dx$ вычислили приближённо методом левых прямоугольников с $n=2$ отрезками. Найдите абсолютную погрешность приближения.',M('4'),
 [(M(str(w1)),'Ученик забыл умножить сумму значений функции $0+2$ на шаг $h=2$ и получил приближение $2$ вместо $4$.'),
  (M(tex(err/ex)),'Ученик вычислил относительную погрешность $\\dfrac{4}{8}$ вместо абсолютной.'),
  (M(str(ex)),'Ученик записал точное значение интеграла вместо погрешности.')])
# B1
f=X**3; ex=I(f,0,1); h=R(1,2); ap=trap(f,0,1,2); assert (ex,ap)==(R(1,4),R(5,16))
w1=h/2*(f.subs(X,0)+f.subs(X,h)+f.subs(X,1)); w2=h*(f.subs(X,0)+2*f.subs(X,h)+f.subs(X,1))
assert (w1,w2)==(R(9,32),R(5,8))
task(S,'B','Вычислите приближённое значение интеграла $\\displaystyle\\int_{0}^{1}x^{3}\\,dx$ по формуле трапеций с $n=2$ отрезками.',M(tex(ap)),
 [(M(tex(w1)),'Ученик не удвоил значение функции во внутреннем узле: взял $f(0)+f\\left(\\dfrac{1}{2}\\right)+f(1)$ вместо $f(0)+2f\\left(\\dfrac{1}{2}\\right)+f(1)$.'),
  (M(tex(w2)),'Ученик умножил сумму на $h=\\dfrac{1}{2}$ вместо $\\dfrac{h}{2}=\\dfrac{1}{4}$.'),
  (M(tex(ex)),'Ученик записал точное значение интеграла по формуле Ньютона — Лейбница, а не приближение по формуле трапеций.')])
# B2: bound
f=X**4; M2=sp.Max(*[0]) if False else None
f2=sp.diff(f,X,2); M2=f2.subs(X,2); assert M2==48
bnd=lambda a,b,M,n: R((b-a)**3*M,12*n**2)
key=bnd(0,2,M2,4); assert key==2
w1=R((2-0)*M2,12*4**2); w2=R((2-0)**3*M2,12*4); w3=R((2-0)**3*M2,4**2)
assert (w1,w2,w3)==(R(1,2),8,24)
# проверка границы фактом: фактическая погрешность не больше оценки
act=abs(trap(f,0,2,4)-I(f,0,2)); assert act<=key, act
task(S,'B','Погрешность формулы трапеций с $n$ отрезками оценивается как $|R_n|\\leqslant\\dfrac{(b-a)^{3}M_{2}}{12n^{2}}$, где $M_{2}=\\max\\limits_{[a;b]}|f\'\'(x)|$. Найдите эту оценку для интеграла $\\displaystyle\\int_{0}^{2}x^{4}\\,dx$ при $n=4$.',M('2'),
 [(M(tex(w1)),'Ученик взял в числителе $(b-a)$ вместо $(b-a)^{3}$.'),
  (M(str(w2)),'Ученик взял в знаменателе $n$ вместо $n^{2}$.'),
  (M(str(w3)),'Ученик забыл множитель $12$ в знаменателе.')])
# B3
M2=2; k=lambda n: R(1*M2,12*n**2)
nn=min(n for n in range(1,50) if k(n)<=R(1,100)); assert nn==5 and k(4)>R(1,100)
w1=4; w2=17; w3=min(n for n in range(1,50) if R(1,12*n**2)<=R(1,100)); assert w3==3
import math
assert math.ceil(math.sqrt(100/6))==5 and round(100/6)==17
task(S,'B','Сколько отрезков разбиения нужно взять, чтобы погрешность формулы трапеций для интеграла $\\displaystyle\\int_{0}^{1}x^{2}\\,dx$ не превышала $0{,}01$? Используйте оценку $|R_n|\\leqslant\\dfrac{(b-a)^{3}M_{2}}{12n^{2}}$.',M('5'),
 [(M('4'),'Ученик решил $n^{2}\\geqslant\\dfrac{100}{6}\\approx16{,}7$ и округлил $n\\approx4{,}08$ вниз до $4$; при $n=4$ оценка равна $\\dfrac{1}{96}>0{,}01$.'),
  (M('17'),'Ученик получил $n^{2}\\geqslant16{,}7$ и округлил само $n^{2}$ до $17$, не извлекая корень.'),
  (M('3'),'Ученик забыл взять $M_{2}=2$ (вторая производная $x^{2}$) и решал $\\dfrac{1}{12n^{2}}\\leqslant0{,}01$.')])
# C1: Simpson
f=X**3; ex=I(f,0,2); h=1
simp=R(h,3)*(f.subs(X,0)+4*f.subs(X,1)+f.subs(X,2)); trp=R(h,2)*(f.subs(X,0)+2*f.subs(X,1)+f.subs(X,2))
assert (ex,simp,trp)==(4,4,5)
wS=R(h,3)*(f.subs(X,0)+2*f.subs(X,1)+f.subs(X,2)); wH=R(h,2)*(f.subs(X,0)+4*f.subs(X,1)+f.subs(X,2))
assert (abs(wS-ex),abs(wH-ex))==(R(2,3),2)
task(S,'C','Интеграл $\\displaystyle\\int_{0}^{2}x^{3}\\,dx$ вычисляют по формуле Симпсона $\\dfrac{h}{3}\\bigl(f(x_0)+4f(x_1)+f(x_2)\\bigr)$ с $h=1$. Найдите абсолютную погрешность.',M('0'),
 [(M(tex(abs(trp-ex))),'Ученик вычислил приближение по формуле трапеций ($5$) вместо формулы Симпсона.'),
  (M(tex(abs(wS-ex))),'Ученик взял в формуле Симпсона коэффициенты $1,2,1$ вместо $1,4,1$ и получил приближение $\\dfrac{10}{3}$.'),
  (M(tex(abs(wH-ex))),'Ученик взял множитель $\\dfrac{h}{2}$ вместо $\\dfrac{h}{3}$ в формуле Симпсона и получил приближение $6$.')])
# C2
f=sp.sin(X); ex=I(f,0,sp.pi); assert ex==2
hh=sp.pi/3; ap=sp.simplify(hh*(f.subs(X,hh)+f.subs(X,2*hh)))      # f(0)=f(pi)=0
assert sp.simplify(ap-sp.pi*sqrt(3)/3)==0 and float(ap)<2
err=sp.simplify(ex-ap)
w1=ex-sqrt(3)                                   # без шага h
w2=ex-hh*(R(1,2)+R(1,2))                       # sin 60° принят за 1/2
w3=sp.simplify(sp.pi/2*(f.subs(X,hh)+f.subs(X,2*hh))-ex)    # шаг pi/2 вместо pi/3
assert float(w1)>0 and float(w2)>0 and float(w3)>0
import math
def tx(e,s_):
    assert abs(float(e)-eval(s_[1],{'pi':math.pi,'sqrt3':math.sqrt(3)}))<1e-12
    return s_[0]
S_key=(r'$2-\dfrac{\pi\sqrt{3}}{3}$','2-pi*sqrt3/3'); S_w1=(r'$2-\sqrt{3}$','2-sqrt3'); S_w2=(r'$2-\dfrac{\pi}{3}$','2-pi/3'); S_w3=(r'$\dfrac{\pi\sqrt{3}}{2}-2$','pi*sqrt3/2-2')
task(S,'C','Интеграл $\\displaystyle\\int_{0}^{\\pi}\\sin x\\,dx$ вычисляют по формуле трапеций с $n=3$ отрезками. Найдите абсолютную погрешность (в виде точного выражения).',tx(err,S_key),
 [(tx(w1,S_w1),'Ученик не умножил сумму $\\sin\\dfrac{\\pi}{3}+\\sin\\dfrac{2\\pi}{3}=\\sqrt{3}$ на шаг $h=\\dfrac{\\pi}{3}$.'),
  (tx(w2,S_w2),'Ученик принял $\\sin\\dfrac{\\pi}{3}=\\dfrac{1}{2}$ и $\\sin\\dfrac{2\\pi}{3}=\\dfrac{1}{2}$ (взял значения синуса для $30^{\\circ}$ и $150^{\\circ}$).'),
  (tx(w3,S_w3),'Ученик взял шаг $h=\\dfrac{\\pi}{2}$ вместо $\\dfrac{\\pi}{3}$ и получил приближение больше точного значения; тогда погрешность равна $\\dfrac{\\pi\\sqrt{3}}{2}-2$.')])
save(S)
