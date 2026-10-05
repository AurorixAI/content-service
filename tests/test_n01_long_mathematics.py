"""Independent solutions and counterexamples for the second content wave."""
import importlib.util
import json
from pathlib import Path

import pytest
import sympy as sp

from tools.content_review.build_n01_long_manifest import REPAIRS
from tools.content_review.guarded_repair import validate_choices, validate_entry

ROOT=Path(__file__).parents[1]
MANIFEST=json.loads((ROOT/'data/content_repairs/n01-2026-10-05-w2.json').read_text())


def test_train_duration_and_all_authored_wrong_choices():
    assert (9*60+8)-7*60 == 128 == 2*60+8
    assert (10*60+20)-7*60 == 3*60+20  # wrong row: Karshi
    assert all(v !=128 for v in [60+8,120,3*60+20])


def test_table_rows_columns_and_individual_cells_all_give_the_same_total():
    data=sp.Matrix([[22,30,15,28],[14,17,20,19],[25,32,21,18],[9,7,12,16],[15,11,23,14]])
    columns=[sum(data[:,i]) for i in range(4)]
    assert columns==[85,97,91,95]
    assert sum(data)==sum(columns)==368
    assert [sum(data[i,:]) for i in range(5)]==[95,70,96,44,63]
    assert sum(columns[:3])==273 and sum(columns)+368==736 and sum(data[0,:])==95


def test_continuity_increment_condition_and_counterexamples():
    h,x=sp.symbols('h x',real=True)
    for f in [sp.Integer(1),x,x**2,sp.sin(x)]:
        assert sp.limit(f.subs(x,2+h)-f.subs(x,2),h,0)==0
    # Local constancy is not necessary: f(x)=x has increment h, not zero.
    assert (x.subs(x,2+h)-x.subs(x,2))==h
    # h→0 is automatic; it cannot rule out a jump in f.
    assert sp.limit(h,h,0)==0
    n=sp.Symbol('n',positive=True,integer=True)
    jump=sp.Piecewise((1,h>0),(0,True))
    assert sp.limit(1/n,n,sp.oo)==0 and jump.subs(h,1/n)==1


def test_five_original_equations_without_the_imported_solutions():
    x,t=sp.symbols('x t',real=True)
    roots=sp.solve(x**2-6*x+8,x)
    assert roots==[2,4]
    assert [r for r in roots if (r**2-4*r+3)>0]==[4]
    assert sp.solve(t**2-2*t,t)==[0,2]
    assert [2**r for r in [0,2] if 2**r !=1]==[4]
    assert sp.solve(x**2-2*x-3,x)==[-1,3]
    assert [r for r in [-1,3] if r>0]==[3]
    roots=sp.solve(x**2-6*x+6,x)
    assert roots==[3-sp.sqrt(3),3+sp.sqrt(3)]
    assert [r for r in roots if r>sp.Rational(5,2)]==[3+sp.sqrt(3)]
    assert (2*3-5)!=(3**2-4*3+1)  # authored 3 is wrong
    # For cos(x)≠0, the left side reduces to sin(2x), whose only
    # possible values in s=s² are 0 and1. Check both full series.
    assert sp.solve(t-t**2,t)==[0,1]
    for k in range(-6,7):
        for point in [sp.pi*k,sp.pi/4+sp.pi*k]:
            assert sp.cos(point)!=0
            left=2*sp.tan(point)/(1+sp.tan(point)**2)
            assert sp.simplify(left-sp.sin(2*point)**2)==0
        assert sp.cos(sp.pi/2+sp.pi*k)==0
    assert sp.simplify(sp.sin(2*(5*sp.pi/4)))==1  # doubled period misses it


def test_fibonacci_both_induction_steps_and_wrong_indices():
    u=[0,1,1]
    for k in range(2,44): u.append(u[-1]+u[-2])
    for n in range(1,21):
        odd=sum(u[1:2*n:2])
        assert odd==u[2*n]
        assert odd+u[2*n+1]==u[2*n+2]
        assert all(wrong!=u[2*n+2] for wrong in [u[2*n+3],u[2*n+1],2*u[2*n+1]])
        squares=sum(v*v for v in u[1:n+1])
        assert squares==u[n]*u[n+1]
        assert squares+u[n+1]**2==u[n+1]*u[n+2]
        assert all(wrong!=u[n+1]*u[n+2] for wrong in [u[n+1]*u[n+3],u[n+2]**2,u[n]*u[n+1]])


def sequential(values):
    value=values[0]+values[1]
    for index in range(2,len(values)):
        value=value*values[index] if index%2==0 else value+values[index]
    return value


def test_original_swap_question_is_underdetermined_and_new_paired_sums_are_invariant():
    first=[2019]+[1]*9
    second=[1009,1,2]+[1]*7
    swap=lambda values:[x for i in range(0,10,2) for x in (values[i+1],values[i])]
    assert sequential(first)==sequential(second)==2024
    assert sequential(swap(first))==2024 and sequential(swap(second))==1015
    a=sp.symbols('a1:11')
    product=sp.prod(a[i]+a[i+1] for i in range(0,10,2))
    swapped=sp.prod(a[i+1]+a[i] for i in range(0,10,2))
    assert sp.expand(product-swapped)==0


@pytest.mark.parametrize('task_id',REPAIRS)
def test_second_wave_all_display_fields_and_explanation_mirrors(task_id):
    spec=importlib.util.spec_from_file_location('n01_long_latex_validator',ROOT/'scripts/backfill_latex_deepseek.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    row=REPAIRS[task_id]['changes']
    entry=next(e for e in MANIFEST['repairs'] if e['id']==task_id)
    assert all(row[k]==v for k,v in entry['changes'].items())
    validate_entry(entry);validate_choices(row)
    texts=[row['question_latex'],row['correct_answer_latex'],*row['answer_options_latex']]
    for d in row['distractor_meta']:
        assert d['explanation']==d['error_logic']
        assert d['explanation_latex']==d['error_logic_latex']
        texts.extend([d['value_latex'],d['error_logic_latex']])
    for value in texts: assert module.validate_with_katex(value)==(True,'')
    assert max(map(len,row['answer_options_latex']))<180
