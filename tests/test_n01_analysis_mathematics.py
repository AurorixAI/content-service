"""Independent solutions for the 22 wave-five educational contracts.

These are content regressions, not a claim of calibrated diagnostic accuracy.
"""
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction as F
from itertools import permutations, product
import importlib.util
import json
from math import cos, pi, sin
from pathlib import Path
import re

import pytest
import sympy as sp
from sympy.calculus.util import function_range

from tools.content_review.build_n01_analysis_manifest import REPAIRS
from tools.content_review.guarded_repair import validate_choices, validate_entry

ROOT = Path(__file__).parents[1]
MANIFEST = json.loads((ROOT/'data/content_repairs/n01-2026-10-05-w5.json').read_text())


def row(task_id):
    return REPAIRS[task_id]['changes']


def number(value):
    value = value.strip('$ ').replace('{,}', '.')
    value = re.sub(r'\\(?:d?frac)\{?(\d)\}?\{?(\d)\}?',r'\1/\2',value)
    return F(value)


def numeric(task_id, correct, wrong):
    task = row(task_id)
    assert number(task['correct_answer']) == correct
    actual = [number(d['value']) for d in task['distractor_meta']]
    assert actual == wrong
    assert len(set([correct, *actual])) == 4


def four_places(a, b):
    return (Decimal(a)/Decimal(b)).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)


def test_all_eight_ranges_determine_each_boundedness_answer():
    x = sp.Symbol('x', real=True)
    intervals = [sp.Interval(-1,1), sp.Interval(0,sp.sqrt(3)/2),
                 sp.Interval(-sp.sqrt(3)/2,1), sp.Interval(-8,1),
                 sp.Interval.open(-sp.sqrt(2)/2,0),
                 sp.Interval(-sp.sqrt(3)/2,sp.sqrt(3)/2)]
    functions = [sp.sqrt(1-x*x)]*3+[30/sp.sqrt(100-x*x),
                 1/sp.sqrt(1-x*x),1/sp.sqrt(1-x*x)]
    ranges = [function_range(f,x,d) for f,d in zip(functions,intervals)]
    assert ranges == [sp.Interval(0,1), sp.Interval(sp.Rational(1,2),1),
                      sp.Interval(0,1), sp.Interval(3,5),
                      sp.Interval.open(1,sp.sqrt(2)), sp.Interval(1,2)]
    e = sp.log(sp.sqrt(x*x-1),2)
    z = sp.log(sp.sqrt(1-x*x),2)
    assert sp.limit(e,x,1,dir='+') == -sp.oo
    assert sp.limit(e,x,sp.oo) == sp.oo
    assert sp.limit(z,x,1,dir='-') == -sp.oo and z.subs(x,0) == 0
    all_ranges = ranges[:5]+[sp.S.Reals,ranges[5],sp.Interval(-sp.oo,0)]
    predicates = [lambda r:r.inf!=-sp.oo, lambda r:r.sup!=sp.oo,
                  lambda r:r.inf!=-sp.oo and r.sup!=sp.oo]
    for index, predicate in enumerate(predicates,1):
        task = row(f'G11_TB_1_3_1_11_{index}')
        expected = {label for label, r in zip('абвгдежз',all_ranges) if predicate(r)}
        parse = lambda text:set(text.replace(',','').replace(' ',''))
        assert parse(task['correct_answer']) == expected
        assert all(parse(d['value'])!=expected for d in task['distractor_meta'])
        table = task['question_latex'].split(r'\begin{array}{ll}')[1].split(r'\end{array}')[0]
        assert len(table.strip().split(r'\\')) == 8


@pytest.mark.parametrize('index,heads,total', [(1,2048,4040),(2,6019,12000),(3,12012,24000)])
def test_relative_frequency_and_each_wrong_computation(index,heads,total):
    numeric(f'G11_TB_22_3_22_3_{index}', F(four_places(heads,total)),
            [F(four_places(total-heads,total)), F(four_places(total,heads)),
             F(four_places(heads,total*10))])
    assert 0 <= F(heads,total) <= 1
    assert str(heads) in row(f'G11_TB_22_3_22_3_{index}')['question_latex']
    assert str(total) in row(f'G11_TB_22_3_22_3_{index}')['question_latex']


