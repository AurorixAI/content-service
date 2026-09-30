from fractions import Fraction as F
ok = [F(13,3) == F(39,9), F(24,30) == F(16,20) == F(12,15) == F(8,10) == F(4,5), F(12,60) == F(6,30) == F(4,20) == F(3,15) == F(2,10),
      F(4,8) != 1 and F(5,4) != 1, F(2,3) != F(24,30)]
print(all(ok), ok)
