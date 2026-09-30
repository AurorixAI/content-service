from sympy import *
x, y = symbols("x y"); R = Rational; ok = []
ok.append(solve(-R(1, 3)*x + 8, x) == [24])
ok.append([(-R(1, 3)*v) for v in (-6, -3, 6)] == [2, 1, -2] and [solve(-R(1, 3)*x - t, x)[0] for t in (-2, 1, 2)] == [6, -3, -6])
ok.append([-R(1, 4)*v for v in (-3, -2, -1, 0, 1, 2, 3)] == [R(3, 4), R(1, 2), R(1, 4), 0, -R(1, 4), -R(1, 2), -R(3, 4)])
ok.append([-R(8, 3)*v + 4 for v in (-3, 0, 3)] == [12, 4, -4])
ok.append(solve([y - (4*x - 10), y - (R(1, 3)*x + 1)], [x, y]) == {x: 3, y: 2})
ok.append(solve([y - (-R(4, 9)*x - 3), y - (-R(7, 5)*x - 3)], [x, y]) == {x: 0, y: -3})
ok.append(solve([-x + 2*y + 6, 3*x + 2*y - 2], [x, y]) == {x: 2, y: -2} and solve([-2*x + 2*y + 6, x + y - 2], [x, y]) == {x: R(5, 2), y: -R(1, 2)}
          and solve([y + 2*x - 2, y - R(1, 3)*x + 5], [x, y]) == {x: 3, y: -4} and solve([y + R(5, 2)*x + 10, y - R(1, 2)*x - 4], [x, y]) == {x: -R(14, 3), y: R(5, 3)})
e = R(3, 8)*y + y - R(1, 4)*y; ok.append(simplify(e - R(9, 8)*y) == 0 and e.subs(y, R(8, 3)) == 3 and e.subs(y, R(4, 9)) == R(1, 2))
# 690: classification against x + 2y = 5
def kind(a, b, c):  # a x + b y = c vs x + 2y = 5
    d = a*2 - b*1
    if d != 0: return 1
    return 3 if Matrix([[a, b, c], [1, 2, 5]]).rank() == 1 else 2
L = {"x+y=5": (1, 1, 5), "1/4y-4x=0": (-4, R(1, 4), 0), "6y+3x=10": (3, 6, 10), "0,6x=1,8": (R(6, 10), 0, R(18, 10)), "2x+4y=10": (2, 4, 10), "2x+4y=9": (2, 4, 9), "3x+6y=15": (3, 6, 15), "0,25x+0,5y=4,8": (R(1, 4), R(1, 2), R(48, 10))}
got = {k: kind(*v) for k, v in L.items()}
ok.append(got == {"x+y=5": 1, "1/4y-4x=0": 1, "6y+3x=10": 2, "0,6x=1,8": 1, "2x+4y=10": 3, "2x+4y=9": 2, "3x+6y=15": 3, "0,25x+0,5y=4,8": 2})
print("checks", len(ok), "all ok:", all(ok), ok)
