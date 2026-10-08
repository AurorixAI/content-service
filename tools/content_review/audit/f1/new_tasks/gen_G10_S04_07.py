from common import *
S='G10_S04_07'; X=x; Y=sp.Symbol('y',real=True)
def is_inv(f,g,pts=(-3,-1.5,0.5,2.5,4,7)):
    """f(g(x))=x and g(f(x))=x, checked symbolically when possible and numerically on points (real cube roots)"""
    def num(e,t):
        v=sp.N(e.subs(X,t)); return complex(v) if v.is_number else float('nan')
    for t in pts:
        try:
            a=sp.N(f.subs(X,sp.N(g.subs(X,t)))); b=sp.N(g.subs(X,sp.N(f.subs(X,t))))
            if not (a.is_real and b.is_real and abs(a-t)<1e-9 and abs(b-t)<1e-9): return False
        except Exception: return False
    return True
def inverse(f):
    r=sp.solve(sp.Eq(Y,f),X); assert len(r)==1,r; return r[0].subs(Y,X)
Fm=lambda e: M('y='+sp.latex(e).replace(r'\frac',r'\dfrac'))
# A1: inverse of 3x-6
f=3*X-6; g=(X+6)/3; assert is_inv(f,g) and sp.simplify(inverse(f)-g)==0
w1=(X-6)/3; w2=X/3+6; w3=3*X+6
assert not any(is_inv(f,w) for w in (w1,w2,w3))
task(S,'A','Какая из функций является обратной к функции $y=3x-6$?',M(r'y=\dfrac{x+6}{3}'),
 [(M(r'y=\dfrac{x-6}{3}'),'Ученик при выражении $x$ через $y$ перенёс $-6$ в другую часть с неверным знаком: $3x=y-6$.'),
  (M(r'y=\dfrac{x}{3}+6'),'Ученик разделил на $3$ только слагаемое $x$, оставив $-6$ без деления и сменив знак.'),
  (M('y=3x+6'),'Ученик поменял знак у свободного члена, но коэффициент $3$ оставил: в обратной функции коэффициент становится $\\dfrac{1}{3}$.')])
# A2: inverse of x^3+1
f=X**3+1; g=sp.real_root(X-1,3); assert is_inv(f,g)
w1=sp.real_root(X,3)-1; w2=sp.real_root(X+1,3); w3=(X-1)**3
assert not any(is_inv(f,w) for w in (w1,w2,w3))
task(S,'A','Какая из функций является обратной к функции $y=x^{3}+1$?',M(r'y=\sqrt[3]{x-1}'),
 [(M(r'y=\sqrt[3]{x}-1'),'Ученик извлёк корень только из $x$, а число $1$ вычел за знаком корня: из $x^{3}=y-1$ надо извлекать корень из всей разности $y-1$.'),
  (M(r'y=\sqrt[3]{x+1}'),'Ученик при переносе $1$ не сменил знак: $x^{3}=y+1$.'),
  (M(r'y=(x-1)^{3}'),'Ученик возвёл в куб вместо извлечения кубического корня: перепутал обратную операцию.')])
# B1: parameter a
a=sp.Symbol('a'); sol=sp.solve(sp.simplify((a*((X-3)/5)+3)-X),a); assert sol==[5]
fa=lambda av: av*X+3; g=(X-3)/5
assert is_inv(fa(5),g) and not any(is_inv(fa(v),g) for v in (R(1,5),-5,3))
task(S,'B','При каком значении $a$ функции $f(x)=ax+3$ и $g(x)=\\dfrac{x-3}{5}$ взаимно обратны?',M('5'),
 [(M(tex(R(1,5))),'Ученик взял коэффициент $\\dfrac{1}{5}$ из формулы $g$, не заметив, что у обратной функции коэффициент должен быть обратным числом: $a=5$.'),
  (M('-5'),'Ученик решил, что коэффициенты взаимно обратных функций противоположны, и взял число, противоположное знаменателю.'),
  (M('3'),'Ученик принял за $a$ свободный член $3$, перепутав его с коэффициентом при $x$.')])
# B2: pairs
import math
pairs={'A':(2**X,sp.log(X,2)),'B':(2**X,sp.log(X,R(1,2))),'C':(2**X,2**(-X)),'D':(2**X,X**2)}
def num_inv(f,g):
    ff=sp.lambdify(X,f,'math'); gg=sp.lambdify(X,g,'math')
    try: return all(abs(gg(ff(t))-t)<1e-9 for t in (0.5,1,2,3)) and all(abs(ff(gg(t))-t)<1e-9 for t in (0.5,1,2,3))
    except Exception: return False
