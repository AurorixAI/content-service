"""Independent solutions and counterexamples for all 40 wave-four contracts."""
from collections import Counter
from fractions import Fraction as F
import importlib.util
import json
from math import ceil
from pathlib import Path
import re

import pytest
import sympy as sp

from tools.content_review.build_n01_compact_manifest import REPAIRS
from tools.content_review.guarded_repair import validate_choices, validate_entry

ROOT = Path(__file__).parents[1]
MANIFEST = json.loads((ROOT/'data/content_repairs/n01-2026-10-05-w4.json').read_text())


def row(task_id):
    return REPAIRS[task_id]['changes']


def number(text):
    value = text.strip('$ ').replace(r'\,', '').replace('{,}', '.')
    mixed = re.fullmatch(r'(\d+)\\dfrac(\d)(\d)', value)
    if mixed:
        return F(int(mixed[1])) + F(int(mixed[2]), int(mixed[3]))
    value = re.sub(r'\\(?:d?frac)\{?(\d+)\}?\{?(\d+)\}?', r'\1/\2', value)
    return F(value)


def verify_numeric(task_id, correct, wrong):
    task = row(task_id)
    assert number(task['correct_answer']) == correct
    actual = [number(d['value']) for d in task['distractor_meta']]
    assert actual == wrong
    assert correct not in wrong and len(set([correct, *wrong])) == 4


def test_budget_expression_and_feasible_purchase():
    m = sp.Symbol('m')
    change = sp.expand(5000 - (12*m + 10*(m-120)))
    assert change == 6200-22*m
    assert change.subs(m, 200) == 1800 and change.subs(m, 250) == 700
    task = row('DIFF_G5_S07_01_C_02')
    assert task['correct_answer'] == '$6200-22m$'
    assert [d['value'] for d in task['distractor_meta']] == ['$5000-22m$', '$3800-22m$', '$6200-2m$']
    assert 'm>120' in task['question_latex'] and 'денег хватает' in task['question_latex']


def test_trees_last_return_is_explicit_and_changes_valid_answer():
    distances = list(range(8, 73, 8))
    full = sum(2*d for d in distances)
    verify_numeric('DIFF_G5_S09_01_C_01', full, [sum(distances), full-72, sum(2*d for d in distances[:-1])])
    assert full == 720 and 'в том числе после последнего' in row('DIFF_G5_S09_01_C_01')['question_latex']


def test_dog_and_fly_use_meeting_time_not_number_of_turns():
    meeting = F(30, 6+4)
    verify_numeric('DIFF_G5_S44_01_C_03', 12*(meeting-F(2,60)), [12*meeting, 35, 12*F(15,6)])
    meeting = F(120,40+50)
    verify_numeric('DIFF_G5_S44_02_C_03', 80*meeting, [120, 80, F(120,100)*80])


def test_volume_and_kinetic_energy_scaling():
    volume = lambda h: h*(h+2)*3*(h+2)
    difference = volume(4)-volume(3)
    verify_numeric('DIFF_G7_S03_01_C_01', difference, [volume(4), volume(3), difference*10])
    kinetic = 300-4*10*5
    height = F(300-F(kinetic,4), 4*10)
    verify_numeric('DIFF_G7_S03_01_C_03', height, [F(300-F(kinetic,2),40), 5, F(300,40)])
    assert height == F(55,8)


def test_confetti_transfer_conserves_only_the_first_two_boxes():
    first_two = F(1487+2543,100)
    total = F(1487+2543+1857,100)
    tasting = F(487,100)
    verify_numeric('DIFF_G7_S05_02_C_01', first_two, [first_two-tasting, total, total-tasting])


def test_primary_cycle_a_each_wrong_step_and_all_following_values():
    def trace(add=9, divide=3, subtract=15):
        values = [F(60+add)]
        values.append(values[-1]/divide)
        values.append(values[-1]-subtract)
        values.append(values[-1]*12)
        values.append(values[-1]/2)
        return values, values[-1]+12
    expected = [trace(), trace(divide=23), trace(subtract=5), trace(add=19)]
    assert expected[0] == ([69,23,8,96,48],60)
    assert [v[1] for v in expected[1:]] == [-60,120,80]
    task = row('G5_TB_11_438.1')
    for text, (values, _) in zip(task['answer_options'], expected):
        assert [number(v.replace(r'\ ','')) for v in text.strip('$').split(';')] == values


