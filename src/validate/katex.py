"""Компиляция формул через серверный KaTeX (Node).

Перенесено из прототипа `newocr/mathocr/mathocr/validate/katex.py` (Сессия 2).

Зачем: SymPy в `pipeline/answer_sympy_gate.py` проверяет **ответы** — сходится ли
математика. Никто при этом не проверяет, что `question_latex` вообще **рендерится**
на экране ученика. Это разные отказы: формула может быть математически верной и
при этом не компилироваться из-за OCR-артефакта (`ight)` — потерянный `\\right`,
`\\\\circ` — задвоенный бэкслеш).

Батчем отдаёт формулы Node-скрипту `katex_compile.js` → `renderToString(latex,
{throwOnError: true})` → по каждой `{ok, error}`.

Node и npm-пакет `katex` ставятся `npm install`. Их отсутствие — **не ошибка
пайплайна**: вызывающий ловит `KatexUnavailable` и мягко пропускает проверку.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

_SCRIPT = Path(__file__).parent / "katex_compile.js"
# Корень репо, где лежит node_modules/
_REPO_ROOT = Path(__file__).resolve().parents[2]

_BATCH = 400


class KatexUnavailable(RuntimeError):
    """Node или npm-пакет katex недоступны."""


def is_available() -> bool:
    """Есть ли `node` в PATH и установлен ли пакет `katex`."""
    if shutil.which("node") is None:
        return False
    return (_REPO_ROOT / "node_modules" / "katex").is_dir()


def compile_formulas(formulas: list[str], batch_size: int = _BATCH) -> list[bool]:
    """Скомпилировать формулы, вернуть `ok` в исходном порядке.

    Пустой вход → пустой список. Node/katex недоступны → `KatexUnavailable`.
    Батчинг: один процесс Node на `batch_size` формул (амортизация запуска).
    """
    return [r["ok"] for r in compile_with_errors(formulas, batch_size)]


def compile_with_errors(formulas: list[str], batch_size: int = _BATCH) -> list[dict]:
    """Как `compile_formulas`, но с сообщениями: `[{ok, error}, ...]`."""
    if not formulas:
        return []
    if shutil.which("node") is None:
        raise KatexUnavailable("не найден `node` в PATH")
    if not (_REPO_ROOT / "node_modules" / "katex").is_dir():
        raise KatexUnavailable("не установлен npm-пакет katex (`npm install`)")

    out: list[dict] = []
    for start in range(0, len(formulas), batch_size):
        out.extend(_run_batch(formulas[start : start + batch_size]))
    return out


def _run_batch(chunk: list[str]) -> list[dict]:
    proc = subprocess.run(
        ["node", str(_SCRIPT)],
        input=json.dumps(chunk),
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    if proc.returncode != 0:
        raise KatexUnavailable(
            f"katex_compile.js завершился с {proc.returncode}: {proc.stderr.strip()}"
        )
    data = json.loads(proc.stdout)
    if len(data) != len(chunk):
        raise KatexUnavailable("katex_compile.js вернул неверное число результатов")
    return data
