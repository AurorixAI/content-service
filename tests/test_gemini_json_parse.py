"""B11 — разбор ответа модели: команда LaTeX против JSON-escape.

Шов, на котором рождается порча формул. До этих тестов покрытия у него не было.

Корень дефекта: `\f`, `\b`, `\n`, `\r`, `\t` — валидные JSON-escape, поэтому
`{"latex": "\frac{1}{2}"}` — синтаксически корректный JSON, который молча даёт
form feed + "rac". Формула после этого компилируется KaTeX без ошибки и
показывает ученику мусор, а `compile_rate` остаётся 1.0.
"""
import json

import pytest

from src.pipeline.gemini_client import parse_json_response

# Команды, которые начинаются с буквы валидного JSON-escape. Каждая — реальный
# класс порчи, замеренный на выгрузке прототипа (6 книг, 10 769 формул).
LATEX_ESCAPE_COLLISIONS = [
    (r"\frac{1}{2}", "form feed"),
    (r"\begin{cases}", "backspace"),
    (r"\text{ cm}", "tab"),
    (r"\times", "tab"),
    (r"\theta", "tab"),
    (r"\to", "tab"),
    (r"\neq", "newline"),
    (r"\nabla", "newline"),
    (r"\right)", "carriage return"),
    (r"\rho", "carriage return"),
]

LATEX_CORPUS = [c for c, _ in LATEX_ESCAPE_COLLISIONS] + [
    r"\left(\frac{14\pi}{3}\right)",
    r"150^\circ",
    r"x \cdot y",
    r"\sqrt{2}",
    r"\alpha + \beta",
    r"\frac{a}{b} = \frac{c}{d}",
    r"\text{см}^2",
    r"\begin{cases} x > 0 \\ y < 5 \end{cases}",
]


@pytest.mark.parametrize("latex,control_char", LATEX_ESCAPE_COLLISIONS)
def test_latex_command_not_eaten_as_escape(latex, control_char):
    """Модель прислала сырой обратный слэш — команда должна уцелеть."""
    got = parse_json_response('{"latex": "%s"}' % latex)["latex"]
    assert got == latex, f"{latex} съеден как {control_char}: {got!r}"


@pytest.mark.parametrize("latex,_", LATEX_ESCAPE_COLLISIONS)
def test_no_control_characters_leak_into_output(latex, _):
    """Управляющих символов в математике не бывает — ни одного на выходе."""
    got = parse_json_response('{"latex": "%s"}' % latex)["latex"]
    leaked = [c for c in got if ord(c) < 32]
    assert not leaked, f"утекли управляющие символы {[hex(ord(c)) for c in leaked]}"


@pytest.mark.parametrize("latex", LATEX_CORPUS)
def test_roundtrip_correctly_escaped(latex):
    """parse(serialize(x)) == x — корректно экранированный JSON не портится."""
    assert parse_json_response(json.dumps({"latex": latex}))["latex"] == latex


@pytest.mark.parametrize("latex", LATEX_CORPUS)
def test_roundtrip_is_idempotent(latex):
    """Повторный разбор уже разобранного ничего не меняет."""
    once = parse_json_response(json.dumps({"latex": latex}))["latex"]
    twice = parse_json_response(json.dumps({"latex": once}))["latex"]
    assert once == twice == latex


def test_mixed_valid_and_invalid_escapes_in_one_string():
    """Кучность дефекта: раньше судьба `\\frac` зависела от того, попалась ли
    рядом команда с невалидным escape (`\\left`), роняющая быстрый путь."""
    got = parse_json_response(r'{"latex": "\left(\frac{1}{2}\right)"}')["latex"]
    assert got == r"\left(\frac{1}{2}\right)"


# ── настоящие управляющие символы обязаны уцелеть ────────────────────────


def test_genuine_newline_preserved():
    assert parse_json_response('{"text": "строка1\\nстрока2"}')["text"] == "строка1\nстрока2"


def test_genuine_newline_before_latin_word_preserved():
    """`\\nline2` — не команда, значит перевод строки."""
    assert parse_json_response('{"text": "line1\\nline2"}')["text"] == "line1\nline2"


def test_genuine_tab_before_word_preserved():
    """`\\ttopic` — не команда (`to` совпадает лишь префиксом), значит таб."""
    assert parse_json_response('{"text": "a\\ttopic"}')["text"] == "a\ttopic"


# ── прежняя терпимость к глюкам модели не должна пропасть ────────────────


def test_markdown_fence_stripped():
    assert parse_json_response('```json\n{"a": 1}\n```') == {"a": 1}


def test_trailing_garbage_tolerated():
    assert parse_json_response('{"a": 1}\n\n}}') == {"a": 1}


def test_latex_inside_fenced_block():
    got = parse_json_response('```json\n{"latex": "\\frac{1}{2}"}\n```')["latex"]
    assert got == r"\frac{1}{2}"


def test_truncated_array_recovered():
    truncated = '[{"id": 1, "latex": "\\frac{1}{2}"}, {"id": 2, "latex": "\\ti'
    got = parse_json_response(truncated)
    assert got == [{"id": 1, "latex": r"\frac{1}{2}"}]