def test_ring_probability_is_area_ratio_in_the_stated_direction():
    k = sp.Symbol('k')
    areas = [(2*(11-i))**2-(2*(10-i))**2 for i in range(1,11)]
    probabilities = [F(a,20**2) for a in areas]
    assert sum(probabilities)==1 and all(p>0 for p in probabilities)
    assert all(a>b for a,b in zip(probabilities,probabilities[1:]))
    task = row('G11_TB_22_4_1')
    texts = [task['correct_answer'], *[d['value'] for d in task['distractor_meta']]]
    def expression(text):
        match = re.fullmatch(r'\$\\dfrac\{([^}]+)\}\{([^}]+)\}\$',text)
        if match:
            return sp.sympify(match[1].replace('k','*k'))/sp.sympify(match[2])
        assert text == r'$\dfrac1{10}$'
        return sp.Rational(1,10)
    actual = [expression(t) for t in texts]
    assert [actual[0].subs(k,i) for i in range(1,11)] == probabilities
    assert all(sp.simplify(a-actual[0])!=0 for a in actual[1:])
    assert 'равномерно по площади' in task['question_latex']


def test_proportional_shoe_plan_keeps_every_count_and_total():
    counts = [2,5,6,12,11,7,4,2,1]
    assert sum(counts)==50
    task = row('G11_TB_23_1_23_1_1')
    parse = lambda t:[number(v) for v in t.strip('$').split(';')]
    plan = [F(1000,50)*c for c in counts]
    assert sum(plan)==1000
    assert [parse(t) for t in task['answer_options']] == [plan,[c*10 for c in counts],list(range(36,45)),counts]
    table = task['question_latex'].split(r'\hline')[1].split(r'\end{array}')[0]
    assert list(map(int,re.findall(r'\d+',table))) == [v for pair in zip(range(36,45),counts) for v in pair]
    assert 'учебном плане' in task['question_latex']


def test_current_is_the_limit_of_charge_difference_quotient():
    t,h = sp.symbols('t h', real=True)
    charge = lambda t:t**3+2*t
    derivative = sp.limit((charge(t+h)-charge(t))/h,h,0)
    assert derivative == sp.diff(charge(t),t) == 3*t*t+2
    assert derivative.subs(t,2)==14 and charge(2)==12 and charge(2)/2==6
    assert sp.limit(charge(2+h)-charge(2),h,0)==0
    assert row('G11_TB_4_1_3')['correct_answer'] == r'$f^{\prime}(t)$'


def test_absolute_value_monotonicity_includes_the_nondifferentiable_corner():
    x = sp.Symbol('x', real=True)
    left,right = x*x+x-1, x*x-x-1
    assert sp.diff(left,x)==2*x+1 and sp.diff(right,x)==2*x-1
    assert [sp.sign(sp.diff(left,x).subs(x,s)) for s in [-1,-sp.Rational(1,4)]] == [-1,1]
    assert [sp.sign(sp.diff(right,x).subs(x,s)) for s in [sp.Rational(1,4),1]] == [-1,1]
    assert sp.diff(left,x).subs(x,0)!=sp.diff(right,x).subs(x,0)
    task = row('G11_TB_5_2_17_2')
    assert task['correct_answer'] == r'$(-1/2;0),\ (1/2;+\infty)$'
    assert 'максимальные открытые' in task['question_latex']


def test_trigonometric_stationary_point_pi_does_not_split_decreasing_interval():
    x = sp.Symbol('x', real=True)
    f = sp.sin(x)+sp.sin(2*x)/2
    derivative = sp.diff(f,x)
    assert sp.trigsimp(derivative-(2*sp.cos(x)-1)*(sp.cos(x)+1))==0
    assert derivative.subs(x,sp.pi)==0
    assert [cos(t)+cos(2*t)>0 for t in [-pi/6,0,pi/6]]==[True]*3
    assert [cos(t)+cos(2*t)<0 for t in [pi/2,pi-.1,pi+.1,3*pi/2]]==[True]*4
    assert row('G11_TB_5_2_17_4')['correct_answer'] == r'$(-\pi/3;\pi/3);\ (\pi/3;5\pi/3)$'


