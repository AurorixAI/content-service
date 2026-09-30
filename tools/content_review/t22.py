from collections import Counter
from fractions import Fraction as F
import statistics as st
def cnt(s): return sorted(Counter(map(int,s.split())).items())
d1="23 30 24 25 30 24 32 33 31 31 25 33 23 30 29 24 33 30 26 29 27 29 26 28 29 30 27 30 28 32 31 27 30 27 33 28"
print('8573',cnt(d1),len(d1.split()))
d2="20 27 23 27 26 18 22 25 26 23 23 25 28 26 23 22 21 19 21 29 30 27 26 30 29 22 18 29 22 26 28 27 29 27 22 29 26 27 21 19 25 29 29 21 18 26 20 24 19 27"
c=cnt(d2);print('8581',c,len(d2.split()))
for n in ('916549695 939749596 949039391 913229296','945539391 931179396 913749193 919149494'):
    C=Counter("".join(n.split())); print('8582/3',[C.get(str(i),0) for i in range(10)])
print('8584',(3*3+4+2*5+7+3*10)/10)
print('8597',sum(x*p for x,p in zip((-4,-2,0,1,3),(F(3,11),F(1,11),F(5,11),F(1,11),F(1,11)))))
print('8598',sum(x*p for x,p in zip((-3,-2,0,1,2,4),(F(1,10),F(2,10),F(3,10),F(2,10),F(1,10),F(1,10)))))
print('8587',st.multimode([6,17,8,9,5,8,10]),'8588',st.multimode([20,11,7,5,9,11,3]),'8589',st.multimode([4,5,7,4,3,7,2,5]))
print('8590',st.median([25,16,14,21,22]))
print('8591',max([18,-4,16,-3,11,5,4,-5,1,3])-min([18,-4,16,-3,11,5,4,-5,1,3]),'8592',26-2)
print('8593',(max([0,5,0,7,0,4,0,7,0,6,0,4])+min([0,5,0,7,0,4,0,7,0,6,0,4]))/2,'8594',(8+1)/2)
print('8595',st.multimode([4,-3,2,0,3,-2]),st.median([4,-3,2,0,3,-2]),(4-3)/2,'8596',st.median([6,5,-2,4,-5,0]),(6-5)/2, sum([6,5,-2,4,-5,0])/6)
for nm,d in (('8599',[9,11,8,10]),('8600',[18,16,15,19]),('8601',[8,11,8,9,9]),('8602',[1,9,4,8,8])): print(nm,st.pvariance(d))
for nm,d in (('8603',[4,5,8,3,5]),('8604',[9,12,7,10,12])): print(nm,st.pvariance(d),'mean',st.mean(d))
d=[-4]+[-2]*4+[1]*3+[4]*2; print('8605',st.pvariance(d))
print('8571',[F(m,n) for n,m in ((10,6),(50,32),(100,68),(250,155),(500,320))])
# 8579 tetra product
C=Counter(a*b for a in range(1,5) for b in range(1,5)); print('8579',sorted(C.items()))
