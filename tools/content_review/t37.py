from sympy import *
x,y=symbols('x y'); R=Rational
print(9658,solve([2*x-y-x*y-14,x+2*y+x*y+7],[x,y]),"key (3,-2),(-7/3,14)")
print(9631,solve([(2*x-y)/3-(x-2*y)/2-R(3,2),(2*x+y)/2-(x+2*y)/3-R(1,3)],[x,y]))
print(9632,solve([(x-y+1)/2+(x+y-1)/5-7,(x-y+1)/3-(x+y-1)/4+3],[x,y]))
print(9640,solve([-2*x+y-11,3*x+2*y-1],[x,y]))