assert [k for k,(f_,g_) in pairs.items() if num_inv(f_,g_)]==['A']
task(S,'B','Укажите пару взаимно обратных функций.','$y=2^{x}$ и $y=\\log_{2}x$',
 [('$y=2^{x}$ и $y=\\log_{1/2}x$','Ученик взял логарифм с обратным основанием: $\\log_{1/2}x=-\\log_{2}x$, поэтому $g(f(x))=-x$, а не $x$.'),
  ('$y=2^{x}$ и $y=2^{-x}$','Ученик решил, что обратная функция получается сменой знака показателя; но $2^{-x}\\cdot2^{x}=1$, а не равенство $g(f(x))=x$.'),
  ('$y=2^{x}$ и $y=x^{2}$','Ученик принял квадрат за операцию, обратную к возведению двойки в степень $x$; $x^{2}$ не восстанавливает $x$ из значения $2^{x}$.')])
# B3: fractional-linear
f=(X+1)/(X-2); g=inverse(f); assert sp.simplify(g-(2*X+1)/(X-1))==0 and is_inv(f,g)
w1=(X-2)/(X+1); w2=(2*X-1)/(X-1); w3=(2*X+1)/(X+1)
assert not any(is_inv(f,w) for w in (w1,w2,w3))
task(S,'B','Найдите функцию, обратную к $y=\\dfrac{x+1}{x-2}$.',M(r'y=\dfrac{2x+1}{x-1}'),
 [(M(r'y=\dfrac{x-2}{x+1}'),'Ученик взял обратное число к дроби (перевернул дробь), хотя обратная функция получается решением уравнения относительно $x$.'),
  (M(r'y=\dfrac{2x-1}{x-1}'),'Ученик получил $x(y-1)=2y-1$, потеряв знак при переносе $-2y$ и $x$ в одну часть.'),
  (M(r'y=\dfrac{2x+1}{x+1}'),'Ученик получил $x(y+1)=2y+1$, перенеся слагаемое $x$ с неверным знаком.')])
# C1: x^2-4x on x>=2
f=X**2-4*X; g=2+sp.sqrt(X+4)
assert sp.simplify(f.subs(X,g)-X)==0
assert all(abs(g.subs(X,f.subs(X,t)).evalf()-t)<1e-9 for t in (2,3,5))
w1=2-sp.sqrt(X+4); w2=2+sp.sqrt(X-4); w3=sp.sqrt(X+4)-2
assert all(abs(w1.subs(X,f.subs(X,t)).evalf()-t)>1e-6 for t in (3,5))
task(S,'C','Функция $f(x)=x^{2}-4x$ рассматривается при $x\\geqslant2$. Найдите обратную к ней функцию.',M(r'y=2+\sqrt{x+4}'),
 [(M(r'y=2-\sqrt{x+4}'),'Ученик выбрал знак минус перед корнем; но по условию $x\\geqslant2$, поэтому $x=2+\\sqrt{y+4}$ (значения обратной функции не меньше $2$).'),
  (M(r'y=2+\sqrt{x-4}'),'Ученик при выделении полного квадрата получил $(x-2)^{2}=y-4$, вместо $(x-2)^{2}-4=y$.'),
  (M(r'y=\sqrt{x+4}-2'),'Ученик при выделении полного квадрата перенёс $2$ с неверным знаком: $x=\\sqrt{y+4}-2$.')])
# C2: sqrt(x-1)+2, with domain
f=sp.sqrt(X-1)+2; g=(X-2)**2+1
assert all(abs(g.subs(X,f.subs(X,t)).evalf()-t)<1e-9 for t in (1,2,5)) and all(abs(f.subs(X,g.subs(X,t)).evalf()-t)<1e-9 for t in (2,3,6))
assert f.subs(X,1)==2   # область значений f: y>=2
task(S,'C','Найдите функцию, обратную к $y=\\sqrt{x-1}+2$, и её область определения.',M(r'y=(x-2)^{2}+1,\ x\geqslant2'),
 [(M(r'y=(x-2)^{2}+1,\ x\geqslant1'),'Ученик записал область определения исходной функции $x\\geqslant1$; область определения обратной функции равна области значений $f$, то есть $x\\geqslant2$.'),
  (M(r'y=(x+2)^{2}+1,\ x\geqslant2'),'Ученик при переносе $2$ не сменил знак: $\\sqrt{y-1}=x+2$.'),
  (M(r'y=(x-2)^{2}-1,\ x\geqslant2'),'Ученик при возведении в квадрат перенёс $1$ с неверным знаком: $y-1=(x-2)^{2}$ записал как $(x-2)^{2}-1$.')])
save(S)
