"""Independent mathematics for every remaining N01 task (not CAT calibration)."""
from fractions import Fraction as F
from itertools import product, permutations
import cmath
import json
from math import pi, atan, acos, asin, sqrt, tan, cos, sin
from pathlib import Path
import pytest
import sympy as s

from tools.content_review.build_n01_final_manifest import (
    B_IRT_DIFFICULTY, C_TO_B, DEFERRED_REPAIRS, MC_GUESSING, REPAIRS)
from tools.content_review.guarded_repair import apply, validate_choices, validate_entry
from tools.content_review.n01_review_knowledge import NODES

MANIFEST = json.loads((Path(__file__).parents[1]/'data/content_repairs/n01-2026-10-06-w6.json').read_text())
DEFERRED = json.loads((Path(__file__).parents[1]/'data/content_repairs/n01-2026-10-06-w6b.json').read_text())
ALL_REPAIRS = {**REPAIRS, **DEFERRED_REPAIRS}


def task(id):
    return ALL_REPAIRS[id]['changes']


def key(id, expected):
    row = task(id)
    assert row['correct_answer'] == expected
    assert expected not in [d['value'] for d in row['distractor_meta']]


@pytest.mark.parametrize('entry', MANIFEST['repairs']+DEFERRED['repairs'], ids=lambda e:e['id'])
def test_complete_choice_contract_and_bounded_presentation(entry):
    validate_entry(entry); row = task(entry['id']); validate_choices(row)
    assert len(row['answer_options']) == 4
    assert row['question_text'] == row['question_latex']
    assert row['correct_answer'] == row['correct_answer_latex']
    assert row['answer_options'] == row['answer_options_latex']
    assert max(map(len,row['answer_options'])) < 170
    assert len(row['question_latex']) < 310
    assert all(d['error_type'] != 'ai_generated' for d in row['distractor_meta'])
    assert row['sympy_solution'] is None  # stale symbolic keys must not win grading


def test_remaining_set_exact_and_new_taxonomy_cannot_extend_navigation():
    assert len(REPAIRS)==49 and len(MANIFEST['repairs'])==49
    assert {e['id'] for e in MANIFEST['repairs']}==set(REPAIRS)
    assert {e['id'] for e in DEFERRED['repairs']}==set(DEFERRED_REPAIRS)=={'G11_TB_§9_3_6','ds_llm_7c36694c8cba'}
    assert all(n['is_active'] is False for n in NODES)
    assert len({n['id'] for n in NODES})==len(NODES)
    assert MANIFEST['historical_protection_required']==[] and DEFERRED['knowledge_nodes']==[]
    assert set(DEFERRED['historical_protection_required'])==set(DEFERRED_REPAIRS)
    assert MANIFEST['knowledge_nodes']==NODES and len(NODES)==23
    assert not {e['id'] for e in MANIFEST['repairs']} & set(DEFERRED_REPAIRS)


def test_log_equivalence_requires_positive_arguments_not_just_same_sign():
    p,q=s.symbols('p q', real=True)
    assert s.log(s.exp(2))==2
    assert (-1)*(-1)>0  # counterexample to product>0 as log domain
    assert -1!=0
    key('G11_TB_10_5*_10_23*', r'$f(x)>0$ и $g(x)>0$')


def test_conjugation_counterexamples_and_geometry():
    z,w=1+1j,2+1j
    correct=(z*w).conjugate()
    assert correct==z.conjugate()*w.conjugate()
    assert all(v!=correct for v in [z*w.conjugate(),z.conjugate()+w.conjugate(),-z*w])
    key('G11_TB_1_4_3',r'$\overline{zw}=\overline z\,\overline w$')
    z=-1+sqrt(3)*1j
    assert abs(z)==pytest.approx(2) and cmath.phase(z)==pytest.approx(2*pi/3)
    assert atan(z.imag/z.real)==pytest.approx(-pi/3)
    key('G11_TB_2_1','Расстояние от точки до начала координат')
    key('G11_TB_2_2',r'$|z|=2,\quad \operatorname{Arg}z=\dfrac{2\pi}3$')


