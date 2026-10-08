from common import *
S='G10_S23_07'; pi=sp.pi
T=lambda v: M(tex(v))
asin,acos,atan=sp.asin,sp.acos,sp.atan
# A1
key=asin(R(1,2))+acos(R(1,2)); assert key==pi/2 and (asin(R(1,2)),acos(R(1,2)))==(pi/6,pi/3)
w1=pi/6+pi/6; w2=pi/3+pi/3; w3=pi/6*pi/3
assert (w1,w2)==(pi/3,2*pi/3)
task(S,'A','Вычислите $\\arcsin\\dfrac{1}{2}+\\arccos\\dfrac{1}{2}$.',T(pi/2),
 [(T(w1),'Ученик принял $\\arccos\\dfrac{1}{2}=\\dfrac{\\pi}{6}$ (значение арксинуса), и получил $\\dfrac{\\pi}{6}+\\dfrac{\\pi}{6}$.'),
  (T(w2),'Ученик принял $\\arcsin\\dfrac{1}{2}=\\dfrac{\\pi}{3}$ (значение арккосинуса), и получил $\\dfrac{\\pi}{3}+\\dfrac{\\pi}{3}$.'),
  (M(r'\dfrac{\pi^{2}}{18}'),'Ученик перемножил значения вместо сложения: $\\dfrac{\\pi}{6}\\cdot\\dfrac{\\pi}{3}$.')])
# A2
key=atan(-1); assert key==-pi/4
task(S,'A','Вычислите $\\operatorname{arctg}(-1)$.',T(-pi/4),
 [(T(pi/4),'Ученик потерял знак: $\\operatorname{arctg}(-1)=-\\operatorname{arctg}1$, арктангенс — нечётная функция.'),
  (T(3*pi/4),'Ученик взял угол из промежутка $[0;\\,\\pi]$ с тангенсом $-1$; значения арктангенса лежат в $\\left(-\\dfrac{\\pi}{2};\\,\\dfrac{\\pi}{2}\\right)$.'),
  (M('-1'),'Ученик «сократил» арктангенс и тангенс и записал аргумент $-1$ вместо угла, тангенс которого равен $-1$.')])
assert sp.tan(3*pi/4)==-1 and sp.tan(-pi/4)==-1
# B1
key=asin(sp.sin(5*pi/6)); assert key==pi/6
task(S,'B','Вычислите $\\arcsin\\left(\\sin\\dfrac{5\\pi}{6}\\right)$.',T(pi/6),
 [(T(5*pi/6),'Ученик «сократил» арксинус и синус; но $\\dfrac{5\\pi}{6}$ не лежит в промежутке $\\left[-\\dfrac{\\pi}{2};\\,\\dfrac{\\pi}{2}\\right]$, поэтому ответ равен $\\pi-\\dfrac{5\\pi}{6}$.'),
  (T(-pi/6),'Ученик потерял знак: $\\sin\\dfrac{5\\pi}{6}=\\dfrac{1}{2}>0$, значит арксинус положителен.'),
  (T(5*pi/6-pi/2),'Ученик вычел $\\dfrac{\\pi}{2}$ из угла, вместо использования формулы приведения $\\sin\\dfrac{5\\pi}{6}=\\sin\\dfrac{\\pi}{6}$.')])
assert 5*pi/6-pi/2==pi/3
# B2
key=sp.cos(asin(R(-3,5))); assert key==R(4,5)
task(S,'B','Вычислите $\\cos\\left(\\arcsin\\left(-\\dfrac{3}{5}\\right)\\right)$.',T(R(4,5)),
 [(T(R(-4,5)),'Ученик решил, что косинус отрицателен, так как отрицателен синус; но $\\arcsin\\left(-\\dfrac{3}{5}\\right)$ лежит в промежутке $\\left[-\\dfrac{\\pi}{2};\\,0\\right]$, где косинус положителен.'),
  (T(R(-3,5)),'Ученик «сократил» косинус и арксинус и записал аргумент.'),
  (T(R(5,4)),'Ученик нашёл косинус как отношение гипотенузы к катету $\\dfrac{5}{4}$ вместо отношения катета к гипотенузе.')])
# B3
key=acos(sp.cos(7*pi/6)); assert key==5*pi/6
task(S,'B','Вычислите $\\arccos\\left(\\cos\\dfrac{7\\pi}{6}\\right)$.',T(5*pi/6),
 [(T(7*pi/6),'Ученик «сократил» арккосинус и косинус; но $\\dfrac{7\\pi}{6}$ не лежит в промежутке $[0;\\,\\pi]$.'),
  (T(pi/6),'Ученик вычел $\\pi$: $\\dfrac{7\\pi}{6}-\\pi$, хотя $\\cos\\dfrac{7\\pi}{6}=\\cos\\dfrac{5\\pi}{6}$ (угол $2\\pi-\\dfrac{7\\pi}{6}$).'),
  (T(-5*pi/6),'Ученик взял угол с противоположным знаком; значения арккосинуса лежат в промежутке $[0;\\,\\pi]$, отрицательных нет.')])
assert acos(sp.cos(7*pi/6))!=pi/6
# C1
key=sp.sin(2*acos(R(3,5))); assert sp.simplify(key-R(24,25))==0 and abs(float(key)-0.96)<1e-12
sin_w=R(3,5); w1=2*sin_w*R(3,5); w2=2*R(4,5); w3=2*R(3,5)**2-1
assert (w1,w2,w3)==(R(18,25),R(8,5),R(-7,25))
task(S,'C','Вычислите $\\sin\\left(2\\arccos\\dfrac{3}{5}\\right)$.',T(R(24,25)),
 [(T(R(18,25)),'Ученик принял $\\sin\\left(\\arccos\\dfrac{3}{5}\\right)=\\dfrac{3}{5}$ (значение косинуса) в формуле $\\sin2\\alpha=2\\sin\\alpha\\cos\\alpha$.'),
  (T(R(8,5)),'Ученик применил формулу $\\sin2\\alpha=2\\sin\\alpha$, потеряв множитель $\\cos\\alpha$; результат больше $1$ и не может быть значением синуса.'),
  (T(R(-7,25)),'Ученик вычислил $\\cos2\\alpha=2\\cos^{2}\\alpha-1$ вместо $\\sin2\\alpha$.')])
# C2
key=atan(2)+atan(3); assert abs(float(key)-3*float(pi)/4)<1e-12
assert R(2+3,1-2*3)==-1 and sp.atan(2)+sp.atan(3)>pi/2
w1=atan(R(2+3,1-2*3)); assert w1==-pi/4
task(S,'C','Вычислите $\\operatorname{arctg}2+\\operatorname{arctg}3$.',T(3*pi/4),
 [(T(-pi/4),'Ученик применил формулу $\\operatorname{arctg}a+\\operatorname{arctg}b=\\operatorname{arctg}\\dfrac{a+b}{1-ab}$ без поправки $+\\pi$ при $ab>1$ и получил $\\operatorname{arctg}(-1)$.'),
  (T(pi/4),'Ученик взял модуль результата формулы суммы тангенсов, получив $\\operatorname{arctg}1$; сумма двух углов, больших $\\dfrac{\\pi}{4}$, больше $\\dfrac{\\pi}{2}$.'),
  (T(pi/2),'Ученик применил формулу $\\operatorname{arctg}a+\\operatorname{arctg}\\dfrac{1}{a}=\\dfrac{\\pi}{2}$ к числам $2$ и $3$, которые не являются взаимно обратными.')])
assert float(atan(2))>float(pi/4) and float(atan(3))>float(pi/4)
save(S)
