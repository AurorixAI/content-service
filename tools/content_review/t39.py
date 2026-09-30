from sympy import *
x,t=symbols('x t',real=True)
f=x**3-6*x**2+9*x+1; print("13_1", solve(diff(f,x)), solve_univariate_inequality(diff(f,x)>0,x), solve_univariate_inequality(diff(f,x)<0,x))
f=sqrt(16-x**2); print("13_4", solve(diff(f,x)), solve_univariate_inequality(diff(f,x)>0,x,domain=Interval.open(-4,4)))
xp=symbols('xp',positive=True)
f=xp**3-3*log(xp); print("18_4_2", solve(diff(f,xp)), solve_univariate_inequality(diff(f,xp)>0,xp))
f=log(xp)/xp; print("18_4_3", solve(diff(f,xp)), solve_univariate_inequality(diff(f,xp)>0,xp))
X=-5*t**2+800*t; print("6_89", solve(diff(X,t)), X.subs(t,80), solve(X,t), diff(X,t).subs(t,160))
X=-5*t**2+800*t+2000; r=solve(X,t); print("6_91", X.subs(t,80), r, [N(v) for v in r], simplify(diff(X,t).subs(t,max(r,key=lambda v:N(v)))), N(diff(X,t).subs(t,80+20*sqrt(17))))
for a,b,c in [(3,Rational(5,2),Rational(3,2)),(6,Rational(37,10),Rational(17,10))]:
    d=symbols('d',positive=True); ang=atan((a+b-c)/d)-atan((b-c)/d); print("statue", solve(diff(ang,d),d))
for base,n in [(1.001,100),(0.998,100),(1.003,25),(0.9997,25),(1000/1001,10),(1000/998,15),(1000/1003,20),(10000/9997,35)]:
    print("5_41", round(1+n*(base-1),4), round(base**n,4))
print("5_40", [round(1+0.5*d,4) for d in (0.01,0.02,-0.01,-0.02)])
