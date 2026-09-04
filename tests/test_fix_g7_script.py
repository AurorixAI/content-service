"""B45: `scripts/fix_g7_failed.py` падал `NameError` при запуске.

Четыре `F821` в одном файле — `rows`, `limit`, `pass2_distractor_verify`,
`run_retry_loop`. Причина одна: у двух функций потерялись строки `def`, тела
остались висеть после `return` предыдущей функции. Синтаксически файл при этом
корректен и импортируется — падает только вызов, то есть на запуске.

Тот же класс, что B33, но в разовом скрипте починки G7, а не на входе воркера.
`F821` по `src/` при этом чисто.
"""

import importlib.util
import inspect
import pathlib

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "fix_g7_failed.py"


@pytest.fixture(scope="module")
def module():
    spec = importlib.util.spec_from_file_location("fix_g7_failed", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ENTRY_POINTS = [
    "fetch_failed",
    "fix_rows",
    "pass2_distractor_verify",
    "pass3_manual_fixes",
    "run_retry_loop",
    "main",
]


@pytest.mark.parametrize("name", ENTRY_POINTS)
def test_entry_point_is_defined(module, name):
    assert callable(getattr(module, name, None)), f"{name} не определена — NameError на запуске"


class TestCallSitesMatchSignatures:
    """Восстановленные `def` должны принимать то, чем их зовёт `main`."""

    def test_pass2_takes_rows_and_dry_run(self, module):
        sig = inspect.signature(module.pass2_distractor_verify)
        assert list(sig.parameters) == ["engine", "rows", "dry_run"]
        assert sig.parameters["dry_run"].kind is inspect.Parameter.KEYWORD_ONLY

    def test_retry_loop_takes_limit(self, module):
        sig = inspect.signature(module.run_retry_loop)
        assert list(sig.parameters) == ["engine", "limit"]
        assert sig.parameters["limit"].kind is inspect.Parameter.KEYWORD_ONLY


def test_no_orphan_bodies_after_return():
    """Осиротевшее тело — строка кода на уровне модуля сразу после `return`.

    Именно так дефект и выглядел: докстринг «Second pass: …» висел между
    функциями и читался как никому не принадлежащий строковый литерал.
    """
    import ast

    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    stray = [
        node for node in tree.body
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        and node is not (tree.body[0] if tree.body else None)
    ]
    assert not stray, f"строковый литерал на уровне модуля, строки: {[n.lineno for n in stray]}"