def test_sales_division_and_formula_truth_values():
    revenues = [336000,112000,180000,30000]
    prices = [24000,16000,18000,3000]
    counts = [F(r,p) for r,p in zip(revenues,prices)]
    task = row('G5_TB_30_502')
    parsed = [[number(v.replace(r'\ ','')) for v in t.strip('$').split(';')] for t in task['answer_options']]
    assert parsed == [counts, counts[:-1]+[1], [n*10 for n in counts], [counts[1],counts[0],*counts[2:]]]
    assert counts == [14,7,10,10]
    # Units/definitions: speed is distance divided by time, not their product.
    a,b,s,t,p,n,W = 2,3,20,4,7,3,40
    facts = [a*b==6, s*t==s/t, p*n==21, F(p*n,p)==n, F(W,t)==10]
    assert facts == [True,False,True,True,True]
    assert row('G5_TB_30_503')['correct_answer'] == r'$+;\ -;\ +;\ +;\ +$'
    assert row('G5_TB_35_615')['correct_answer'] == 'Развёрнутый'
    assert 180 != 90 and not 0 < 180 < 90 and not 90 < 180 < 180


def test_stock_correction_mean_and_weighted_speed():
    opening = 1160980+2070600
    arrivals = 4640260+6235900
    sales = 3824150+6136480
    verify_numeric('G5_TB_38_1521', opening+arrivals-sales, [opening+arrivals, opening, 1160980+4640260-3824150])
    corrected_mean = F(25*130-145+120,25)
    verify_numeric('G5_TB_68_1672', corrected_mean, [130,130-(145-120),130+F(145-120,25)])
    v1,v2 = F(4*60,9), F(3*60,6)
    verify_numeric('G5_TB_68_1675', F((4+3)*60,9+6), [(v1+v2)/2,v1,v2])


def test_payback_rounding_is_to_tenths_not_whole_years():
    def payback(saving): return round(F(2500000,3500000)*F(1,F(42,100)*saving),1)
    verify_numeric('G5_TB_69_1681', payback(F(1,5)), [payback(1),payback(F(1,10)),payback(F(42,100))])
    assert payback(F(42,100)) == 4 and 'до десятых' in row('G5_TB_69_1681')['question_latex']


@pytest.mark.parametrize('source,matrix,selected_row,month', [
    ('198',[[15678,14791,15949],[29105,28016,29991],[14528,13752,14710]],1,1),
    ('85',[[1576400,1465400,1798500],[2951500,2871400,2764800],[1479500,1332100,1574800]],2,2),
])
def test_furniture_all_cells_preserved_and_every_incomplete_sum(source,matrix,selected_row,month):
    chosen = matrix[selected_row]
    column = [r[month] for r in matrix]
    all_cells = [v for r in matrix for v in r]
    verify_numeric(f'G5_TB_6_{source}.1', sum(chosen), [sum(chosen[:2]),sum(chosen[1:]),chosen[0]+chosen[2]])
    omitted = [2,1,0]
    verify_numeric(f'G5_TB_6_{source}.2', sum(column), [sum(column)-column[i] for i in omitted])
    verify_numeric(f'G5_TB_6_{source}.3', sum(all_cells), [sum(r[0] for r in matrix),sum(matrix[1]),sum(sum(r[:2]) for r in matrix)])
    for i in [1,2,3]:
        question = row(f'G5_TB_6_{source}.{i}')['question_latex']
        data = question.split(r'\hline',1)[1].split(r'\end{array}',1)[0]
        assert list(map(int,re.findall(r'\d+',data))) == all_cells


def test_train_duration_and_same_day_stop_order():
    departures = [(6,40),(7,0),(7,0),(8,0)]
    arrivals = [(12,40),(10,20),(9,8),(11,47)]
    duration = [(ah*60+am)-(dh*60+dm) for (dh,dm),(ah,am) in zip(departures,arrivals)]
    assert duration == [360,200,128,227]
    names = ['Андижан','Карши','Самарканд','Бухара']
    assert row('G6_TB_124–125_1046.1')['correct_answer'] == names[duration.index(max(duration))]+'; '+names[duration.index(min(duration))]
    assert 9*60+8 < 10*60+20
    assert row('G6_TB_124–125_1046.3')['correct_answer'] == 'Самарканд'
    assert 'одного рейса' in row('G6_TB_124–125_1046.3')['question_latex']


def test_work_table_totals_and_extrema_preserve_original_data():
    data = [[22,30,15,28],[14,17,20,19],[25,32,21,18],[9,7,12,16],[15,11,23,14]]
    verify_numeric('G6_TB_124–125_1047.2', sum(data[1]), [sum(data[2]),data[1][0],data[1][-1]])
    columns = [sum(r[i] for r in data) for i in range(4)]
    assert columns == [85,97,91,95]
    names = ['Сентябрь','Октябрь','Ноябрь','Декабрь']
    assert row('G6_TB_124–125_1047.5')['correct_answer'] == names[columns.index(max(columns))]+'; '+names[columns.index(min(columns))]