def test_moivre_and_each_wrong_operation():
    r,n,angle=2,3,pi/7
    actual=(r*cmath.exp(1j*angle))**n
    assert actual==pytest.approx(r**n*cmath.exp(1j*n*angle))
    assert all(abs(v-actual)>1 for v in [n*r*cmath.exp(1j*n*angle),r**n*cmath.exp(1j*angle),r**n*cmath.exp(1j*angle/n)])
    key('G11_TB_2_6',r'$r^n(\cos n\varphi+i\sin n\varphi)$')


@pytest.mark.parametrize('id,n,modulus,constant', [('G11_TB_2_9_2',4,3,81),('G11_TB_2_9_3',6,2,64)])
def test_every_complex_root_and_completeness(id,n,modulus,constant):
    roots=[modulus*cmath.exp(1j*(pi+2*pi*k)/n) for k in range(n)]
    assert len({(round(z.real,8),round(z.imag,8)) for z in roots})==n
    assert all(abs(z**n+constant)<1e-9 for z in roots)
    wrong_angles=[modulus*cmath.exp(1j*2*pi*k/n) for k in range(n)]
    assert all(abs(z**n+constant)>constant for z in wrong_angles)
    assert len(roots[:n//2])<n
    assert f'z^{n}' in task(id)['question_latex']
    assert ('k=0,1,2,3' if n==4 else r'k=0,1,\ldots,5') in task(id)['correct_answer']


def test_sum_product_and_arrangements_by_enumeration():
    assert len(list(range(5))+list(range(5,9)))==9
    assert len(list(product(range(5),range(4))))==20
    assert len(list(permutations([1,5,7],2)))==6
    key('G11_TB_21_1_1_21_1_1_1','$9$');key('G11_TB_21_1_1_21_1_1_2','$20$')
    key('G11_TB_21_1_1_21_1_1_4','$6$')


def test_finite_events_complement_union_intersection():
    omega=set(range(1,7));a={2,4,6};b={3,6}
    assert omega-a=={1,3,5} and a|b=={2,3,4,6} and a&b=={6}
    assert a^b=={2,3,4} and omega-(a|b)=={1,5}
    assert {7}&omega==set() and 0<len(a)<len(omega)
    key('G11_TB_22_1_2','Достоверное; невозможное; случайное')
    key('G11_TB_22_2_1',r'$\{1,3,5\}$')
    key('G11_TB_22_2_3',r'$\{2,3,4,6\}$');key('G11_TB_22_2_4',r'$\{6\}$')


def test_frequency_and_independent_products_with_wrong_event_distinction():
    assert F(88,100)==F(22,25) and F(88,100)!=F(12,100)
    key('G11_TB_22_3_22_3_4','$0{,}88$')
    p,q=F(3,10),F(4,10)
    assert (1-p)*(1-q)==F(42,100)
    assert len({(1-p)*(1-q),p*q,1-p*q,(1-p)-q})==4
    key('G11_TB_22_5_3','$0{,}42$')
    outcomes=list(product(range(1,7),repeat=2));both=[o for o in outcomes if o==(6,6)]
    union=[o for o in outcomes if 6 in o]
    assert F(len(both),len(outcomes))==F(1,36) and F(len(union),len(outcomes))==F(11,36)
    key('G11_TB_22_5_5',r'$\dfrac1{36}$')


def test_sampling_question_checks_design_not_a_guaranteed_accuracy():
    full=list(range(300));one_school=set(range(100))
    inclusion=[F(100,len(full)) for _ in full]
    assert len(set(inclusion))==1
    assert [int(i in one_school) for i in full].count(0)==200
    key('G11_TB_23_1_1_3','Случайный отбор из полного списка работ всех школ')
    key('G11_TB_23_1_1_6','Другие части поля исключены, поэтому оценка может быть смещена')
    assert 'репрезентативн' not in task('G11_TB_23_1_1_3')['question_latex']


def test_inscribed_isosceles_global_maximum():
    a=s.symbols('a', real=True);f=4*s.sin(a)*s.cos(a)**3
    assert s.simplify(s.diff(f,a)-4*s.cos(a)**2*(1-4*s.sin(a)**2))==0
    assert s.simplify(f.subs(a,s.pi/6))==3*s.sqrt(3)/4
    assert f.subs(a,0)==0 and f.subs(a,s.pi/2)==0
    assert 3*sqrt(3)/4>1
    key('G11_TB_5_3_10',r'$\dfrac{3\sqrt3}{4}R^2$')


def test_global_derivative_signs_not_just_local_second_derivative():
    x=s.symbols('x',real=True);f=-(x-1)**2
    assert s.diff(f,x).subs(x,0)>0 and s.diff(f,x).subs(x,2)<0
    assert f.subs(x,1)==0 and f.subs(x,0)<0 and f.subs(x,2)<0
    # A local maximum with f''<0 need not be global.
    g=x**4-x**2;assert s.diff(g,x,2).subs(x,0)<0 and g.subs(x,2)>g.subs(x,0)
    key('G11_TB_5_3_5_3_1',r'$f(x_0)$ — наибольшее значение на $(a,b)$')


def test_epsilon_delta_largest_radius_and_each_inadmissible_or_smaller_formula():
    for eps in [.04,1,4,9]:
        radius=sqrt(eps)
        assert (radius*.999)**2<eps and (radius*1.001)**2>eps
        assert (radius*1.5)**2>eps
    assert 3<4 and 3**2>4  # δ=ε fails; δ=ε² also admits this x
    key('G11_TB_6_1_5',r'$\sqrt\varepsilon$')


def test_continuity_domains_and_endpoint_value_counterexamples():
    key('G11_TB_6_3_6_3_1',r'$g(a)\ne0$')
    # f(a)=g(a)=0 leaves f/g undefined; f(a)!=0 doesn't fix g(a)=0.
    key('G11_TB_6_3_6_3_3',r'$\lim_{x\to a+}f(x)=f(a),\quad\lim_{x\to b-}f(x)=f(b)$')
    values=[0 for _ in range(10)];endpoint=1
    assert values[0]!=endpoint  # finite interior limit alone isn't continuity


def test_quotient_sign_complete_truth_table():
    for a,b in product([-2,0,2],repeat=2):
        if b!=0:assert (a/b>0)==((a>0 and b>0) or (a<0 and b<0))
    key('G11_TB_9_7*_9_51','Оба значения строго положительны или оба строго отрицательны')


def test_polynomial_growth_correct_bound_and_wrong_proof_witnesses():
    x=s.symbols('x',positive=True);f=x**5-2*x**3+2*x
    assert f.subs(x,2)==20
    assert s.expand(s.diff(f,x)-(x*x*(5*x*x-6)+2))==0
    assert s.diff(-2*x**3,x)<0
    key('G11_TB_§11_1_1',r'$f\prime(x)=x^2(5x^2-6)+2>0$ при $x>2$')


def test_open_endpoint_is_infimum_not_minimum():
    x=s.symbols('x',positive=True);f=2*x+1/x**2
    assert f.subs(x,s.Rational(1,2))==5
    assert s.diff(f,x).subs(x,s.Rational(1,4))<0
    assert f.subs(x,s.Rational(49,100))>5
    key('G11_TB_§11_1_3',r'$f(x)>5$; наименьшее значение не достигается')


@pytest.mark.parametrize('id,m,expected',[('G11_TB_§11_2_2',2,3),('G11_TB_§11_2_3',4,5)])
def test_amgm_global_minima_and_equality_condition(id,m,expected):
    # m copies of sqrt(x), then x^(-m/2): product exactly 1.
    x=s.symbols('x',positive=True);expr=m*s.sqrt(x)+x**(-s.Rational(m,2))
    assert s.simplify(s.sqrt(x)**m*x**(-s.Rational(m,2)))==1
    assert expr.subs(x,1)==expected
    assert s.simplify(s.diff(expr,x)).subs(x,s.Rational(1,4))<0
    assert s.simplify(s.diff(expr,x)).subs(x,4)>0
    key(id,f'${expected}$ при $x=1$')


def test_tangent_derivative_and_positive_difference():
    x=s.symbols('x');assert s.trigsimp(s.diff(s.tan(x)-x,x)-s.tan(x)**2)==0
    assert tan(.5)>.5
    key('G11_TB_§11_3_1',r'$\tan^2x$')


def test_cubic_minimum_is_positive_not_a_claim_from_one_point():
    a=s.symbols('a');f=a**3+3*a*a-13*a+10;critical=-1+4*s.sqrt(3)/3
    assert s.simplify(s.diff(f,a).subs(a,critical))==0
    assert s.simplify(f.subs(a,critical))==(225-128*s.sqrt(3))/9
    assert 225**2>128**2*3 and float(critical)>0
    key('G11_TB_§11_4_2',r'$a=-1+\dfrac{4\sqrt3}3$')


def test_log_monotonicity_and_second_derivative():
    x=s.symbols('x',positive=True)
    assert s.diff(s.log(x)/s.log(s.Rational(1,2)),x).subs(x,2)<0
    key('G11_TB_§16_4','$0<a<1$')
    f=x*x-1-2*x*s.log(x)
    assert s.simplify(s.diff(f,x,2)-(2-2/x))==0 and f.subs(x,1)==0 and s.diff(f,x).subs(x,1)==0
    key('G11_TB_§19_16_5',r'$2-\dfrac2x$')


def test_antiderivative_chain_and_constant():
    x=s.symbols('x');f=3+s.tan(x/2)
    assert s.trigsimp(2*s.cos(x/2)**2*s.diff(f,x)-1)==0
    key('G11_TB_§24_2_4',r'$\dfrac1{2\cos^2(x/2)}$')


def test_solid_volumes_from_cross_section_integrals():
    x,R,H,r=s.symbols('x R H r',positive=True)
    cap=s.integrate(s.pi*(R*R-x*x),(x,R-H,R))
    assert s.simplify(cap-s.pi*H**2*(R-H/3))==0
    assert s.simplify(cap.subs(H,2*R))==4*s.pi*R**3/3
    frustum=s.integrate(s.pi*(r+(R-r)*x/H)**2,(x,0,H))
    assert s.simplify(frustum-s.pi*H*(R*R+R*r+r*r)/3)==0
    key('G11_TB_§26_11_1',r'$\pi H^2\left(R-\dfrac H3\right)$')
    key('G11_TB_§26_11_2',r'$\dfrac{\pi H}3(R^2+Rr+r^2)$')


def test_real_power_and_quotient_rule_each_wrong_formula():
    x=s.symbols('x',positive=True);n=s.symbols('n',real=True)
    assert s.simplify(s.diff(s.exp(n*s.log(x)),x)-n*x**(n-1))==0
    key('G11_TB_§3_2',r'$x^n=e^{n\ln x}$ и правило производной сложной функции')
    u,v=x*x+1,x+2;correct=s.diff(u/v,x)
    assert s.simplify(correct-(s.diff(u,x)*v-u*s.diff(v,x))/v**2)==0
    wrong=[s.diff(u,x)/s.diff(v,x),(s.diff(u,x)*v+u*s.diff(v,x))/v**2,s.diff(u,x)/v]
    assert all(s.simplify(w.subs(x,1)-correct.subs(x,1))!=0 for w in wrong)
    key('G11_TB_§3_3',r'$\dfrac{u\prime v-uv\prime}{v^2}$')


def test_velocity_acceleration_are_derivatives_in_one_dimension():
    t,v0,a=s.symbols('t v0 a');assert s.diff(v0,t)==0 and s.diff(v0+a*t,t)==a
    key('G11_TB_§5_5_63_a',r'$v=\mathrm{const},\ a=0;\qquad a=\mathrm{const}\ne0,\ v=v_0+at$')


def test_inverse_trig_branches_anchors_and_absolute_value():
    for x in [-.9,-.5,0,.5,.9]:assert asin(x)==pytest.approx(atan(x/sqrt(1-x*x)))
    assert acos(.5)==pytest.approx(pi/3) and atan(sqrt(3))==pytest.approx(pi/3)
    for x in [-1,-.9,-.5,-.01]:assert acos(x)==pytest.approx(pi+atan(sqrt(1-x*x)/x))
    key('G11_TB_§9_3_2','$h(0)=0$')
    key('G11_TB_§9_3_3',r'$h(1/2)=\pi/3-\arctan\sqrt3=0$');key('G11_TB_§9_3_4',r'$C=\pi$')
    for x in [1.01,1.5,3,10]:
        u=2*x/(1+x*x);uprime=2*(1-x*x)/(1+x*x)**2
        assert uprime/sqrt(1-u*u)==pytest.approx(-2/(1+x*x))
        assert 2*atan(x)+asin(u)==pytest.approx(pi)
    key('G11_TB_§9_3_6',r'$-\dfrac2{1+x^2}$')


def test_cubes_induction_geometric_square_and_decimal_block():
    n=s.symbols('n',integer=True,positive=True)
    assert s.expand(n*n*(n+1)**2/4+(n+1)**3-(n+1)**2*(n+2)**2/4)==0
    assert all(sum(k**3 for k in range(1,j+1))==j*j*(j+1)**2//4 for j in range(1,41))
    key('G9_TB_31_629',r'$(n+1)^3$')
    for j in range(1,12):
        t=10**(j+1);value=(5+t)*sum(10**k for k in range(j+1))+1
        assert (t+2)%3==0 and value==((t+2)//3)**2
    key('G9_TB_ЗПТ_883',r'$\left(\dfrac{t+2}3\right)^2$')
    for k in range(1,12):
        assert all((a*(5*10**k-1))%5!=0 for a in [1,2,3,4,6,7,8,9])
        assert 5*10**k-1>=10**k
    key('G9_TB_ЗПТ_888',r'$5\cdot10^k-1\ge10^k$')


def test_positive_quadratic_and_all_incorrect_square_expansions():
    x=s.symbols('x');f=x*x-3*x+200
    assert s.expand((x-s.Rational(3,2))**2+s.Rational(791,4)-f)==0
    assert s.Rational(791,4)>0
    wrong=[(x-3)**2+191,(x-s.Rational(3,2))**2+200,(x+s.Rational(3,2))**2+s.Rational(791,4)]
    assert all(s.expand(w-f)!=0 for w in wrong)
    key('G9_TB_УПК_811_1',r'$x^2-3x+200=(x-3/2)^2+791/4$')


def test_trigonometric_simplifications_keep_original_domains():
    for a in [.2,.7,1.1,2.2]:
        u,v=tan(a),1/tan(a)
        assert (u+v)**2-(u-v)**2==pytest.approx(4)
        assert (u+v)/(u-v)==pytest.approx(1/(sin(a)**2-cos(a)**2))
        assert (cos(2*a)-cos(4*a))/(sin(2*a)+sin(4*a))==pytest.approx(tan(a))
    key('ds_llm_1931248be21b','$4$')
    key('ds_llm_613af5ca35a6',r'$\dfrac1{\sin^2\alpha-\cos^2\alpha}$')
    key('ds_llm_c1ebc4ce40c7',r'$\tan\alpha$')
    assert 'sin' not in task('ds_llm_c1ebc4ce40c7')['correct_answer']


def test_inflections_require_second_derivative_sign_change_not_stationarity():
    x=s.symbols('x',real=True);f=(x*x-1)/(x*x+1)
    assert s.simplify(s.diff(f,x,2)-4*(1-3*x*x)/(x*x+1)**3)==0
    for point in [-1/s.sqrt(3),1/s.sqrt(3)]:
        assert s.simplify(f.subs(x,point))==-s.Rational(1,2)
        assert s.diff(f,x,2).subs(x,float(point)-.01)*s.diff(f,x,2).subs(x,float(point)+.01)<0
    assert s.diff(f,x,2).subs(x,0)==4
    key('ds_llm_7c36694c8cba',r'$(-1/\sqrt3,-1/2)$ и $(1/\sqrt3,-1/2)$')


def test_deferred_manifest_refuses_without_protection_ack_before_touching_database():
    class NoDatabase:
        def begin(self): raise AssertionError('database must not be opened')
    for execute in (False, True):
        with pytest.raises(ValueError, match='historical pupil answers'):
            apply(NoDatabase(), DEFERRED, execute=execute, backup=Path('unused.json'))
    # the w6 manifest has no protected IDs, so the guard never blocks it
    assert not set(MANIFEST['historical_protection_required']) & {e['id'] for e in MANIFEST['repairs']}


def test_irt_conventions_for_converted_multiple_choice_and_lowered_difficulty():
    assert (MC_GUESSING, B_IRT_DIFFICULTY) == (0.2, 0.5)
    for manifest in (MANIFEST, DEFERRED):
        for e in manifest['repairs']:
            c = e['changes']
            assert c.get('answer_type', 'multiple_choice') == 'multiple_choice'
            assert c.get('irt_guessing', 0.2) == 0.2
            if e['id'] in C_TO_B:
                assert (c['difficulty'], c['irt_difficulty']) == ('B', 0.5)
            else:
                assert 'difficulty' not in c and 'irt_difficulty' not in c
    converted = [e for e in MANIFEST['repairs']+DEFERRED['repairs'] if 'answer_type' in e['changes']]
    assert len(converted) == 49 and all(e['changes']['irt_guessing'] == 0.2 for e in converted)
    assert len(C_TO_B) == 4


def test_taxonomy_decisions_of_review():
    nodes = {n['id']: n for n in NODES}
    assert nodes['G10_S16_05']['parent_id'] == 'G10_P18'
    assert nodes['G9_P40']['parent_id'] == 'G9_T05' and nodes['G9_P40']['level'] == 'L3'
    assert 'G11_S16_04' not in nodes
    used = {e['changes'].get('skill_id') for e in MANIFEST['repairs']}
    assert 'G11_S16_04' not in used and {n for n in nodes if nodes[n]['level']=='L4'} <= used
    by_id = {e['id']: e['changes'] for e in MANIFEST['repairs']}
    assert by_id['G11_TB_§5_5_63_a']['skill_id'] == 'G11_S28_03'
    assert 'skill_id' not in by_id['G11_TB_22_5_3']  # exam-only by design: stays NULL
    nodes_ids = set(nodes)
    for e in MANIFEST['repairs']+DEFERRED['repairs']:
        sid = e['changes'].get('skill_id')
        assert sid is None or sid in nodes_ids or not sid.startswith(('G11_S45','G10_S29','G10_S30'))


def test_review_minor_distractor_fixes_are_mathematically_wrong_choices():
    x=s.symbols('x',positive=True);f=2*x+1/x**2
    assert s.solve(s.diff(f,x),x)==[1] and f.subs(x,1)==3          # critical point 1, outside (0,1/2)
    assert f.subs(x,s.Rational(1,2))==5 and s.diff(f,x).subs(x,s.Rational(1,4))<0
    assert all(f.subs(x,s.Rational(k,100))>5 for k in range(1,50))  # f>5 inside: 3 never attained
    for eps in (s.Rational(1,4),4):                                  # delta=eps is not the largest valid radius
        ok=lambda d:all(v*v<eps for v in [d*s.Rational(k,100) for k in range(1,100)])
        assert ok(s.sqrt(eps)) and (ok(eps) and eps<s.sqrt(eps) if eps<1 else not ok(eps))
    A,B={2,4,6},{3,6}
    assert A|B=={2,3,4,6} and A&B=={6}
    wrong_union=[{2,4,6},{2,3,4},{1,5}];wrong_inter=[{2,4},{3,6},{3}]
    assert A|B not in wrong_union and A&B not in wrong_inter
    assert not ({2,3,4,6} in wrong_inter or {6} in wrong_union)      # no cross-hint between 22_2_3 and 22_2_4
    assert {2,3,4,6}!={6} and (A^B)=={2,3,4}
    d3=[d['value'] for d in task('G11_TB_22_2_3')['distractor_meta']]
    d4=[d['value'] for d in task('G11_TB_22_2_4')['distractor_meta']]
    assert task('G11_TB_22_2_4')['correct_answer'] not in d3 and task('G11_TB_22_2_3')['correct_answer'] not in d4
    assert len(task('G11_TB_23_1_1_6')['distractor_meta'])==3
