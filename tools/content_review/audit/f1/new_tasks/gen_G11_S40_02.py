from common import *
S='G11_S40_02'; X=x
def NL(f,a,b):
    F=sp.integrate(f,X); assert sp.simplify(sp.diff(F,X)-f)==0
    v=sp.simplify(F.subs(X,b)-F.subs(X,a)); assert sp.simplify(v-sp.integrate(f,(X,a,b)))==0
    return F,v
def val(F,a,b): return sp.simplify(F.subs(X,b)-F.subs(X,a))
T=lambda e: M(sp.latex(e).replace(r'\frac',r'\dfrac'))
# A1
f=3*X**2+2*X; F,v=NL(f,1,2); assert v==10
d1=F.subs(X,2); d2=-v; d3=sp.diff(f,X).subs(X,2)-sp.diff(f,X).subs(X,1)
assert (d1,d3)==(12,6)
task(S,'A','Вычислите $\\displaystyle\\int_{1}^{2}\\left(3x^{2}+2x\\right)dx$.',M('10'),
 [(M(str(d1)),'Ученик нашёл первообразную $F(x)=x^{3}+x^{2}$ верно, но подставил только верхний предел: $F(2)=12$, а $F(1)$ не вычел.'),
  (M(str(d2)),'Ученик вычел в обратном порядке: $F(1)-F(2)$.'),
  (M(str(d3)),'Ученик вместо первообразной нашёл производную подынтегральной функции $6x+2$ и подставил пределы: $14-8$.')])
# A2
f=sp.sqrt(X); F,v=NL(f,1,4); assert v==R(14,3)
w1=val(X**R(3,2),1,4); w2=val(2*sp.sqrt(X),1,4); w3=val(sp.diff(f,X)*1,1,4)
assert (w1,w2,w3)==(7,2,R(-1,4))
task(S,'A','Вычислите $\\displaystyle\\int_{1}^{4}\\sqrt{x}\\,dx$.',M(tex(v)),
 [(M(str(w1)),'Ученик проинтегрировал степень $x^{1/2}$, но забыл разделить на новый показатель $\\dfrac{3}{2}$, получив $F(x)=x^{3/2}$.'),
  (M(str(w2)),'Ученик взял первообразную $F(x)=2\\sqrt{x}$, перепутав её с удвоенным корнем.'),
  (M(tex(w3)),'Ученик вместо первообразной нашёл производную $\\dfrac{1}{2\\sqrt{x}}$ и подставил пределы.')])
# B1
f=sp.exp(2*X); F,v=NL(f,0,1); assert sp.simplify(v-(sp.E**2-1)/2)==0
task(S,'B','Вычислите $\\displaystyle\\int_{0}^{1}e^{2x}\\,dx$.',M(r'\dfrac{e^{2}-1}{2}'),
 [(M(r'e^{2}-1'),'Ученик взял первообразную $e^{2x}$ без множителя $\\dfrac{1}{2}$, как будто внутренняя функция $2x$ отсутствует.'),
  (M(r'2e^{2}-2'),'Ученик умножил на $2$ вместо деления: взял $F(x)=2e^{2x}$ (как при дифференцировании).'),
  (M(r'\dfrac{e^{2}}{2}'),'Ученик верно нашёл $F(x)=\\dfrac{e^{2x}}{2}$, но принял $F(0)=0$ вместо $F(0)=\\dfrac{1}{2}$.')])
# B2
f=2/X+1; F,v=NL(f,1,sp.E); assert sp.simplify(v-(sp.E+1))==0
w1=(2*(1)+sp.E)-(2*1+1); w2=2-0; w3=(-2/sp.E**2)-(-2)
assert sp.simplify(w1-(sp.E-1))==0 and sp.simplify(w3-(2-2/sp.E**2))==0
task(S,'B','Вычислите $\\displaystyle\\int_{1}^{e}\\left(\\dfrac{2}{x}+1\\right)dx$.',M('e+1'),
 [(M('e-1'),'Ученик принял $\\ln1=1$ и вычислил $F(1)=2\\cdot1+1=3$ вместо $F(1)=2\\ln1+1=1$.'),
  (M('2'),'Ученик проинтегрировал только слагаемое $\\dfrac{2}{x}$ и потерял слагаемое $1$ (его первообразная $x$).'),
  (M(r'2-\dfrac{2}{e^{2}}'),'Ученик вместо интегрирования дифференцировал: $\\left(\\dfrac{2}{x}\\right)\'=-\\dfrac{2}{x^{2}}$ и $(1)\'=0$, и подставил пределы в $-\\dfrac{2}{x^{2}}$.')])
