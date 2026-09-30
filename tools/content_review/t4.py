from math import log
L=lambda b,x: log(x)/log(b)
a=L(12,18); print(L(8,9), 2*(2*a-1)/(3*(2-a)))
a=L(45,25); print(L(9,15),(a+2)/(2*(2-a)))
a=L(14,7); b=L(5,14); print(L(175,56),(3*b-2*a*b)/(a*b+2))
a=L(20,50); b=L(3,20); print(L(150,200), b*(a+4)/(3*(a*b+1)))