@pytest.mark.parametrize('index,f,points,values,signs', [
    (1,lambda x:sp.Rational(3,4)*x**3+sp.Rational(9,4)*x**2+2,[-2,0],[5,2],[1,-1,1]),
    (2,lambda x:4*x**4-8*x**2+1,[-1,0,1],[-3,1,-3],[-1,1,-1,1]),
])
def test_extrema_tables_have_real_witness_functions(index,f,points,values,signs):
    x = sp.Symbol('x',real=True)
    derivative = sp.diff(f(x),x)
    assert [f(p) for p in points] == values
    assert all(derivative.subs(x,p)==0 for p in points)
    probes = [points[0]-1,*[F(a+b,2) for a,b in zip(points,points[1:])],points[-1]+1]
    assert [int(sp.sign(derivative.subs(x,p))) for p in probes] == signs
    task = row(f'G11_TB_5_2_1_{index}')
    expected_types = ['Максимум','минимум'] if index==1 else ['Минимумы','максимум']
    assert all(kind in task['correct_answer'] for kind in expected_types)
    assert all(f'{p};{v}' in task['correct_answer'] for p,v in zip(points,values))


def test_equal_minimum_values_do_not_force_symmetry():
    base = lambda x:4*x**4-8*x**2+1
    witness = lambda x:base(x)+(x-1)**4 if x>1 else base(x)
    assert [witness(x) for x in [-1,0,1]] == [-3,1,-3]
    assert witness(2)!=witness(-2)
    # Added derivative is positive for x>1 and zero at the join, so all
    # given derivative signs and critical values survive without symmetry.
    assert all(16*x*(x*x-1)+4*(x-1)**3>0 for x in [1.1,2,10])


@pytest.mark.parametrize('index,polynomial,minimum,maximum', [
    (3,lambda t:2*t*t+2*t-1,F(-3,2),3),
    (4,lambda t:t*t-t,F(-1,4),2),
])
def test_trigonometric_ranges_use_interior_vertex_and_both_endpoints(index,polynomial,minimum,maximum):
    t = sp.Symbol('t',real=True)
    critical = sp.solve(sp.diff(polynomial(t),t),t)
    candidates = [polynomial(-1),polynomial(1),*[polynomial(c) for c in critical if -1<=c<=1]]
    assert min(candidates)==minimum and max(candidates)==maximum
    task = row(f'G11_TB_5_3_6_{index}')
    parse = lambda v:[F(n) for n in v.strip('$[]').split(';')]
    assert parse(task['correct_answer']) == [minimum,maximum]
    assert all(parse(d['value'])!=[minimum,maximum] for d in task['distractor_meta'])


def test_lake_length_is_derived_from_both_time_equations():
    a,b,l,s,t,v,v1,v2 = sp.symbols('a b l s t v v1 v2')
    solved = sp.solve([a+b+l-s,a/(v+v1)+l/v+b/(v-v2)-t,
                       a/(v-v1)+l/v+b/(v+v2)-t],(a,b,l))
    expected = (v*v*s-v*(v*v-v1*v2)*t)/(v1*v2)
    assert sp.simplify(solved[l]-expected)==0
    a,b,l,v,v1,v2 = map(F,[288,182,50,10,2,3])
    outbound = a/(v+v1)+l/v+b/(v-v2)
    inbound = a/(v-v1)+l/v+b/(v+v2)
    assert outbound==inbound==55
    assert (v*v*(a+b+l)-v*(v*v-v1*v2)*outbound)/(v1*v2)==50
    assert row('G11_TB_?_265')['correct_answer'] == r'$\dfrac{v^2s-v(v^2-v_1v_2)t}{v_1v_2}$'


def test_first_racing_catches_and_lap_times():
    T = sp.Symbol('T')
    equation = sp.together((4/(3*T)-1/(T+sp.Rational(5,2)))*(T+10)-sp.Rational(2,3))
    assert set(sp.solve(equation,T)) == {-5,20}
    a,b,c = F(1,15),F(1,20),F(2,45)
    assert F(1,3)/(a-b)==20 and F(2,3)/(a-c)==30
    numeric('G11_TB_?_267_а',1/a,[1/b,1/c,F(2,3)/(a-c)])


def test_pedestrian_wait_is_positive_and_all_arrivals_match():
    v = sp.Symbol('v')
    wait = 12/v-sp.Rational(3,2)  # measured in first-meeting times
    gap = sp.Rational(3,2)-v/12
    assert set(sp.solve(gap-2*wait,v)) == {6,48}
    assert wait.subs(v,48)<0 and wait.subs(v,6)>0
    first_meeting, speed, p = F(1),F(6),F(1,2)
    distance = (12+speed)*first_meeting
    runner = first_meeting+p+speed*first_meeting/12
    p1 = distance/speed
    p2 = first_meeting+p+speed*first_meeting/(speed/F(3,2))
    assert distance==18 and runner==2 and p1==p2==3 and p1-runner==2*p
    numeric('G11_TB_?_268_а',speed,[48,F(12)/F(3,2),12])
    assert 'без остановок с постоянной скоростью' in row('G11_TB_?_268_а')['question_latex']