# B3
f=1/sp.cos(X)**2; F,v=NL(f,0,sp.pi/3); assert sp.simplify(v-sqrt(3))==0
task(S,'B','Вычислите $\\displaystyle\\int_{0}^{\\pi/3}\\dfrac{dx}{\\cos^{2}x}$.',M(r'\sqrt{3}'),
 [(M(r'-\sqrt{3}'),'Ученик взял первообразную $-\\operatorname{tg}x$, перепутав знак: производная тангенса равна $+\\dfrac{1}{\\cos^{2}x}$.'),
  (M(r'-\ln2'),'Ученик взял первообразную $\\ln|\\cos x|$ как для интеграла от тангенса, получил $\\ln\\dfrac{1}{2}-\\ln1$.'),
  (M(r'\dfrac{4\pi}{3}'),'Ученик умножил значение подынтегральной функции $\\dfrac{1}{\\cos^{2}\\frac{\\pi}{3}}=4$ на длину промежутка $\\dfrac{\\pi}{3}$.')])
assert sp.simplify(sp.log(sp.Rational(1,2))+sp.log(2))==0
# C1
f=(X**2-1)/X; ff=sp.simplify(f); F,v=NL(sp.expand(X-1/X),1,2); 
assert sp.simplify(v-(R(3,2)-sp.log(2)))==0 and sp.simplify(sp.integrate(f,(X,1,2))-v)==0
w1=sp.simplify(val(X**2/2+sp.log(X),1,2)); 
q=lambda t: (t**3/3-t)/(t**2/2); w2=sp.nsimplify(sp.simplify(q(sp.Integer(2))-q(sp.Integer(1)))); w3=val(X**2/2-X,1,2)
assert sp.simplify(w1-(R(3,2)+sp.log(2)))==0 and w2==R(5,3) and w3==R(1,2)
task(S,'C','Вычислите $\\displaystyle\\int_{1}^{2}\\dfrac{x^{2}-1}{x}\\,dx$.',M(r'\dfrac{3}{2}-\ln2'),
 [(M(r'\dfrac{3}{2}+\ln2'),'Ученик почленно разделил дробь на $x-\\dfrac{1}{x}$, но взял для $-\\dfrac{1}{x}$ первообразную $+\\ln x$, потеряв знак.'),
  (M(r'\dfrac{5}{3}'),'Ученик проинтегрировал числитель и знаменатель отдельно и поделил результаты, как будто первообразная частного равна частному первообразных.'),
  (M(r'\dfrac{1}{2}'),'Ученик принял $\\dfrac{1}{x}$ за постоянную $1$ и проинтегрировал $x-1$, получив $F(x)=\\dfrac{x^{2}}{2}-x$.')])
# C2
f=sp.sin(X)**2; F,v=NL(f,0,sp.pi/4); assert sp.simplify(v-(sp.pi/8-R(1,4)))==0
w1=val(X/2-sp.sin(2*X)/2,0,sp.pi/4); w2=val(X/2+sp.sin(2*X)/4,0,sp.pi/4); w3=val(sp.sin(X)**3/3,0,sp.pi/4)
assert sp.simplify(w1-(sp.pi/8-R(1,2)))==0 and sp.simplify(w2-(sp.pi/8+R(1,4)))==0 and sp.simplify(w3-sqrt(2)/12)==0
task(S,'C','Вычислите $\\displaystyle\\int_{0}^{\\pi/4}\\sin^{2}x\\,dx$.',M(r'\dfrac{\pi}{8}-\dfrac{1}{4}'),
 [(M(r'\dfrac{\pi}{8}-\dfrac{1}{2}'),'Ученик применил формулу понижения степени $\\sin^{2}x=\\dfrac{1-\\cos2x}{2}$, но взял первообразную $\\cos2x$ равной $\\sin2x$, потеряв множитель $\\dfrac{1}{2}$.'),
  (M(r'\dfrac{\pi}{8}+\dfrac{1}{4}'),'Ученик после понижения степени потерял знак перед $\\cos2x$ и взял $F(x)=\\dfrac{x}{2}+\\dfrac{\\sin2x}{4}$.'),
  (M(r'\dfrac{\sqrt{2}}{12}'),'Ученик проинтегрировал $\\sin^{2}x$ как степень: $\\dfrac{\\sin^{3}x}{3}$, не учтя, что производная синуса не равна $1$.')])
save(S)
