"""Independent calculations, counterexamples and display contracts for wave 3."""
from fractions import Fraction as F
from functools import reduce
import importlib.util
import json
from math import gcd, lcm
from pathlib import Path

import pytest
import sympy as sp

from tools.content_review.build_n01_integrity_manifest import REPAIRS
from tools.content_review.guarded_repair import validate_choices, validate_entry

ROOT = Path(__file__).parents[1]
MANIFEST = json.loads((ROOT/'data/content_repairs/n01-2026-10-05-w3.json').read_text())


def test_primary_book_arrow_order_closes_cycle_and_all_wrong_traces():
    def trace(multiply=True, subtract=False, addition=False):
        values = [100-79]
        values.append(values[-1]+3 if addition else values[-1]*3 if multiply else F(values[-1],3))
        values.append(values[-1]-27)
        values.append(F(values[-1],4))
        values.append(values[-1]-16 if subtract else values[-1]+16)
        return values,values[-1]*4
    assert trace()==([21,63,36,9,25],100)
    assert trace(addition=True)==([21,24,-3,F(-3,4),F(61,4)],61)
    assert trace(multiply=False)==([21,7,-20,-5,11],44)
    assert trace(subtract=True)==([21,63,36,9,-7],-28)


def test_profit_includes_all_period_costs_and_tax_is_not_net_profit():
    salary = 40-20-5-5
    assert salary==10
    costs=5+F(5+salary,3)
    gross=17-costs; net=gross*F(3,4)
    assert (gross,net,net*3)==(7,F(21,4),F(63,4))
    assert ((17-5),(17-5)*F(3,4),(17-5)*F(3,4)*3)==(12,9,27)
    assert (17,17*F(3,4),17*F(3,4)*3)==(17,F(51,4),F(153,4))
    assert (gross,gross*F(1,4),gross*F(1,4)*3)==(7,F(7,4),F(21,4))


def test_function_is_total_single_valued_and_does_not_require_identity_or_injectivity():
    relations=[[(10,100),(50,500)],[(3,F(3,10)),(3,F(35,100))],
               [(10,100),(10,50)],[(3,F(3,10)),(F(7,2),F(35,100))],[(500000,450000)]]
    def functional(pairs):
        return all(len({y for x,y in pairs if x==entry})==1 for entry in {x for x,y in pairs})
    assert [i+1 for i,r in enumerate(relations) if functional(r)]==[1,4,5]
    assert functional([(0,1),(1,1)])  # Constant function is not injective.
    assert functional([(500000,450000)])  # A function need not be identity.
    assert not functional([(0,1),(0,2)])
    # "At most one" alone permits a missing output at an element of X.
    domain={0,1}; partial=[(0,2)]
    assert functional(partial) and set(x for x,y in partial)!=domain