@pytest.mark.parametrize('section,matches,queries', [
    ('1048', [[(3,3),(1,2)],[(3,3),(5,5)],[(2,1),(5,5)]],[(0,max),(0,min),(1,max),(1,min),(2,max),(2,min)]),
    ('1051', [[(2,3),(1,2),(0,0),(2,1)],[(3,2),(5,0),(0,1),(4,2)],[(2,1),(0,5),(1,1),(2,0)],[(0,0),(1,0),(1,1),(2,2)],[(1,2),(2,4),(0,2),(2,2)]],[(0,max),(0,min),(1,max),(2,max)]),
])
def test_football_from_match_scores_tied_extrema_are_complete(section,matches,queries):
    statistics = [[sum(ours>theirs for ours,theirs in games),sum(ours==theirs for ours,theirs in games),sum(ours for ours,_ in games)] for games in matches]
    for index,(column,extremum) in enumerate(queries,1):
        target = extremum(stats[column] for stats in statistics)
        winners = {i for i,stats in enumerate(statistics) if stats[column]==target}
        task = row(f'G6_TB_124–125_{section}.{index}')
        def members(text):
            if text=='Поровну у всех': return set(range(len(matches)))
            return {'АБВГД'.index(n) for n in re.findall(r'«([АБВГД])»',text)}
        assert members(task['correct_answer']) == winners
        assert all(members(d['value']) != winners for d in task['distractor_meta'])
        displayed = task['question_latex'].split(r'\hline',1)[1].split(r'\end{array}',1)[0]
        displayed = re.sub(r'\\text\{[^}]+\}', '', displayed)
        assert list(map(int,re.findall(r'\d+',displayed))) == [stats[column] for stats in statistics]


def test_cafe_counts_all_50_observations_and_wrong_denominators():
    observations = [20,27,23,27,26,18,22,25,26,23,23,25,28,26,23,22,21,19,21,29,30,27,26,30,29,22,18,29,22,26,28,27,29,27,22,29,26,27,21,19,25,29,29,21,18,26,20,24,19,27]
    counts = Counter(observations)
    assert len(observations)==50 and (counts[22],counts[26],counts[24])==(5,7,1)
    verify_numeric('G9_TB_37_483_1.1', counts[22], [4,6,F(counts[22],50)])
    verify_numeric('G9_TB_37_483_1.2', F(counts[26],50), [counts[26],F(counts[26],100),F(counts[26],10)])
    verify_numeric('G9_TB_37_483_1.3', F(counts[24],50), [counts[24],F(counts[24],100),F(counts[24],5)])
    for index in [1,2,3]:
        grid = row(f'G9_TB_37_483_1.{index}')['question_latex'].split(r'\begin{array}{rrrrr}')[1].split(r'\end{array}')[0]
        assert list(map(int,re.findall(r'\d+',grid)))==observations
        assert len(grid.split(r'\\')) == 10


def test_tariff_full_cost_and_minimum_complete_saving_month():
    minutes,internet=2500,35
    bills=[1500+max(0,minutes-2000)*F(7,2),2000+max(0,minutes-3000)*F(3,2)+max(0,internet-10)*40,3000+max(0,internet-30)*30]
    assert bills == [3250,3000,3150]
    assert row('G9_TB_5_2')['correct_answer'] == 'Тариф «2000»'
    saving=36000+48000-sum([30000,11600,2000,700,6400,10000])
    months=ceil(F(500000,saving))
    assert (months-1)*saving < 500000 <= months*saving
    verify_numeric('G9_TB_5_67', months, [500000//saving,ceil(F(500000,48000)),ceil(F(500000,saving+10000))])


@pytest.mark.parametrize('task_id', REPAIRS)
def test_reviewed_latex_contract_and_all_explanation_mirrors(task_id):
    spec = importlib.util.spec_from_file_location('n01_compact_katex', ROOT/'scripts/backfill_latex_deepseek.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    task = row(task_id)
    entry = next(e for e in MANIFEST['repairs'] if e['id']==task_id)
    assert all(task[k]==v for k,v in entry['changes'].items())
    validate_entry(entry); validate_choices(task)
    texts=[task['question_latex'], task['correct_answer_latex'], *task['answer_options_latex']]
    for distractor in task['distractor_meta']:
        assert distractor['value']==distractor['value_latex']
        assert distractor['explanation']==distractor['error_logic']==distractor['error_logic_latex']==distractor['explanation_latex']
        texts.extend([distractor['value_latex'],distractor['error_logic_latex']])
    for text in texts: assert module.validate_with_katex(text)==(True,'')
    assert task['question_text']==task['question_latex']
    assert max(map(len,task['answer_options_latex'])) < 85
