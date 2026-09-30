import sympy as sp
x=sp.symbols('x')
def tan(f,x0):
    return sp.simplify(f.subs(x,x0)+sp.diff(f,x).subs(x,x0)*(x-x0))
pi=sp.pi
T=[('x**2',0,'0'),('x**2',1,'2*x-1'),('x**2',-1,'-2*x-1'),('x**2',2,'4*x-4'),
('x**2+2*x-3',0,'2*x-3'),('x**2+2*x-3',1,'4*x-4'),('x**2+2*x-3',-2,'-2*x-7'),
('x**3-3*x**2+x-1',0,'x-1'),('x**3-3*x**2+x-1',1,'-2*x'),('x**3-3*x**2+x-1',-2,'25*x+27'),('x**3-3*x**2+x-1',-1,'10*x+4'),
('sin(x)',0,'x'),('sin(x)',pi/2,'1'),('sin(x)',pi,'-x+pi'),('sin(x)',-pi/2,'-1'),
('cos(x)',0,'1'),('cos(x)',pi/2,'-x+pi/2'),('cos(x)',-pi,'-1'),('cos(x)',-pi/2,'x+pi/2'),
('tan(x)',0,'x'),('tan(x)',pi/6,'4*x/3+sqrt(3)/3-2*pi/9'),('tan(x)',-pi/4,'2*x+pi/2-1'),
('cot(x)',pi/2,'-x+pi/2'),('cot(x)',-pi/2,'-x-pi/2'),('cot(x)',-pi/6,'-4*x-sqrt(3)-2*pi/3'),('cot(x)',pi/4,'-2*x+1+pi/2'),
('log(x)',1,'x-1'),('log(x)',2,'x/2+log(2)-1'),('log(x)',sp.E,'x/E'),('log(x)',3,'x/3+log(3)-1'),
('log(x,2)',1,'(x-1)/log(2)'),('log(x,2)',2,'x/(2*log(2))+1-1/log(2)'),('log(x,2)',4,'x/(4*log(2))+2-1/log(2)')]
for f,x0,k in T:
    fe=sp.sympify(f)
    got=tan(fe,x0); exp=sp.sympify(k)
    d=sp.simplify(sp.expand_log(got-exp,force=True))
    print('OK ' if d==0 else 'BAD',f,x0,got if d!=0 else '')