def test_recipe_used_fractions_whole_packages_and_rounding_are_distinct():
    rows=[(275,1000,80),(105,250,156),(45,1000,120),(20,1000,53),
          (15,500,45),(15,12,17),(350,1000,47),(700,1000,450),
          (130,1000,30),(10,25,40)]
    cost=sum(F(used,size)*price for used,size,price in rows)
    whole=sum(((used+size-1)//size)*price for used,size,price in rows)
    assert cost==F(46793,100) and whole==1055
    assert round(1500-cost)==1032 and round(cost)==468 and 1500-whole==445


def test_poles_enumerated_and_all_color_counts_for_robots_partition_exactly():
    old=set(range(0,11001,45)); positions=set(range(0,11001,60))
    assert len(positions)==184 and len(positions&old)==62 and len(positions-old)==122
    assert max(positions)==10980
    assert 0 in old&positions and len((positions&old)-{0})==61
    counts=[144,180,252]
    feasible=[n for n in range(1,577) if all(c%n==0 and (c//n)%3==0 and (c//n)%4==0 for c in counts)]
    assert feasible==[1,3]
    assert [c//max(feasible) for c in counts]==[48,60,84]
    assert sum(counts)//max(feasible)==192
    assert reduce(gcd,counts)==36 and sum(c//36 for c in counts)==16


def test_runners_and_lights_periods_fractions_and_excluded_initial_flash():
    meet=next(t for t in range(1,1000) if all(t%period==0 for period in [45,60,75]))
    speed=sum(F(1,period) for period in [45,60,75])
    assert meet==900 and F(meet,60)==15 and speed==F(47,900)
    assert speed*60==F(47,15) and gcd(47,900)==1
    flashes=[t for t in range(1,3601) if all(t%period==0 for period in [12,18,30])]
    assert len(flashes)==20 and flashes[0]==180 and flashes[-1]==3600
    periods=[F(p,3600) for p in [12,18,30]]
    assert periods==[F(1,300),F(1,200),F(1,120)]
    assert lcm(*(p.denominator for p in periods))==600
    assert all(3600%p.denominator==0 for p in periods)  # Common, not least.


def test_balloons_maximal_identical_sets_and_geometry_actual_wrong_results():
    numbers=[204,255,221]
    sets=max(n for n in range(1,681) if all(x%n==0 for x in numbers))
    assert sets==17 and [x//sets for x in numbers]==[12,15,13]
    assert sum(numbers)==680 and sum(x//sets for x in numbers)==40
    sphere=4*3*5**2; cut=3*5**2; both=sphere+2*cut; disk=2*cut
    assert (sphere,cut,both,disk,both-disk)==(300,75,450,150,300)
    assert sphere-disk==150 and sphere//2+cut==225 and both-cut==375
    circumference=2*3*6; area=3*6**2; distance=5*circumference
    assert F(distance,area)==F(5,3)
    assert F(area,distance)==F(3,5) and F(circumference,area)==F(1,3) and F(distance,area//2)==F(10,3)


def test_reservoir_shortfall_and_climb_with_pause():
    assert 3*2-F(25,8)==F(23,8)
    assert 5-F(25,8)==F(15,8) and 6+F(25,8)==F(73,8)
    speed=F(1000-400,11-8)
    height=400
    for hour in range(8,14): height+=0 if hour==11 else speed
    assert speed==200 and height==1400
    assert 400+speed*6==1600 and 1000+speed*2*2==1800


def test_cooling_coefficients_from_the_original_model_and_wrong_substitutions():
    k=sp.Symbol('k')
    old=sp.solve(sp.Eq(76,20+(90-20)*(1-k*5)),k)[0]
    new=sp.solve(sp.Eq(58,10+(90-10)*(1-k*5)),k)[0]
    assert old==sp.Rational(1,25) and new==sp.Rational(2,25) and new/old==2
    assert old/new==sp.Rational(1,2)
    assert (sp.Rational(90-58,(90-20)*5))/old==sp.Rational(16,7)
    assert (sp.Rational(90-58,90-10))/old==10


def test_rounding_and_schedule_greatest_block_first_repeat():
    exact=5*38+4*43; estimated=5*40+4*40
    assert exact==362 and estimated==360
    assert round(exact,-2)==round(estimated,-2)==400
    assert abs(round(exact,-1)-round(estimated,-2))==40
    assert abs(400-round(5*30+4*40,-2))==100 and abs(exact-estimated)==2
    assert max(n for n in range(1,49) if 36%n==0 and 48%n==0)==12
    assert next(n for n in range(1,145) if n%36==0 and n%48==0)==144
    assert 84%36!=0 and 84%48!=0


def test_filter_conserves_its_flow_and_bracelets_have_a_feasible_integer_allocation():
    leak=F(18,6); filter_flow=leak/3
    assert -leak-filter_flow+filter_flow==-3
    assert filter_flow==1 and leak*3==9
    assert 28%3!=0  # Original equal teams impossible.
    teams=[9,9,10]; remaining=[size-2 for size in teams]
    assert sum(teams)==28 and sum(remaining)==22 and sum(remaining)==2*11
    assert sum(remaining)+3*2+5==33
    assert 22+6==28 and 22+5==27 and 22+5+6+6==39


def test_scores_sales_and_tourists_recomputed_with_all_exceptions():
    scores=[45,35,50,30,40]
    transformed=[(s if s==50 else s*F(9,10))+5 for s in scores]
    assert transformed==[F(91,2),F(73,2),55,32,41] and sum(transformed)/5==42
    assert (sum(scores)*F(9,10)+25)/5==41
    assert (150*F(11,10)+50+25)/5==48 and (150*F(9,10)+50)/5==37
    june=[120,150,90]; july=[june[0]*F(6,5),june[1]*F(9,10),june[2]*F(13,10)]
    assert july==[144,135,117] and sum(june)==360 and sum(july)==396
    assert sum((a+b)/2 for a,b in zip(june,july))==378
    path=5*2+4*2; outward_average=F(path,5); returning=outward_average/2
    assert path-returning==F(81,5)
    assert path-F(path,4)/2==F(63,4)
    assert path+returning==F(99,5) and path-outward_average==F(72,5)


@pytest.mark.parametrize('task_id',REPAIRS)
def test_all_display_fields_katex_and_explanation_mirrors(task_id):
    spec=importlib.util.spec_from_file_location('n01_integrity_latex_validator',ROOT/'scripts/backfill_latex_deepseek.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    row=REPAIRS[task_id]['changes']
    entry=next(e for e in MANIFEST['repairs'] if e['id']==task_id)
    assert all(row[k]==v for k,v in entry['changes'].items())
    validate_entry(entry);validate_choices(row)
    texts=[row['question_latex'],row['correct_answer_latex'],*row['answer_options_latex']]
    for d in row['distractor_meta']:
        assert d['explanation']==d['error_logic'] and d['explanation_latex']==d['error_logic_latex']
        texts.extend([d['value_latex'],d['error_logic_latex']])
    for value in texts: assert module.validate_with_katex(value)==(True,'')
    assert max(map(len,row['answer_options_latex']))<180
