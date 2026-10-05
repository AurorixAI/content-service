"""Independent solutions for the six source findings, without LLM calls."""
import importlib.util
import json
import math
from pathlib import Path

import pytest
import sympy as sp

from tools.content_review.build_n01_manifest import REPAIRS
from tools.content_review.guarded_repair import validate_choices, validate_entry

ROOT = Path(__file__).parents[1]
MANIFEST = json.loads((ROOT / "data/content_repairs/n01-2026-10-05-w1.json").read_text())


def fields(task_id):
    return REPAIRS[task_id]["changes"]


def test_vat_is_tax_on_each_traders_added_value_not_the_discount():
    price = sp.Integer(12_000_000)
    wholesale_buy = price * sp.Rational(70, 100)
    retail_buy = price * sp.Rational(80, 100)
    vat = [(retail_buy - wholesale_buy) / 10, (price - retail_buy) / 10]
    assert vat == [120_000, 240_000]
    assert fields("G10_TB_3_9_9")["correct_answer"] == r"$120\,000;\ 240\,000$"
    assert fields("G10_TB_3_9_9")["skill_id"] == "G5_S46_02"
    assert price * sp.Rational(30, 100) / 10 == 360_000  # wrong mechanism


def test_inscribed_square_probability_and_all_wrong_choices():
    r = sp.Symbol("r", positive=True)
    # Pythagoras: diagonal² = 2 side² = (2r)².
    square_area = (2 * r) ** 2 / 2
    probability = sp.simplify(square_area / (sp.pi * r**2))
    assert probability == 2 / sp.pi
    assert 0 < float(probability) < 1
    assert all(sp.simplify(value - probability) != 0
               for value in (1 / sp.pi, 4 / sp.pi, sp.pi / 4))
    row = fields("G10_TB_6_2_16")
    assert row["correct_answer"] == r"$\dfrac{2}{\pi}$"
    assert "равномерно" in row["question_latex"] and "вписан" in row["question_latex"]


def test_open_range_requires_excluding_zero_and_reaches_every_interior_value():
    x, y = sp.symbols("x y", real=True)
    f = 1 + 1 / (1 + x**2)
    assert f.subs(x, 0) == 2  # regression: old key includes the wrong endpoint
    # For any 1<y<2, this x is real and nonzero and f(x)=y.
    inverse = sp.sqrt(1 / (y - 1) - 1)
    assert sp.simplify(f.subs(x, inverse) - y) == 0
    for value in [sp.Rational(101, 100), sp.Rational(3, 2), sp.Rational(199, 100)]:
        point = inverse.subs(y, value)
        assert point.is_real and point != 0
    assert r"\setminus\{0\}" in fields("G10_TB_§42_42_7_3")["correct_answer"]


def test_complementary_events_are_exhaustive_disjoint_and_not_independent():
    universe = {"good-1", "good-2", "bad-1"}
    good, bad = {"good-1", "good-2"}, {"bad-1"}
    assert good | bad == universe and not good & bad
    assert bad == universe - good and good != bad
    assert sp.Rational(len(good), len(universe)) * sp.Rational(len(bad), len(universe)) > 0
    assert fields("G10_TB_6_1_1")["correct_answer"] == "Противоположные"
    assert fields("G10_TB_6_1_1")["skill_id"] == "G10_S27_02"


def test_reflection_then_vertical_shift_and_horizontal_distractor():
    # Reflect the actual domain [0,+∞) as well as values.
    for original_x in [0, 1, 16, 81]:
        reflected_x = -original_x
        expected_y = original_x ** 0.25 + 1
        assert (-reflected_x) ** 0.25 + 1 == expected_y
    assert fields("G10_TB_1_6_7_g")["correct_answer"] == r"$\sqrt[4]{-x} + 1$"
    # g(x-1), evaluated at x=-15, equals2; g(x)+1 is different.
    assert (1 - (-15)) ** 0.25 == 2
    assert (-(-15)) ** 0.25 + 1 != 2


def test_trapezoid_and_rectangle_sums_on_the_exact_requested_grid():
    n = 20
    step = math.pi / 20
    samples = [math.sin(-math.pi / 2 + i * step) for i in range(n + 1)]
    left, right = step * sum(samples[:-1]), step * sum(samples[1:])
    trapezoid = step * (samples[0] / 2 + sum(samples[1:-1]) + samples[-1] / 2)
    assert trapezoid == pytest.approx(0, abs=1e-14)
    assert left == pytest.approx(-math.pi / 20)
    assert right == pytest.approx(math.pi / 20)
    x = sp.Symbol("x", real=True)
    assert sp.integrate(sp.sin(x), (x, -sp.pi / 2, sp.pi / 2)) == 0
    assert 2 * sp.integrate(sp.sin(x), (x, 0, sp.pi / 2)) == 2
    assert fields("G11_TB_6_6_6_43_c")["skill_id"] == "G11_S39_02"
    assert fields("G11_TB_6_6_6_43_c")["correct_answer"] == "$0$"


@pytest.mark.parametrize("task_id", REPAIRS)
def test_all_corrected_layers_render_and_choices_have_consistent_explanations(task_id):
    spec = importlib.util.spec_from_file_location("n01_latex_validator", ROOT / "scripts/backfill_latex_deepseek.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    row = fields(task_id)
    validate_choices(row)
    entry = next(e for e in MANIFEST["repairs"] if e["id"] == task_id)
    # Test the artifact which will be applied, as well as its authoring source.
    assert all(row[key] == value for key, value in entry["changes"].items())
    validate_entry(entry)
    texts = [row["question_latex"], row["correct_answer_latex"], *row["answer_options_latex"]]
    for distractor in row["distractor_meta"]:
        assert distractor["error_logic"] == distractor["explanation"]
        assert distractor["error_logic_latex"] == distractor["explanation_latex"]
        texts.extend([distractor["value_latex"], distractor["error_logic_latex"]])
    for value in texts:
        assert module.validate_with_katex(value) == (True, "")