def test_probability_deviation_and_energy_ratio_are_separate_calculations():
    observed,p = F(1310,2500),F(512,1000)
    deviation = abs(observed-p)
    numeric('ds_llm_0a5197c2a03a',deviation,[F(1,100),observed,0])
    log9,log7 = F(48,10)+F(15,10)*9,F(48,10)+F(15,10)*7
    numeric('ds_llm_5b8a471a3d2b',10**(log9-log7),[10**(9-7),log9-log7,F(9,7)])


def test_all_nine_decimal_subtractions_and_exact_borrowing_errors():
    minuends = ['.383','24.20','4.259','11.4','.343','6.36','8.16','67.9','5.36']
    subtrahends = ['.158','10.28','2.264','6.7','.051','4.34','5.82','2.9','1.39']
    results = [F(a)-F(b) for a,b in zip(minuends,subtrahends)]
    wrong1,wrong2,wrong3 = [results.copy() for _ in range(3)]
    wrong1[0]+=F(1,100)
    wrong2[1]=24-10+abs(F('.20')-F('.28'))
    wrong3[2]=4-2+abs(F('.259')-F('.264'))
    task = row('G5_TB_58_1380')
    parse = lambda value:[number(v) for v in value.strip('$').split(';')]
    assert [parse(t) for t in task['answer_options']] == [results,wrong1,wrong2,wrong3]
    cells = task['question_latex'].split(r'\begin{array}{c|l}')[1].split(r'\end{array}')[0].split(r'\\')
    assert len(cells)==9
    assert [list(map(number,c.split('&')[1].split('-'))) for c in cells] == [[F(a),F(b)] for a,b in zip(minuends,subtrahends)]


def test_instrument_language_constraints_have_one_solution_only_when_languages_distinct():
    instruments = ('piano','cello','guitar','violin')
    languages = ('english','french','german','spanish')
    def valid(inst,lang):
        return (all(lang[i]=='spanish' for i in range(4) if inst[i]=='guitar')
                and inst[1] not in ('violin','cello') and lang[1]!='english'
                and inst[0] not in ('violin','cello') and lang[0] not in ('german','english')
                and all(inst[i]!='cello' for i in range(4) if lang[i]=='german')
                and lang[2]=='french' and inst[2]!='violin')
    solutions = [(i,l) for i in permutations(instruments) for l in permutations(languages) if valid(i,l)]
    assert solutions == [(('guitar','piano','cello','violin'),('spanish','german','french','english'))]
    unrestricted = [(i,l) for i in permutations(instruments) for l in product(languages,repeat=4) if valid(i,l)]
    assert len({i for i,_ in unrestricted})>1
    translate = {'Гитара':'guitar','Пианино':'piano','Виолончель':'cello','Скрипка':'violin'}
    task = row('G6_TB_35_1303')
    parse = lambda text:tuple(translate[v.capitalize()] for v in text.split('; '))
    assert parse(task['correct_answer'])==solutions[0][0]
    assert all(not any(valid(parse(d['value']),l) for l in permutations(languages)) for d in task['distractor_meta'])
    assert 'разные языки' in task['question_text']


@pytest.mark.parametrize('task_id', REPAIRS)
def test_full_display_key_option_and_explanation_contract(task_id):
    spec = importlib.util.spec_from_file_location('n01_analysis_katex',ROOT/'scripts/backfill_latex_deepseek.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    task = row(task_id)
    entry = next(e for e in MANIFEST['repairs'] if e['id']==task_id)
    assert all(task[k]==v for k,v in entry['changes'].items())
    validate_entry(entry)
    validate_choices(task)
    texts = [task['question_latex'],task['correct_answer_latex'],*task['answer_options_latex']]
    for d in task['distractor_meta']:
        assert d['value']==d['value_latex']
        assert d['explanation']==d['error_logic']==d['error_logic_latex']==d['explanation_latex']
        texts.extend([d['value_latex'],d['error_logic_latex']])
    for text in texts:
        assert module.validate_with_katex(text)==(True,'')
    assert task['question_text']==task['question_latex']
    assert max(map(len,task['answer_options_latex']))<110
