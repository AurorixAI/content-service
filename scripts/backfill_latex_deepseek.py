#!/usr/bin/env python3
"""
backfill_latex_deepseek.py — v3

Исправления относительно v2:
1. Формат ответа LLM — НЕ JSON, а простые текстовые разделители.
   Причина: LaTeX состоит из обратных слэшей, а JSON-эскейпинг
   backslash-heavy контента ненадёжен даже у хороших моделей —
   \\beta, \\tau, \\nu, \\rho систематически ломались через коллизию
   с JSON escape-последовательностями \\b \\t \\n \\r.
2. Разрешение принимается ПОПОЛЯ (per-field), а не по задаче целиком.
   Что прошло — сохраняется сразу. Что не прошло — точечно в review_queue,
   остальные 8 полей той же задачи не выбрасываются.
3. SQL проверяет ВСЕ элементы distractor_meta через jsonb_array_elements,
   не только индекс [0].
4. question_text / correct_answer (поля для полнотекстового поиска)
   больше не перезаписываются — трогаем только *_latex поля.
5. KaTeX-валидатор сначала вычленяет и проверяет $$...$$ блоки отдельно,
   потом — оставшиеся одиночные $...$.
6. Семафор ограничивает реальные вызовы API на уровне задачи: один вызов
   получает полный неизменяемый контекст задания и возвращает все display-поля.
"""

import argparse
import asyncio
import copy
import hashlib
import json
import logging
import re
import subprocess
import sys
import os
import shutil
import time
import unicodedata
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('APP_ENV', 'production')

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from sqlalchemy import create_engine, text
from src.pipeline.deepseek_client import call_deepseek as _call_deepseek

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backfill_latex_deepseek")

# Persisted in the audit journal with every material display change.  A version
# is deliberately explicit: a future prompt change must be traceable to the
# exact group of fields it authored.
LATEX_BACKFILL_MODEL = "deepseek-v4-flash"
LATEX_BACKFILL_PROMPT_VERSION = "latex-display-v4.2-final-review"
LATEX_BACKFILL_POLICY_VERSION = "raw-immutable-model-final-review-v1"

# ═══════════════════════════════════════════════════════════════
# ПРОМПТ v3: house style + формат БЕЗ JSON (обходим проблему
# эскейпинга backslash-heavy LaTeX-контента)
# ═══════════════════════════════════════════════════════════════

PROMPT_PREFIX = """Ты — модуль нормализации LaTeX для образовательной платформы ALGO.
Переписываешь текст школьной математической задачи в строгом соответствии
со стандартом ниже. НЕ решаешь задачу, НЕ меняешь числа и математический смысл.
Только синтаксис и оформление.

СТАНДАРТ (обязателен без исключений):

1. РАЗДЕЛИТЕЛИ:
   - $...$  — короткая математика ВНУТРИ предложения (переменные x, y, простые равенства)
   - $$...$$ — ДЛЯ ВСЕХ выносных формул, крупных многоэтажных дробей, пределов (\\lim), интегралов (\\int) и систем уравнений. Если формула содержит предел или крупную составную дробь — всегда выноси её в $$...$$ с новой строки!
   - Никогда \\[ \\], \\( \\)

2. Основные дроби: \\dfrac{a}{b}. Внутри показателя степени/индекса используй
   компактный \\frac{a}{b}, потому что \\dfrac там типографически слишком крупный.
   Никогда "a/b" как текст.
3. Корни: ТОЛЬКО \\sqrt{x}. Никогда символ √.
4. Степени/индексы: ВСЕГДА в фигурных скобках: x^{2}, x_{1} (даже 1 символ).
5. Умножение: \\cdot для чисел/переменных. Никогда *, никогда "x" как знак умножения.
6. Греческие буквы и операторы: ТОЛЬКО LaTeX-команды (\\alpha, \\beta, \\tau, \\nu,
   \\rho, \\leq, \\geq, \\neq, \\infty, \\pm, \\mathbb{R}, \\varnothing).
   Никогда unicode-символы.
7. Русский текст ВНУТРИ математики: ВСЕГДА оборачивай в \\text{...}.
8. Интервалы: разделитель — точка с запятой: $x \\in (-2; 5]$
9. Системы уравнений: через \\begin{cases}...\\end{cases}
10. НЕ исправляй опечатки, слова, числа, знаки, порядок частей или пунктуацию
    исходника. Допустимы ТОЛЬКО LaTeX-разметка и типографские пробелы вокруг
    уже существующих математических знаков. Исходный текст — источник истины.
    Не заменяй `е` на `ё` или `ё` на `е`, не исправляй орфографию и стиль.

11. ЕСЛИ ВО ВХОДЕ УЖЕ ЕСТЬ $...$ ИЛИ $$...$$:
   - сохрани количество, порядок и границы этих формул;
   - НИКОГДА не вставляй новый $ или $$ внутрь существующей формулы;
   - не переноси часть формулы в отдельный $...$;
   - разрешены только безопасные нормализации: \\frac → \\dfrac,
     x^2 → x^{2}, x_1 → x_{1}, \\left/\\right и пробелы.

КРИТИЧЕСКИ ВАЖНО — если встречается ДВУСМЫСЛЕННАЯ конструкция
(например "15/08" — неясно дата это или дробь) — НЕ угадывай.
Ставь confidence low и объясняй причину.

ФОРМАТ ОТВЕТА — СТРОГО этот текстовый формат, БЕЗ JSON, БЕЗ markdown:

@@CONFIDENCE: high
@@REASON: NONE
@@TEXT:
<переписанный текст здесь, дословно как должен быть сохранён,
никакого экранирования обратных слэшей не требуется — пиши LaTeX
как есть, например \\dfrac{2}{5}, а не \\\\dfrac>
@@END

(CONFIDENCE — одно из: high, medium, low. REASON — причина сомнения
или NONE, если сомнений нет. Ничего кроме этих 4 блоков не выводи.)

Текст для обработки:
"""

# One task is the unit of LLM context.  The model sees every source field but
# may output only the requested display projections; this prevents a distractor
# from being formatted without seeing the question it belongs to.
TASK_BUNDLE_PROMPT_PREFIX = """Ты — модуль аудита и нормализации LaTeX для образовательной платформы ALGO.
Перед тобой ПОЛНЫЙ контекст ОДНОГО задания. Исходные поля неизменяемы: не
решай задачу, не исправляй содержание, не меняй слова, числа, знаки, порядок
вариантов и пунктуацию. Для каждого поля есть RAW (источник истины) и
CURRENT_LATEX (текущая display-версия, она может быть пустой или испорченной).
Запрещены любые редакторские изменения обычного текста: не заменяй `е` на `ё`
или `ё` на `е`, не исправляй орфографию, стиль и пробелы вне математики.

ТЫ ПРИНИМАЕШЬ РЕШЕНИЕ ДЛЯ КАЖДОГО ПОЛЯ:
- KEEP — CURRENT_LATEX уже полностью корректен, визуально рендерится, точно
  передаёт RAW И БЕЗ ИСКЛЮЧЕНИЙ соответствует профессиональному house-style
  ниже. Верни его БУКВАЛЬНО, символ в символ.
- REPLACE — CURRENT_LATEX пуст, сломан или неверно отображает RAW. Верни новую
  display-LaTeX-версию. Если в RAW есть очевидно повреждённые старые
  разделители ($, скобки, `$-$ как дефис), исправь ИХ ТОЛЬКО в display-версии,
  сохранив все слова, числа, знаки и математический смысл RAW.
- REVIEW — смысл RAW действительно неоднозначен и безопасно создать display
  без догадки невозможно. Не выдумывай содержание.

КРИТИЧЕСКОЕ ПРАВИЛО РЕШЕНИЯ:
- Пустой, синтаксически сломанный или не соответствующий house-style
  CURRENT_LATEX НИКОГДА не является причиной REVIEW и не понижает confidence.
  Это штатная причина REPLACE. Если RAW однозначен, ты ОБЯЗАН вернуть полностью
  готовый исправленный TEXT с decision REPLACE и confidence high/medium.
- REVIEW допустим ТОЛЬКО при неоднозначности математического СМЫСЛА самого RAW,
  когда существуют минимум две разные содержательные интерпретации. Фразы
  «CURRENT_LATEX пуст», «CURRENT_LATEX содержит \\frac», «нужно создать LaTeX»
  или «KaTeX parse error» запрещены как причины REVIEW: это именно твоя работа.
- Не описывай в REASON, что собираешься исправить. Сразу выполни исправление в
  TEXT. Для корректного REPLACE ставь REASON: NONE.
- Верни блок для КАЖДОГО OUTPUT_FIELDS, даже если его RAW дословно совпадает с
  другим полем. Запрещено пропускать дублирующиеся answer/option/dmeta значения.

Правила для REPLACE: $...$ для inline-математики, $$...$$ только для
действительно выносных формул; \\dfrac для основных дробей и компактный \\frac
только внутри степени/индекса; степени/индексы в
фигурных скобках; \\cdot для умножения; стандартные LaTeX-команды для
греческих букв. Разрешено исправить ТОЛЬКО display-разметку. Никогда не
исправляй образовательное содержание.

KEEP ЗАПРЕЩЁН, если хотя бы в одном математическом фрагменте CURRENT_LATEX
есть `\\frac` вне степени/индекса, дробь через `/`, умножение через `*` или `\\times`, степень
или индекс без фигурных скобок (`x^2`, `I_0`), Unicode-знак (`√`, `×`, `≤`,
`≥`, `≠`, `∞`, `±`, греческая буква) либо `\\leqslant`/`\\geqslant`. В таком
случае обязательно REPLACE: `40/5` -> `\\dfrac{40}{5}`, `3*3` ->
`3 \\cdot 3`, `L_1` -> `L_{1}`, `I_0` -> `I_{0}`, `x≥2` -> `x \\geq 2`.
Это изменение ТОЛЬКО LaTeX-представления; все исходные факты должны остаться
неизменными.
Перед выдачей TEXT выполни буквальный финальный проход по КАЖДОМУ символу
`^` и `_` во всех формулах: сразу после него обязана стоять `{`. Исправь ВСЕ
вхождения, а не только первое. Аналогично проверь КАЖДЫЙ `/` и `*` внутри
математики. Если для поля указан `@@CURRENT_VALIDATION`, это обязательная
причина REPLACE, которую нужно полностью устранить во всех вхождениях.
Обычный знак `/` допустим только как часть единицы измерения внутри
`\\text{...}`, например `$7{,}5\\,\\text{л/см}$`; арифметическое деление всегда
оформляй через `\\dfrac`. Не оставляй отдельный фрагмент `$/$`: единицу вида
`км/ч` вынеси в обычный текст либо оформи целиком через `\\text{км/ч}`.
Повреждённые границы вокруг деления обязательно собери в одну формулу:
`$(a+b)$ $/2=c$` -> `$\\dfrac{a+b}{2}=c$`,
`$(a+b)/2=c$` -> `$\\dfrac{a+b}{2}=c$`.
Не заменяй исходное деление `/` двоеточием `:`. Вложенное деление
`$3/(\\frac{3}{4})$` нужно оформить как
`$\\dfrac{3}{\\frac{3}{4}}$`, сохранив именно операцию деления.
Если `/` разделяет обычные слова, это не математика:
`смежных $/$ односторонних углов` нужно вернуть как
`смежных/односторонних углов`, сохранив оба исходных слова.
Единицы `10 стр $/$ день` верни как `$10$ стр/день`; числовое значение и
названия единиц менять запрещено.
Вложенные команды проверяй рекурсивно. В `\\dfrac{x^{\\frac{1}{2}}}{y}`
внутренний компактный `\\frac` правилен, потому что находится в степени;
`\\dfrac{x^{\\dfrac{1}{2}}}{y}` внутри степени следует избегать как избыточно крупный.

LEGACY-РАЗМЕТКА:
- У чистого значения ответа всегда одна внешняя пара `$...$`, никогда `$$...$$`.
- «Одна внешняя пара» означает БУКВАЛЬНО ровно два символа `$` во всём TEXT.
  Если RAW равен `$x=1; y=2$`, правильно: `$x=1; y=2$`.
  ЗАПРЕЩЕНО: `$x=1$; $y=2$`. То же правило действует для answer,
  dmeta[n].value и option[n], когда RAW является одной чистой формулой.
- В старых данных `\\frac` иногда повреждён управляющим символом form-feed и
  выглядит как `rac{a}{b}` или `\\x0crac{a}{b}`. Если числитель и знаменатель
  однозначны, восстанови только display-команду как `\\dfrac{a}{b}`.
- В старой таблице `\\hline` может идти сразу после заголовка без `\\\\`.
  В display-array поставь корректный перенос строки перед `\\hline`; значения
  ячеек, их порядок и количество не меняй.
  Буквальный общий пример: `x&y\\hline1&2\\\\2&4` нужно переписать как
  `x & y \\\\ \\hline 1 & 2 \\\\ 2 & 4`. KEEP для исходной формы запрещён.
- Старая система `\\left\\{\\begin{array}{l}x=1, \\\\ y=2\\end{array}\\right.`
  ВСЕГДА заменяется на `\\begin{cases}...\\end{cases}` без изменения уравнений.
- В поле question системы, крупные интегралы и пределы являются выносными
  конструкциями и обязаны находиться внутри `$$...$$` с новой строки. В полях
  dmeta[n].description и кратких пояснениях инлайн-формулы с `\\lim` и `\\int`
  допустимы внутри `$...$` для сохранения связности текста фразы.
- МАРКЕРЫ ПУНКТОВ (СПИСКОВ): Если в RAW маркер пункта задачи (например `$а)$`,
  `$б)$`, `$1)$`, `$2)$`, `$a)$`, `$b)$` или `$: 1) ...$`) оказался внутри
  знаков `$ ... $`, ты ОБЯЗАН вынести маркер пункта наружу в обычный текст перед
  формулой: например `а) $f(x)$` вместо `$а) f(x)$`, `1) $x=2$` вместо `$1) x=2$`.
  Внутри математических знаков `$ ... $` НЕ должно оставаться закрывающей круглой скобки пункта.
- В чистых компактных значениях answer, dmeta[n].value и option[n] действует
  правило одной внешней пары `$...$` даже для системы, интеграла или предела:
  кнопки/карточки ответа не превращай в выносные блоки `$$...$$`.
- Повреждённый разделитель разрядов `$45\\$,$672$` означает число 45672.
  Правильно: `$45\\,672$`. Никогда не пиши `$45{,}672$`: это десятичная
  запятая и она меняет представление числа. Аналогично
  `$149\\$,$597\\$,$870$` -> `$149\\,597\\,870$`.

ОБЯЗАТЕЛЬНАЯ РЕАКЦИЯ НА @@CURRENT_VALIDATION:
- `pure_math_value_must_be_one_inline_formula` -> всё математическое значение целиком
  (включая запятые и точки с запятой между координатами/корнями) должно находиться
  внутри ровно одной внешней пары `$ ... $`; не разрывай формулу на части;
- `professional_style_requires_dfrac` -> удали КАЖДЫЙ арифметический `/` из
  математических фрагментов: собери его операнды в `\\dfrac{...}{...}`; если
  это единица или разделитель слов, вынеси `/` из `$...$` как обычный текст;
- `professional_style_requires_cases_for_system` -> `\\begin{cases}` в `$$`;
- `professional_style_requires_display_system` -> в question
  перенеси всю систему в `$$`;
- `professional_style_requires_display_operator` -> в question
  перенеси весь интеграл или предел в `$$`, не маскируй нарушение через
  `\\displaystyle` внутри `$`;
- `semantic_number_sequence_changed` у legacy-разрядов -> используй `\\,`,
  сохранив все цифры в том же порядке.
Если после твоего REPLACE указанное нарушение осталось, всё поле будет
отклонено. Перед @@END_FIELD буквально перепроверь соответствующий пункт.

ОБЯЗАТЕЛЬНАЯ САМОПРОВЕРКА ПЕРЕД ОТВЕТОМ:
1. Прочитай именно TEXT, который собираешься вернуть, как пользовательский
   визуальный рендер, а не как черновик. У каждой формулы должны быть верные
   границы $...$ или $$...$$; внутри формулы не должен оказаться русский текст.
2. Не объявляй REPLACE, если в TEXT осталась та же ошибочная граница из
   CURRENT_LATEX. Пример: `$(25-15=10$ чисел)` нужно вернуть как
   `$(25-15=10)$ чисел` — закрывающая круглая скобка входит в формулу,
   слово «чисел» находится снаружи. Это пример общего правила, а не отдельной
   задачи.
3. Если `$-$` использован как обычный дефис между словами, он НЕ является
   формулой: в display нужен обычный дефис, например `из-за`.
4. KEEP разрешён только если CURRENT_LATEX уже прошёл такую же визуальную
   проверку. Не считай старую разметку корректной только потому, что она
   непуста.
5. Круглые скобки, относящиеся к формуле, не могут быть разнесены между двумя
   блоками `$...$`. Например, legacy-текст
   `$(123456$, но сумма $25)$` должен стать
   `$(123456)$, но сумма $25$`. Первый вариант оставляет русский текст и
   разорванные скобки внутри визуальной формулы, поэтому он всегда REPLACE,
   а не KEEP.
6. Скобка, открытая в обычном тексте, обязана закрываться тоже вне `$...$`.
   Например, `(или допущена ошибка: $451$ вместо $441)$` неверно; правильно
   `(или допущена ошибка: $451$ вместо $441$)`.
7. Нельзя оставлять скобку только с одной стороны формулы. Исправляй
   `$(50$ см)` в `($50$ см)`, а `$(157)$` в `($157$)`.
8. Десятичное число — одна формула: `$0$.$5$`, `$24$.$5$` и `$(0$.$25)$`
   недопустимы. Верни соответственно `$0.5$`, `$24.5$`, `($0.25$)`.
9. Метка перечисления не является частью формулы. Legacy-варианты
   `$1)f(x)=...$`, `$a)f(x)=...$`, `$A) f(x)=...$` и `$b) x_n=...$`
   обязательно верни как `1) $f(x)=...$`, `a) $f(x)=...$`,
   `A) $f(x)=...$`, `b) $x_n=...$`. Саму метку и её алфавит менять нельзя.
10. В буквенных маркерах сохраняй точный исходный символ и алфавит:
    латинская `a)` не может превращаться в кириллическую `а)` и наоборот.
    Это изменение RAW-текста, а не LaTeX-нормализация.
    ЗАПРЕЩЕНО возвращать `$a)$`, `$b)$`, `$A)$` или `$1)$`: это всегда
    неверная LaTeX-граница. Метка обязана быть снаружи `$...$`.

КОНТРАКТ ЗНАЧЕНИЙ ОТВЕТА (СТРОГО):
- Для полей `answer`, `dmeta[i].value` и `option[i]` чистое число, дробь,
  переменная, выражение, неравенство, интервал или множество ОБЯЗАТЕЛЬНО
  возвращай как одну LaTeX-формулу `$...$`. Примеры: `27` -> `$27$`,
  `-5/4` -> `$-\\dfrac{5}{4}$`, `x∈(-∞;5]` -> `$x \\in (-\\infty; 5]$`.
- Непустое математическое значение без `$...$` не является корректным
  `correct_answer_latex`/`value_latex`/`answer_options_latex` и не может
  получить KEEP.
- Если вариант содержит обычный русский текст, сохраняй текст, а математику
  внутри него оформляй `$...$`; не меняй смысл варианта.
- Составной нумерованный ответ (`1) ...; 2) ...`) является смешанным текстом:
  не оборачивай весь список одним `$...$`, оберни отдельно математику каждого
  пункта.

Ниже идут все поля задания. Решение требуется вернуть для полей из
OUTPUT_FIELDS. Верни СТРОГО по одному блоку для КАЖДОГО, в том же label,
без JSON и markdown:

@@FIELD: <label>
@@DECISION: KEEP|REPLACE|REVIEW
@@CONFIDENCE: high|medium|low
@@REASON: NONE или краткая причина
@@TEXT:
<для KEEP — CURRENT_LATEX буквально; для REPLACE — исправленный display-LaTeX;
 для REVIEW — текущий текст без выдумывания>
@@END_FIELD

КОНТЕКСТ ПОЛЕЙ:
"""

# Per-field requests use a compact, deliberately non-contradictory contract.
# The older exhaustive bundle prompt above is retained only as historical
# documentation while deployed runs migrate; it is not sent to the model.
SINGLE_FIELD_PROMPT_PREFIX = r"""Ты — профессиональный LaTeX-нормализатор ALGO.
Обработай РОВНО ОДНО целевое display-поле. Контекст нужен только для понимания
обозначений; выводить или переписывать контекстные поля запрещено.

ПРИОРИТЕТЫ (верхнее правило сильнее нижнего):
1. Сохрани все факты RAW: слова, буквы, числа, операции, их порядок и смысл.
   Не решай задачу, не исправляй математику и не перефразируй текст.
2. Старые `$`, `$$` и их положение НЕ являются фактами. Это повреждённая
   display-разметка: добавляй, удаляй и ПЕРЕНОСИ только LaTeX-разделители так,
   чтобы итог визуально и синтаксически был корректен.
   Если дан `RAW_WITHOUT_LEGACY_DELIMITERS`, используй его как буквальный
   каркас текста и расставь формулы заново; старые позиции `$` из RAW не копируй.
   Если дан `@@LEGACY_DECIMAL_BOUNDARY_CANDIDATES`, старое `$5$, $2` может
   быть одной разорванной десятичной записью. Прочитай полный контекст задания
   и правильный ответ: если соседние цифры действительно образуют десятичное
   число, собери их в ОДНУ формулу с `{,}` (например `$5{,}2 \cdot 0{,}4$`).
   Не сохраняй прежнюю разорванную границу. Если это всё-таки перечисление,
   сохрани запятую как пунктуацию вне формулы. Решение принимает только LLM по
   смыслу задания; детектор не меняет число сам.
   Если дан `@@LEGACY_PUNCTUATION_ONLY_MATH`, legacy-фрагмент вроде `$.$` или
   `$,$` не является формулой. Удали только его `$`-границы и верни исходный
   знак пунктуации в обычном тексте. Не удаляй сам знак и не меняй слова рядом.
3. Круглые/квадратные скобки RAW — факты: не добавляй и не удаляй их по
   умолчанию. Разрешено переносить `$` через существующую скобку:
   `$(0x=18$` -> `($0x=18$), а `(значение $0)` -> `(значение $0$)`.
   Единственное исключение: если в RAW явно потеряна РОВНО ОДНА парная
   скобка и у неё есть единственная однозначная позиция в конце той же фразы
   или перечисления, восстанови только эту скобку. Если вариантов позиции два
   или больше — верни REVIEW, не угадывай.
4. CURRENT_LATEX — только черновик. Если он пуст или нарушает
   CURRENT_VALIDATION, обязательно REPLACE. REVIEW допустим только при двух
   реально разных математических прочтениях RAW, а не из-за сломанного LaTeX.

HOUSE STYLE:
- inline-математика `$...$`; крупная система/интеграл/предел в текстовом поле
  — отдельный `$$...$$`; чистое значение ответа — одна пара `$...$`;
- основные дроби `\dfrac{a}{b}`, компактный `\frac` только внутри степени или
  индекса; арифметические `/`, `*`, `\times` запрещены, используй `\dfrac` и
  `\cdot` без изменения операции. Но `*` как маска неизвестной цифры в записи
  числа — НЕ умножение: `24*` нужно показать как `$24\ast$`, а не
  `$24\cdot$`; контекст задачи определяет этот редкий случай;
- если RAW содержит дробь-группу `A/(B)`, круглые скобки здесь задают полный
  знаменатель: покажи ровно `\dfrac{A}{B}`, например
  `1/(3\cdot4)` -> `\dfrac{1}{3\cdot4}`. Не оставляй `/` и не превращай
  группу в умножение;
- никогда не заменяй исходное арифметическое деление `/` двоеточием `:`.
  Оформи те же операнды через `\dfrac`; двоеточие допустимо только тогда,
  когда оно уже было в RAW;
- `\sqrt{x}`, `x^{2}`, `x_{1}`, стандартные `\alpha`, `\leq`, `\geq`,
  `\neq`, `\infty`; Unicode-математические символы запрещены;
- русский текст остаётся вне математики либо оформляется `\text{...}`;
- единицы и слова после числа всегда остаются вне inline-формулы: пиши
  `$10$ л`, `$9{,}8$ литров`, `$40$ см`, а не `$10л$`, `$9{,}8литров$`
  или `$40см$`. Если скобка охватывает число с единицей, пиши
  `($10$ л)`: закрывающая скобка следует после единицы и вне формулы;
- одинарные кавычки вокруг единственной латинской переменной непосредственно
  перед формулой (`'a'(...)`) могут быть старым повреждённым разделителем.
  Только если полный контекст однозначно подтверждает переменную, покажи
  `$a$ (` без этих кавычек; если это может быть обычная цитата — REVIEW;
- системы оформляй `\begin{cases}...\end{cases}`.

ОБЯЗАТЕЛЬНАЯ ФИНАЛЬНАЯ ПРОВЕРКА ИМЕННО ВОЗВРАЩАЕМОГО TEXT:
- каждая пара `$` закрыта; русский текст не попал внутрь формулы;
- каждая `(`, `)`, `[`, `]` открывается и закрывается на одной стороне
  LaTeX-границы: либо обе внутри одной формулы, либо обе вне её;
- если одна пара скобок охватывает несколько формул и текст между ними,
  обе скобки обязаны быть снаружи: `($6+10$ или $6+11-1$)`. Варианты
  `$(6+10$ или $6+11-1)$` и `$(6+10$ или `$6+11-1)$` запрещены;
- внутри математики нет арифметических `/`, `*`, `\times`, основной `\frac`,
  Unicode-знаков, русских слов/единиц и степеней/индексов без `{}`; допустим
  только `\ast`, когда RAW однозначно обозначает неизвестную цифру;
- устранена КАЖДАЯ причина из CURRENT_VALIDATION, не только первая;
- все слова, буквы, числа, операции и обычная пунктуация RAW сохранились.

Верни только один блок, без JSON и markdown:
@@FIELD: <точный TARGET_FIELD>
@@DECISION: KEEP|REPLACE|REVIEW
@@CONFIDENCE: high|medium|low
@@REASON: NONE или конкретная неоднозначность RAW
@@TEXT:
<готовое display-поле>
@@END_FIELD

ЦЕЛЕВОЕ ПОЛЕ И РЕЛЕВАНТНЫЙ КОНТЕКСТ:
"""

# ═══════════════════════════════════════════════════════════════
# ПАРСИНГ ОТВЕТА — простой сплит по маркерам, без JSON.
# Backslash-heavy LaTeX больше не проходит через escape-декодирование,
# поэтому \beta, \tau, \nu, \rho больше не могут быть повреждены.
# ═══════════════════════════════════════════════════════════════

def parse_llm_response(raw: str, fallback: str) -> dict:
    conf_m = re.search(r"@@CONFIDENCE:\s*(high|medium|low)", raw, re.IGNORECASE)
    reason_m = re.search(r"@@REASON:\s*(.*)", raw)
    text_m = re.search(r"@@TEXT:\s*\n(.*?)\n@@END", raw, re.DOTALL)

    if not text_m:
        # Модель не выдержала формат — не угадываем, помечаем low confidence
        return {"canonical": fallback, "confidence": "low",
                "ambiguity_reason": "format_parse_failed"}

    reason_raw = (reason_m.group(1).strip() if reason_m else "NONE")
    reason = None if reason_raw.upper() == "NONE" else reason_raw

    return {
        "canonical": text_m.group(1).strip(),
        "confidence": (conf_m.group(1).lower() if conf_m else "low"),
        "ambiguity_reason": reason,
    }


_GARBLED_LEGACY_DOLLAR_SOUP_RE = re.compile(r"\$\s*\$\s*\$|\${3,}")


def _is_garbled_legacy_dollar_soup(value: object) -> bool:
    """Detect a stored display value that is empty math shells, not content.

    A handful of legacy rows carry values such as
    ``"$1) $ $ $ $\\log_{3}5 < \\log_{3}7$$; 2) $$...$$$$$"`` — three or more
    ``$`` in a row, or ``$`` separated only by whitespace, cannot come from a
    balanced ``$...$``/``$$...$$`` pair with real content inside every pair.
    Repeated backfill passes stalled on these exact fields because the model
    was asked to *repair* this shell instead of replacing it outright.  This
    check only ever widens ``needs_display_repair`` to treat the field as
    empty (a full, clean regeneration from the immutable raw source); it
    never invents or discards raw content itself.
    """
    text = str(value or "")
    return bool(text) and bool(_GARBLED_LEGACY_DOLLAR_SOUP_RE.search(text))


def _normalize_candidate_markup(label: str, text: str) -> str:
    """Standardize surface LaTeX markup patterns produced by LLM candidates or legacy storage.

    1. Moves trapped list markers (e.g. `$а)$`, `$1)$`, `$a) $`, `$10) -`) outside math delimiters.
    2. Cleans up broken unit delimiters such as `м $ / $ с` -> `м/с`.
    3. Wraps naked Cyrillic variable symbols inside math mode in `\\text{...}`.
    4. Merges multi-part pure math values and broken intervals (`$(A$; $B)$` -> `$(A; B)$`).
    5. Normalizes systems: `\\left\\{\\begin{array}` -> `\\begin{cases}`.
    6. Normalizes exponent fractions: `^{4/7}` -> `^{\\frac{4}{7}}`.
    7. Normalizes unbraced single-character scripts: `^2` -> `^{2}`, `_1` -> `_{1}`.
    8. Normalizes main-formula fractions: `\\frac` -> `\\dfrac`.
    9. Normalizes binary `*` and `\\times` to `\\cdot` inside math fragments.
    10. Wraps pure math values in `$ ... $` if missing outer delimiters.
    """
    if not text:
        return text
    val = text.strip()

    # 0. Collapse repeated dollars and strip empty math: "$ $ $ $" or "$$$$$"
    val = re.sub(r"\$\s*\$\s*\$+", "$", val)
    val = re.sub(r"(?<!\$)\$\s*\$(?!\$)", "", val)

    # 0b. List markers followed by dot outside math: $1$. -> 1.
    val = re.sub(r"(?<!\\)\$([0-9A-Za-zА-Яа-яЁё*]{1,2})\.\s*\$", r"\1. $", val)

    # 0c. Trapped intervals across math boundaries: ($-4$; 0) -> $(-4; 0)$
    val = re.sub(r"\(\s*\$([^$]+)\$\s*;\s*([^$)]+)\s*\)", r"$(\1; \2)$", val)
    val = re.sub(r"\[\s*\$([^$]+)\$\s*;\s*([^$\]]+)\s*\]", r"$[\1; \2]$", val)
    val = re.sub(r"\[\s*\$([^$]+)\$\s*;\s*([^$)]+)\s*\)", r"$[\1; \2)$", val)
    val = re.sub(r"\(\s*\$([^$]+)\$\s*;\s*([^$\]]+)\s*\]", r"$(\1; \2]$", val)

    # 1. Systems: \left\{\begin{array}{l}...\end{array}\right. -> \begin{cases}...\end{cases}
    val = re.sub(r"\\left\s*\\\{\s*\\begin\{array\}\s*(?:\{[a-z]*\})?", r"\\begin{cases}", val)
    val = re.sub(r"\\end\{array\}\s*\\right\.?", r"\\end{cases}", val)

    # 2. Exponent fraction: ^{4/7} -> ^{\frac{4}{7}}
    val = re.sub(r"\^\{([0-9A-Za-zА-Яа-яЁё\\]+)/([0-9A-Za-zА-Яа-яЁё\\]+)\}", r"^{\\frac{\1}{\2}}", val)

    # 3. Exponent bare scripts: x^2 -> x^{2}, x_1 -> x_{1}, ^\circ -> ^{\circ}
    val = re.sub(r"\^([A-Za-z0-9])(?=[^A-Za-z0-9]|$)", r"^{\1}", val)
    val = re.sub(r"_([A-Za-z0-9])(?=[^A-Za-z0-9]|$)", r"_{\1}", val)
    val = re.sub(r"\^(\\[A-Za-z]+)(?=[^A-Za-z{]|$)", r"^{\1}", val)
    val = re.sub(r"_(\\[A-Za-z]+)(?=[^A-Za-z{]|$)", r"_{\1}", val)

    # 4. Bare \frac -> \dfrac
    val = re.sub(r"\\frac\b", r"\\dfrac", val)

    # 5. Intervals split across math boundaries: $(A$; $B)$ -> $(A; B)$
    val = re.sub(r"(?<!\\)\$\s*;\s*(?<!\\)\$", "; ", val)
    val = re.sub(r"(?<!\\)\$\s*,\s*(?<!\\)\$", ", ", val)

    # 5b. Split decimal math boundaries: $1$.$2$ -> $1.2$, $1{,} $2 -> $1{,}2$
    val = re.sub(r"([0-9]+)\$\.\$([0-9]+)", r"\1.\2", val)
    val = re.sub(r"\$([0-9]+)\$\.\$([0-9]+)\$", r"$\1.\2$", val)
    val = re.sub(r"\$([0-9]+)\s*\{?,\}?\s*\$([0-9]+)\$", r"$\1{,}\2$", val)

    # 6. Trapped list markers inside math
    val = re.sub(r"(?<!\\)\$([0-9A-Za-zА-Яа-яЁё*]{1,2})\)\$", r"\1)", val)
    val = re.sub(r"(?<!\\)\$([0-9A-Za-zА-Яа-яЁё*]{1,2})\$(?=\))", r"\1", val)
    val = re.sub(r"(?<!\\)\$([0-9A-Za-zА-Яа-яЁё*]{1,2})\)\s*(?!\$)", r"\1) $", val)
    val = re.sub(r"\$\s*:\s*\n\s*([0-9A-Za-zА-Яа-яЁё*]{1,2})\)\s*", r":\n\1) $", val)
    def _split_trapped_markers(m):
        content = m.group(1)
        fixed = re.sub(r";\s*([0-9A-Za-zА-Яа-яЁё*]{1,2})\)\s*", r"$; \1) $", content)
        return "$" + fixed + "$"
    val = re.sub(r"(?<!\$)\$(?!\$)([^$]+)(?<!\$)\$(?!\$)", _split_trapped_markers, val)

    # 6b. Inline \tag{...} -> \qquad (...)
    val = re.sub(r"\\tag\*?\{([^}]+)\}", r"\\qquad (\1)", val)

    # 6d. Normalize trapped opening paren in math: $VAR(NUM$ -> $VAR$ ($NUM$
    val = re.sub(r"(?<!\\)\$([A-Za-zА-Яа-яЁё0-9]+)\(([0-9A-Za-zА-Яа-яЁё\.,]+)\$", r"$\1$ ($\2$", val)
    # $(NUM$ -> ($NUM$
    val = re.sub(r"(?<!\\)\$\(([0-9A-Za-zА-Яа-яЁё\.,]+)\$", r"($\1$", val)
    # Formula starts with ( but has no closing ) inside math: $(...$ -> ($...$
    def _fix_open_paren(m):
        inner = m.group(1)
        if inner.startswith("(") and ")" not in inner:
            return "($" + inner[1:] + "$"
        return "$" + inner + "$"
    val = re.sub(r"(?<!\$)\$(?!\$)([^$]+)(?<!\$)\$(?!\$)", _fix_open_paren, val)

    # 6e. Trapped parentheses in words: $(x+2 \neq 0$, но...) -> ($x+2 \neq 0$, но...)
    val = re.sub(r"(?<!\\)\$\(([^$]+),\s*([А-Яа-яЁё]+)", r"($\1$, \2", val)
    val = re.sub(r"(?<!\\)\$\(([0-9A-Za-zА-Яа-яЁё\.\,\-]+)\$", r"($\1$", val)
    val = re.sub(r"(?<!\\)\$([0-9A-Za-zА-Яа-яЁё\.\,\-]+)\)\$", r"$\1$)", val)

    # 7. Units: м $ / $ с -> м/с
    val = re.sub(r"([А-Яа-яЁё]+)\s*\$\s*/\s*\$\s*([А-Яа-яЁё]+)", r"\1/\2", val)
    # 7a. Trapped slashes at math boundaries: $/60$ -> /$60$, $60/$ -> $60$/, $4^{\circ}/$ -> $4^{\circ}$/
    val = re.sub(r"(?<!\\)\$\s*/\s*(?<!\\)\$", "/", val)
    val = re.sub(r"(?<!\\)/\s*\$(?!\$)", "$/", val)
    val = re.sub(r"(?<!\$)\$(?!\$)\s*/(?!\s*\$)", "/$", val)

    # 7b. Convert \dots / \ldots outside math to typographic ellipsis …
    math_split = re.split(r"((?<!\$)\$(?!\$)[^$]+(?<!\$)\$(?!\$))", val)
    for i in range(0, len(math_split), 2):
        math_split[i] = re.sub(r"\\(?:l?dots)\b", "…", math_split[i])
    val = "".join(math_split)

    # 7c. Standard inequality commands
    val = re.sub(r"\\(?:geqslant|geq\s*slant)\b", r"\\ge", val)
    val = re.sub(r"\\(?:leqslant|leq\s*slant)\b", r"\\le", val)

    # 8. Math-mode normalization (* -> \cdot, \times -> \cdot, division / -> \dfrac, Cyrillic -> \text{...})
    def clean_math_fragment(m):
        inner = m.group(1)

        # 1. Asterisks / masks of unknown digits / placeholders
        inner = re.sub(r"\*{2,}", lambda sm: r"\ast" * len(sm.group(0)), inner)
        inner = re.sub(r"(?<=\d)\*(?=\s*($|[)\],.;:!?]))", r"\\ast", inner)
        inner = re.sub(r"(?<![A-Za-zА-Яа-яЁё0-9])\*(?=\s*\d)", r"\\ast", inner)
        inner = re.sub(r"\(\*\)", r"(\\ast)", inner)
        inner = re.sub(r"^(\s*)\*(\s*)$", r"\1\\ast\2", inner)
        inner = re.sub(r"\*\s*([=><])", r"\\ast \1", inner)
        inner = re.sub(r"([=><])\s*\*", r"\1 \\ast", inner)
        inner = re.sub(r"(?:^|(?<=[(]))\s*\*\s*(?=[+–-])", r"\\ast ", inner)
        inner = re.sub(r"(?<=[+–-])\s*\*\s*(?:$|(?=[)]))", r" \\ast", inner)
        inner = re.sub(r"(?<=[0-9A-Za-zА-Яа-яЁё_\^\{\}])\s*\*\s*(?=[+–-])", r"\\ast ", inner)
        inner = re.sub(r"(?<=[+–-])\s*\*\s*(?=[0-9A-Za-zА-Яа-яЁё_\^\{\}])", r" \\ast", inner)
        inner = re.sub(r"(?<=[+–-])\s*\*\s*(?=[+–-])", r" \\ast", inner)
        inner = re.sub(r"\\dfrac\{\*\}", r"\\dfrac{\\ast}", inner)
        inner = re.sub(r"\\dfrac\{([^{}]+)\}\{\*\}", r"\\dfrac{\1}{\\ast}", inner)

        # 2. Binary multiplication * -> \cdot
        inner = re.sub(r"(?<=[a-zA-Z0-9_\}\)])\s*\*\s*(?=[a-zA-Z0-9_\{\\])", r" \\cdot ", inner)
        inner = re.sub(r"(?<![A-Za-z0-9_\\])\*\s*([a-zA-Z])\b", r"\\cdot \1", inner)
        inner = re.sub(r"\\times\b", r"\\cdot", inner)
        inner = re.sub(r"\\leqslant\b", r"\\le", inner)
        inner = re.sub(r"\\geqslant\b", r"\\ge", inner)

        # 3. Unicode greek in math fragments
        _GREEK = {
            "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta",
            "ε": r"\varepsilon", "θ": r"\theta", "λ": r"\lambda", "μ": r"\mu",
            "π": r"\pi", "ρ": r"\rho", "σ": r"\sigma", "τ": r"\tau",
            "φ": r"\varphi", "ω": r"\omega",
        }
        for g_c, g_cmd in _GREEK.items():
            inner = inner.replace(g_c, g_cmd)

        # 4. Convert division slashes inside math into \dfrac
        inner = re.sub(r"\\left\((.*?)\\right\)\s*/\s*\\left\((.*?)\\right\)", r"\\dfrac{\1}{\2}", inner)
        inner = re.sub(r"\\left\((.*?)\\right\)\s*/\s*([0-9A-Za-zА-Яа-яЁё\\_^{}-]+)", r"\\dfrac{\1}{\2}", inner)
        inner = re.sub(r"([0-9A-Za-zА-Яа-яЁё\\_^{}-]+)\s*/\s*\\left\((.*?)\\right\)", r"\\dfrac{\1}{\2}", inner)
        inner = re.sub(r"\(([^()]+)\)\s*/\s*\(([^()]+)\)", r"\\dfrac{\1}{\2}", inner)
        inner = re.sub(r"\(([^()]+)\)\s*/\s*([0-9A-Za-zА-Яа-яЁё\\_^{}-]+)", r"\\dfrac{\1}{\2}", inner)
        inner = re.sub(r"([0-9A-Za-zА-Яа-яЁё\\_^{}-]+)\s*/\s*\(([^()]+)\)", r"\\dfrac{\1}{\2}", inner)
        inner = re.sub(r"([0-9A-Za-z_^{}\\]+(?:\([^\)]+\))+)\s*/\s*([0-9A-Za-z_^{}\\]+)", r"\\dfrac{\1}{\2}", inner)
        inner = re.sub(r"(-?\\dfrac\{[^{}]*\}\{[^{}]*\})\s*/\s*([0-9]+)", r"\\dfrac{\1}{\2}", inner)
        inner = re.sub(r"(-?\\dfrac\{[^{}]*\}\{[^{}]*\})\s*/\s*(-?\\dfrac\{[^{}]*\}\{[^{}]*\})", r"\\dfrac{\1}{\2}", inner)
        inner = re.sub(r"(-?\\pi|[0-9A-Za-z_^{}-]+)\s*/\s*([0-9]+)", r"\\dfrac{\1}{\2}", inner)
        inner = re.sub(r"([0-9]+)\s*/\s*(\\sqrt\{[^{}]*\})", r"\\dfrac{\1}{\2}", inner)
        inner = re.sub(r"\b([a-zA-Z0-9_\^\{\}]+)\s*/\s*\(([^\)]+)\)", r"\\dfrac{\1}{\2}", inner)
        inner = re.sub(r"(?<![a-zA-Z0-9_\\])([a-zA-Z0-9_\^\{\}']+)\s*/\s*([a-zA-Z0-9_\^\{\}']+)(?![a-zA-Z0-9_\^\{\}'])", r"\\dfrac{\1}{\2}", inner)
        parts = re.split(r"(\\text\{[^{}]*\})", inner)
        for i in range(0, len(parts), 2):
            parts[i] = re.sub(r"([А-Яа-яЁё]+)", r"\\text{\1}", parts[i])
        return "$" + "".join(parts) + "$"
    val = re.sub(r"(?<!\$)\$(?!\$)([^$]+)(?<!\$)\$(?!\$)", clean_math_fragment, val)

    # 8b. Systems: if \begin{cases} is anywhere inside single $, promote to $$...$$ display block
    val = re.sub(r"(?<!\$)\$(?!\$)([^$]*?\\begin\{cases\}[\s\S]*?\\end\{cases\}[^$]*?)(?<!\$)\$(?!\$)", r"\n$$\1$$\n", val)
    val = re.sub(r"\n{3,}", r"\n\n", val).strip()

    # 8b2. Unicode superscripts outside/inside math
    val = re.sub(r"²", r"^2", val)
    val = re.sub(r"³", r"^3", val)

    # 8c. Display operators in questions: promote inline \lim and \int to $$...$$
    if label == "question":
        val = re.sub(
            r"(?<!\$)\$\s*([^$]*?\\(?:int|lim)(?![A-Za-z])[^$]*?)\s*\$(?!\$)",
            r"\n$$\1$$\n",
            val,
        )
        val = re.sub(r"\n{3,}", r"\n\n", val).strip()

    # 9. Pure math values
    if _MATH_VALUE_LABEL_RE.fullmatch(label):
        if not _CYRILLIC_RE.search(val) and "$" not in val and not re.match(r"^[\s—–-]*[0-9A-Za-zА-Яа-яЁё]+[.)]\s*", val) and "°" not in val and not re.fullmatch(r"[:—\s]+", val):
            val = f"${val}$"
        elif not _CYRILLIC_RE.search(val) and val.count("$") >= 2:
            val = re.sub(r"(?<!\\)\$\s*([,;])\s*(?<!\\)\$", r"\1 ", val)
            if not (val.startswith("$") and val.endswith("$")):
                val = f"${val}$"
    elif (val.startswith(r"\text{") or val.startswith(r"\begin{cases}") or r"\mathbb" in val or r"\ctg" in val or r"\left(" in val) and "$" not in val:
        val = f"${val}$"

    return val


def parse_task_bundle_response(
    raw: str, expected_fields: dict[str, dict], *, allow_bare_single_field: bool = False,
) -> dict[str, dict]:
    """Parse an unescaped multi-field response while retaining every backslash.

    A focused repair has exactly one target field. Some small formatter models
    obey its substantive request but return the requested display text without
    protocol markers. Such a response is a *draft*, never a final approval:
    it must go through a later explicit structured final-review response before
    it can be saved.
    """
    block_re = re.compile(
        r"@@FIELD:\s*([^\n]+)\n"
        r"@@DECISION:\s*(KEEP|REPLACE|REVIEW)\s*\n"
        r"@@CONFIDENCE:\s*(high|medium|low)\s*\n"
        r"@@REASON:\s*([^\n]*)\n"
        r"@@TEXT:\s*\n(.*?)\n@@END_FIELD",
        re.IGNORECASE | re.DOTALL,
    )
    parsed: dict[str, dict] = {}
    duplicates: set[str] = set()
    for match in block_re.finditer(raw):
        label = match.group(1).strip()
        if label not in expected_fields:
            continue
        if label in parsed:
            duplicates.add(label)
            continue
        reason_raw = match.group(4).strip()
        parsed[label] = {
            "canonical": _normalize_candidate_markup(label, match.group(5).strip()),
            "decision": match.group(2).upper(),
            "confidence": match.group(3).lower(),
            "ambiguity_reason": None if reason_raw.upper() == "NONE" else reason_raw,
        }
    result: dict[str, dict] = {}
    bare_response = raw.strip()
    if (
        allow_bare_single_field
        and len(expected_fields) == 1
        and not parsed
        and bare_response
        and "@@" not in bare_response
        and "```" not in bare_response
    ):
        label = next(iter(expected_fields))
        return {
            label: {
                "canonical": _normalize_candidate_markup(label, bare_response),
                "decision": "REPLACE",
                # Never manufacture model confidence in Python. This remains
                # usable as a repair draft only; the final independent model
                # review must return an explicit high/medium confidence block.
                "confidence": "low",
                "ambiguity_reason": None,
                "requires_explicit_final_review": True,
                "response_protocol": "bare_repair_draft",
            }
        }
    for label, field in expected_fields.items():
        if label not in parsed or label in duplicates:
            result[label] = {
                "canonical": field["current"],
                "decision": "REVIEW",
                "confidence": "low",
                "ambiguity_reason": "bundle_field_missing_or_duplicate",
            }
        else:
            result[label] = parsed[label]
    return result


# ═══════════════════════════════════════════════════════════════
# ВАЛИДАЦИЯ: KaTeX через Node, отдельно $$ блоки и $ inline
# ═══════════════════════════════════════════════════════════════

# ``katex`` is resolved from this repository's own ``node_modules`` (see
# package.json), never from a checkout-specific absolute path: the validator
# has to run identically on a developer machine and in CI.
_KATEX_MODULE = os.environ.get("KATEX_MODULE") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "node_modules", "katex"
)

KATEX_VALIDATE_JS = "const katex = require(%s);\n" % json.dumps(_KATEX_MODULE) + """
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', d => input += d);
process.stdin.on('end', () => {
    try {
        let text = input;

        // An unmatched delimiter is not a valid display contract even when
        // a permissive regex below happens not to capture it.
        const unescapedDollars = [...text.matchAll(/(?<!\\\\)\\$/g)].length;
        if (unescapedDollars % 2 !== 0) {
            throw new Error('unmatched_math_delimiter');
        }

        // Сначала — блочные $$...$$ (проверяем и вырезаем, чтобы не
        // мешали парсингу одиночных $ ниже)
        const blockRe = /\\$\\$([^$]+)\\$\\$/g;
        let m;
        while ((m = blockRe.exec(text)) !== null) {
            const inner = m[1].trim();
            if (inner) katex.renderToString(inner, { throwOnError: true, strict: 'ignore', displayMode: true });
        }
        const withoutBlocks = text.replace(blockRe, '');

        // Теперь — одиночные $...$
        const inlineRe = /\\$([^$]+)\\$/g;
        while ((m = inlineRe.exec(withoutBlocks)) !== null) {
            const inner = m[1].trim();
            if (inner) katex.renderToString(inner, { throwOnError: true, strict: 'ignore' });
        }

        process.exit(0);
    } catch (e) {
        process.stderr.write(String(e.message || e));
        process.exit(1);
    }
});
"""

NODE_BIN = os.environ.get("NODE_BIN") or shutil.which("node") or "node"
_MATH_VALUE_LABEL_RE = re.compile(r"^(?:answer|dmeta\[\d+\]\.value|option\[\d+\])$")
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
# Exactly one inline formula.  ``.+`` used to accept internal ``$`` characters,
# so ``$x=1$; $y=2$`` was incorrectly certified as one pure answer value.
_SINGLE_INLINE_MATH_RE = re.compile(r"^\$(?!\$)[^$]+(?<!\$)\$$", re.DOTALL)


def validate_with_katex(text_str: str) -> tuple[bool, str]:
    if not text_str or "$" not in text_str:
        return True, ""
    try:
        result = subprocess.run(
            [NODE_BIN, "-e", KATEX_VALIDATE_JS],
            input=text_str.encode("utf-8"),
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            return True, ""
        return False, result.stderr.decode("utf-8", errors="ignore")[:300]
    except Exception as e:
        return False, f"validator_error: {e}"


_MATH_LATIN_WORDS = {
    "sin", "cos", "tan", "cot", "tg", "ctg", "log", "ln", "lim",
    "min", "max", "exp", "sqrt", "frac", "dfrac", "cdot", "times",
    "leq", "geq", "neq", "infty", "mathbb", "varnothing", "emptyset",
    "begin", "end", "cases", "left", "right", "text",
}


def _is_pure_math_value(label: str, source: str) -> bool:
    """Classify value fields without trying to format or understand them locally.

    Russian prose is a mixed-text display value. Values without Cyrillic text
    (numbers, variables, formulas, intervals and symbols in this corpus) are a
    single inline formula and must be stored as exactly one ``$...$`` block.
    The LLM still owns the conversion itself; this function is only a gate.
    """
    raw = str(source or "").strip()
    if not (_MATH_VALUE_LABEL_RE.fullmatch(label) and raw) or _CYRILLIC_RE.search(raw):
        return False
    if "°" in raw:
        return False
    clean_raw = re.sub(r"^\$|\$$", "", raw).strip()
    if re.fullmatch(r"[:—\s]+", clean_raw):
        return False
    if re.match(r"^[\s—–-]*[0-9A-Za-zА-Яа-яЁё]+[.)]\s*", clean_raw):
        return False
    if "*" in raw and not any(c.isalnum() for c in raw.replace("*", "")):
        return False

    # RAW answers sometimes contain English prose from historical imports
    # (for example ``example: 2, 4, 8``).  Treating it as one mathematical
    # value would force an invalid `$...$` wrapper around the word. LaTeX
    # command names and conventional function names remain mathematical.
    latin_words = re.findall(r"(?<!\\)[A-Za-z]{2,}", raw)
    if any(word.lower() not in _MATH_LATIN_WORDS for word in latin_words):
        return False

    # A textbook answer can be an enumerated mixed display such as
    # ``1) $x=1$; 2) $x=2$``. Each mathematical item must be delimited, but
    # wrapping the entire numbered list into one math block is not correct.
    list_markers = re.findall(r"(?:^|[,;\n]\s*)\$?[0-9A-Za-zА-Яа-яЁё]+[.)]", raw)
    if len(list_markers) >= 2 or len(_math_fragments(raw)) >= 2:
        return False
    if raw.count(";") >= 2:
        return False
    return True


def validate_display_contract(label: str, source: str, display: str) -> tuple[bool, str]:
    """Enforce the renderer contract, never synthesize a replacement locally."""
    rendered = str(display or "").strip()
    # ``$8$, $2^{2}$`` is a perfectly valid rendering of a list.  It has the
    # same surface shape as a broken ``$5$, $2`` decimal, so the display alone
    # is not enough evidence to reject it.  Reject the split only when RAW
    # proves that the neighbouring digits are a decimal (``5,2`` / ``5.2``)
    # or already contains the historical broken delimiter encoding.
    if _source_requires_joined_decimal_boundary(source, rendered):
        return False, "legacy_split_decimal_math_boundary"
    if _punctuation_only_math_fragment_diagnostics(rendered):
        return False, "legacy_punctuation_only_math_fragment"
    if _is_pure_math_value(label, source) and not _SINGLE_INLINE_MATH_RE.fullmatch(rendered):
        return False, "pure_math_value_must_be_one_inline_formula"

    # The frontend renders only explicitly delimited formulas. A bare command
    # would be shown to the student as literal ``\dfrac`` text.
    if re.search(r"\\[A-Za-z]+", _outside_math(rendered)):
        return False, "latex_command_outside_math_delimiters"
    boundaries_ok, boundaries_error = _validate_parenthesis_math_boundaries(rendered)
    if not boundaries_ok:
        return False, boundaries_error

    # Large operators belong to display blocks in prose fields. Pure answer
    # values are deliberately exempt: they are rendered inside compact option
    # controls and their contract is exactly one inline formula.
    if not _MATH_VALUE_LABEL_RE.fullmatch(label):
        without_blocks = re.sub(r"\$\$[\s\S]*?\$\$", "", rendered)
        for inline_match in re.finditer(
            r"(?<!\$)\$(?!\$)([^$]+)(?<!\$)\$(?!\$)", without_blocks
        ):
            inline_fragment = inline_match.group(1)
            if r"\begin{cases}" in inline_fragment:
                return False, "professional_style_requires_display_system"
            # In explanations and distractors (dmeta), short inline limits and integrals
            # are standard prose math and do not warrant breaking sentences into blocks.
            # Enforce display block only in question statements.
            if label == "question" and re.search(r"\\(?:int|lim)(?![A-Za-z])", inline_fragment):
                return False, "professional_style_requires_display_operator"
    return True, ""


_UNICODE_MATH_STYLE_RE = re.compile(
    r"[√×÷≤≥≠∞±αβγδεθλμπρστφω²³⁰¹⁴⁵⁶⁷⁸⁹]"
)
_UNBRACED_SCRIPT_RE = re.compile(r"(?:\^|_)(?:[A-Za-z0-9]|\\[A-Za-z]+)")
_BARE_MATH_SLASH_RE = re.compile(r"(?<!\\)/")
_TEXT_COMMAND_RE = re.compile(r"\\(?:text|textrm|textsf|texttt)\{[^{}]*\}")
# A literal asterisk can mean multiplication or a masked digit.  The edge
# forms below are objectively a number template (`24*`, `*24`), not a binary
# operation.  Ambiguous inner forms such as `2*4` are deliberately left to the
# model's full task context, never guessed by this deterministic gate.
_PLACEHOLDER_ASTERISK_RE = re.compile(
    r"(?:(?<=\d)\*(?=\s*(?:$|[)\],.;:!?]))|(?<![A-Za-zА-Яа-яЁё0-9])\*(?=\s*\d))"
)
_SPLIT_DECIMAL_MATH_BOUNDARY_RE = re.compile(
    # The left side must be its own integer math fragment. Looking only at the
    # characters touching ``$`` falsely matched a correct decimal followed by
    # the next list member: ``$0{,}1$, $1$``. The historical defect is the
    # actual split form ``$5$, $2 ...``.
    r"(?<!\\)(?<!\$)\$(?!\$)\s*(\d+)\s*\$(?!\$)\s*([,.])\s*(?<!\\)\$(?!\$)\s*(\d)"
)
_PLAIN_DECIMAL_BOUNDARY_RE = re.compile(r"(?<=\d)[,.](?=\d)")


def _split_decimal_math_boundary_diagnostics(display: str) -> list[str]:
    """Find legacy `$5$, $2` boundaries that visually break one decimal.

    This is intentionally a *gate*, not an automatic content repair.  The
    LLM receives the complete task and chooses whether the adjacent numeric
    fragments form a decimal; the gate only prevents the visibly broken
    legacy delimiter arrangement from being certified as ``verified``.
    """
    return [
        "legacy_split_decimal_math_boundary:" + repr(match.group(0))
        for match in _SPLIT_DECIMAL_MATH_BOUNDARY_RE.finditer(str(display or ""))
    ]


def _source_requires_joined_decimal_boundary(source: str, rendered: str) -> bool:
    """Whether RAW proves *this exact rendered boundary* is a decimal.

    A formatter may legitimately put separate list members into separate math
    fragments.  We therefore use this gate only with evidence from the source
    field itself, never by guessing from the rendered surface form.
    """
    raw = re.sub(r"\{\$([,.])\$\}", r"\1", str(source or ""))
    for match in _SPLIT_DECIMAL_MATH_BOUNDARY_RE.finditer(str(rendered or "")):
        left, right = match.group(1), match.group(3)
        # Explicit RAW decimal, e.g. 0,2 or 0{,}2.  A decimal elsewhere in
        # the same long task is not evidence that a separate `$0$, $1$` list
        # item is broken.
        if re.search(
            rf"(?<![\d$]){re.escape(left)}(?:[,.]|\{{[,.]\}}){re.escape(right)}(?!\d)", raw,
        ):
            return True
        # A historical comma split immediately followed by an arithmetic
        # operator is not a list: ``$5$, $2 \cdot ...`` is the damaged decimal
        # ``5,2``. This keeps the conservative comma policy above while still
        # catching the concrete legacy defect that motivated the gate.
        if re.search(
            rf"\${re.escape(left)}\$\s*,\s*\${re.escape(right)}(?=\s*(?:\\(?:cdot|times)|[*/]))",
            raw,
        ):
            return True
        # Dot-separated historical fragments are unambiguously decimal in
        # this corpus; comma-separated fragments can also be a list, so we
        # deliberately leave the ambiguous comma form to the contextual LLM.
        if match.group(2) == "." and re.search(
            rf"\${re.escape(left)}\$\s*\.\s*\${re.escape(right)}(?:\$|\b)", raw,
        ):
            return True
    return False


def _punctuation_only_math_fragment_diagnostics(display: str) -> list[str]:
    """Reject legacy wrappers such as ``$.$`` around ordinary punctuation."""
    return [
        "legacy_punctuation_only_math_fragment:" + repr(fragment)
        for fragment in _math_fragments(display)
        if re.fullmatch(r"\s*[.,;:]\s*", fragment)
    ]


def _has_bare_math_slash(fragment: str) -> bool:
    """Reject division slashes except inside an explicit text/unit command."""
    without_text = _TEXT_COMMAND_RE.sub("", str(fragment or ""))
    return bool(_BARE_MATH_SLASH_RE.search(without_text))


def _bare_math_slash_examples(fragment: str) -> list[str]:
    """Return compact diagnostics while keeping the authoritative gate broad."""
    without_text = _TEXT_COMMAND_RE.sub("", str(fragment or ""))
    examples = re.findall(r"\S+\s*/\s*\S+", without_text)
    return examples or (["/"] if _BARE_MATH_SLASH_RE.search(without_text) else [])


def _placeholder_asterisk_positions(fragment: str) -> set[int]:
    """Return literal `*` positions that unambiguously mask a digit.

    This is a classification aid for a formatting instruction, not an authoring
    mechanism.  The LLM still chooses the rendered expression from immutable
    source and may return REVIEW for a semantically ambiguous inner asterisk.
    """
    return {match.start() for match in _PLACEHOLDER_ASTERISK_RE.finditer(str(fragment or ""))}


def _has_main_style_frac(fragment: str) -> bool:
    r"""Return True when \frac occurs outside a braced script context.

    TeX naturally renders \frac compactly inside an exponent/subscript;
    forcing \dfrac there produces oversized, visually poor typography.
    Main-level fractions still follow the platform's \dfrac house style.
    """
    stack: list[bool] = []
    pending_script = False
    value = str(fragment or "")
    index = 0
    while index < len(value):
        char = value[index]
        if char in "^_":
            pending_script = True
            index += 1
            continue
        if char.isspace() and pending_script:
            index += 1
            continue
        if char == "{":
            inherited = stack[-1] if stack else False
            stack.append(inherited or pending_script)
            pending_script = False
            index += 1
            continue
        if char == "}":
            if stack:
                stack.pop()
            pending_script = False
            index += 1
            continue
        if value.startswith(r"\frac", index):
            if not (stack and stack[-1]):
                return True
            index += len(r"\frac")
            pending_script = False
            continue
        pending_script = False
        index += 1
    return False


def validate_professional_latex(display: str) -> tuple[bool, str]:
    """Enforce ALGO's LaTeX house style inside explicit math fragments.

    This is deliberately a rejecting gate, not a formatter.  The LLM owns the
    contextual rewrite; deterministic code only prevents a non-professional
    representation from being certified as ``verified``.
    """
    for fragment in _math_fragments(display):
        # Units and Russian prose must remain ordinary text around an inline
        # formula (or live explicitly in \text{...}).  Letting them leak into
        # math makes broken legacy delimiters look parseable to KaTeX while
        # rendering an unprofessional and often visually ambiguous result.
        math_without_text = _TEXT_COMMAND_RE.sub("", fragment)
        if re.search(r"[А-Яа-яЁё]", math_without_text):
            return False, "professional_style_requires_text_outside_math"
        # A left brace plus ``array`` is a legacy way of drawing a system.  It
        # renders, but is not our semantic/typographic representation; the LLM
        # must rewrite it as ``cases`` without changing any equation.
        if re.search(r"\\left\s*\\\{\s*\\begin\{array\}", fragment):
            return False, "professional_style_requires_cases_for_system"
        if _has_main_style_frac(fragment):
            return False, "professional_style_requires_dfrac"
        if _UNBRACED_SCRIPT_RE.search(fragment):
            return False, "professional_style_requires_braced_script"
        if _placeholder_asterisk_positions(fragment):
            return False, "professional_style_requires_placeholder_asterisk"
        if "*" in fragment:
            return False, "professional_style_requires_cdot"
        if r"\times" in fragment:
            return False, "professional_style_requires_cdot"
        if _UNICODE_MATH_STYLE_RE.search(fragment):
            return False, "professional_style_requires_latex_commands"
        if r"\leqslant" in fragment or r"\geqslant" in fragment:
            return False, "professional_style_requires_standard_inequality_commands"
        if _has_bare_math_slash(fragment):
            return False, "professional_style_requires_dfrac"

    return True, ""


_LIST_MARKER_CONTEXT_RE = re.compile(
    r"(?:^|[.:;,?!\$\n—–-]\s*|\s+)"
    # A Cyrillic letter is never a math variable in this corpus (variables
    # are always Latin), so the full alphabet is a safe marker token: this
    # corpus enumerates sub-items past `а-г` into `и, к, л, м, н...` and even
    # `с`, not only the first few letters. Latin stays the narrow `a-j`
    # (`x, y, z, n, m, t, v...` are common variable names here) plus the
    # single Roman-numeral sub-item marker `v` this corpus also uses.
    r"(?:[0-9]{1,3}|[a-jA-Jv]|[а-яёА-ЯЁ])\*?$"
)


def _list_marker_close_positions(text_value: str) -> set[int]:
    """Indices of ``)`` that read as a list marker (``a)``, ``б)``, ``12)``)
    purely from the token immediately before them, independent of bracket
    nesting.  A caller decides *whether* nesting state still lets such a
    position be skipped; this only says the token itself looks like a marker.
    """
    return {
        index for index, char in enumerate(text_value)
        if char == ")" and _LIST_MARKER_CONTEXT_RE.search(text_value[:index])
    }


def _validate_parenthesis_math_boundaries(display: str) -> tuple[bool, str]:
    """Reject parentheses whose two sides live on opposite sides of ``$``.

    KaTeX validates each formula independently and therefore accepts both
    ``$(25-15=10$ чисел)`` and ``(текст ... $441)$``. They are visually broken
    even though the formula fragment itself parses. This scanner is only a
    safety gate; the LLM remains responsible for producing the repair.
    """
    text_value = str(display or "")

    # A list marker can sit *inside* an already-open real parenthetical, e.g.
    # ``(например: 1) решения ...; 2) когда ...равными)``: only the final
    # ``)`` closes the ``(``, and ``1)``/``2)`` are nested markers.  The
    # marker check below only fires when nothing is open, which handles a
    # marker at the top level but would wrongly consume the outer ``(`` on
    # the first nested ``1)`` here.  A blind "markers never count" rule is
    # just as wrong the other way: in ordinary math like ``(2x-1)`` the ``1)``
    # is genuinely the closer, not a marker, even though the token before it
    # (a bare digit after ``-``) matches the same shape.  The two cases are
    # told apart by whether the *rest* of the string still balances once
    # every marker-shaped ``)`` is set aside: it does for the nested-list
    # sentence (one real ``(`` pairs with the one non-marker ``)``) and it
    # does not for ``(2x-1)`` (the ``(`` would then have no closer at all).
    # Markers are only ever treated as non-consuming when that global check
    # confirms the *remaining* brackets balance without them — never as a
    # default — so this cannot silently hide a genuinely missing closer.
    marker_positions = _list_marker_close_positions(text_value)
    if marker_positions:
        opens = sum(1 for c in text_value if c in "([")
        real_closes = sum(
            1 for i, c in enumerate(text_value) if c in ")]" and i not in marker_positions
        )
        markers_always_skippable = opens == real_closes
    else:
        markers_always_skippable = False

    scope: tuple[str, int] | None = None
    next_scope_id = 0
    opened_in: list[tuple[str, int] | None] = []
    index = 0
    while index < len(text_value):
        char = text_value[index]
        if char == "$" and (index == 0 or text_value[index - 1] != "\\"):
            delimiter = "display" if text_value[index:index + 2] == "$$" else "inline"
            if scope is None:
                scope = (delimiter, next_scope_id)
                next_scope_id += 1
            elif scope[0] == delimiter:
                # A parenthesis opened inside this exact formula cannot be
                # closed in a later `$...$` fragment.  Tracking only the word
                # "inline" previously allowed that false match.
                if scope in opened_in:
                    return False, "parenthesis_crosses_math_boundary"
                scope = None
            else:
                return False, "parenthesis_crosses_math_boundary"
            index += 2 if delimiter == "display" else 1
            continue
        if char in "([":
            opened_in.append(scope)
        elif char in ")]":
            is_marker = char == ")" and index in marker_positions
            if is_marker and (not opened_in or markers_always_skippable) and scope is None:
                # A list marker such as ``a)`` or ``б)`` is ordinary prose, not
                # an unmatched mathematical parenthesis.  This corpus enumerates
                # sub-items either as 1-3 digits (``1)``, ``12)``) or as a
                # single early-alphabet letter (``a)``...``j)``, ``а)``...``к)``),
                # optionally starred for an advanced part (``в*)``).  The token
                # itself is what makes a marker safe to recognise, not its
                # preceding context: real textbook prose introduces a marker
                # after a completed sentence, a colon/semicolon, a dash, or
                # plain mid-clause whitespace (``различие а) ...``) just as
                # often as after punctuation.  A late-alphabet or multi-letter
                # token (``x)``, ``N)``) is a common variable name, not a
                # marker, and must still be rejected even after whitespace —
                # broadening the *token* set instead of the *context* keeps
                # that distinction rather than erasing it.
                index += 1
                continue
            if not opened_in:
                return False, "unbalanced_parentheses"
            if opened_in.pop() != scope:
                return False, "parenthesis_crosses_math_boundary"
        index += 1
    if opened_in or scope is not None:
        return False, "unbalanced_parentheses"
    return True, ""


def _single_missing_closing_parenthesis_hint(source: str) -> str:
    """Describe one objectively incomplete prose parenthesis to the LLM.

    This is deliberately *not* a repair routine: it never appends a character
    and has no effect on the persisted value.  It merely gives the reviewing
    model explicit authority to repair the one delimiter when the raw source
    has exactly one unmatched opening parenthesis and no unmatched closing
    parenthesis.  Any semantic ambiguity still requires the model to return
    REVIEW.
    """
    value = str(source or "")
    openings: list[int] = []
    unexpected_closings: list[int] = []
    for index, character in enumerate(value):
        if character == "(":
            openings.append(index)
        elif character == ")":
            if openings:
                openings.pop()
            else:
                unexpected_closings.append(index)
    if len(openings) != 1 or unexpected_closings:
        return ""

    opening = openings[0]
    tail = value[opening:]
    final_punctuation = bool(re.search(r"[.?!…]\s*$", value))
    location = "перед финальной пунктуацией этой фразы" if final_punctuation else "в конце той же фразы"
    return (
        "RAW содержит ровно одну незакрытую `(` без лишней `)`; её позиция "
        f"{opening}, хвост: {json.dumps(tail, ensure_ascii=False)}. "
        "Это подтверждённый дефект парности, а не разрешение менять смысл. "
        f"Если контекст подтверждает одну скобочную фразу, добавь ровно одну `)` {location}; "
        "иначе верни REVIEW."
    )


def _math_boundary_diagnostics(display: str) -> list[str]:
    """Locate unmatched round/square brackets inside individual math blocks.

    This is diagnostic-only: it points the LLM to a damaged legacy fragment
    but never constructs or writes a repair.
    """
    diagnostics: list[str] = []
    pairs = {")": "(", "]": "["}
    for fragment_index, fragment in enumerate(_math_fragments(display)):
        stack: list[tuple[str, int]] = []
        for position, char in enumerate(fragment):
            if char in "([":
                stack.append((char, position))
            elif char in ")]":
                if stack and stack[-1][0] == pairs[char]:
                    stack.pop()
                else:
                    diagnostics.append(
                        f"math_fragment[{fragment_index}] unmatched_closing_{char} "
                        + json.dumps(fragment, ensure_ascii=False)
                    )
        for char, _position in stack:
            diagnostics.append(
                f"math_fragment[{fragment_index}] unmatched_opening_{char} "
                + json.dumps(fragment, ensure_ascii=False)
            )
    return diagnostics


# KaTeX proves syntax only. This deterministic gate rejects a formatter result
# if it no longer contains the source's ordered numbers, letters, or operators.
# It permits house-style notation substitutions such as / -> \dfrac and × ->
# \cdot, but sends any possible source edit to review instead of the database.
_UNICODE_SEMANTIC_MAP = str.maketrans({
    "−": "-", "–": "-", "—": "-", "×": "*", "·": "*", "÷": "/",
    "≤": "<=", "≥": ">=", "≠": "!=", "≈": "approx", "∞": "infty", "±": "+-",
    "∈": "in", "∉": "notin", "∅": "emptyset", "∪": "cup", "∩": "cap",
    "→": "to", "⇒": "implies", "∑": "sum", "∫": "int", "∂": "partial",
    # ``∛`` and ``∜`` are semantic root operators, not a literal digit next
    # to a square-root sign.  Normalising them to the same indexed-root
    # representation as ``\\sqrt[3]`` / ``\\sqrt[4]`` prevents a valid
    # professional projection from being rejected as a changed number.
    "√": "sqrt", "∛": "sqrt[3]", "∜": "sqrt[4]",
    "²": "2", "³": "3", "⁰": "0", "¹": "1",
    "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon",
    "θ": "theta", "λ": "lambda", "μ": "mu", "π": "pi", "ρ": "rho",
    "σ": "sigma", "τ": "tau", "φ": "phi", "ω": "omega",
})
_LATEX_OPERATOR_MAP = (
    (r"\div", "/"),
    (r"\cdot", "*"), (r"\times", "*"), (r"\ast", "*"),
    (r"\leqslant", "<="), (r"\geqslant", ">="),
    (r"\leq", "<="), (r"\geq", ">="), (r"\le", "<="), (r"\ge", ">="),
    (r"\neq", "!="), (r"\approx", "approx"), (r"\pm", "+-"),
    (r"\varnothing", "emptyset"), (r"\emptyset", "emptyset"),
    (r"\notin", "notin"), (r"\in", "in"),
    (r"\cup", "cup"), (r"\cap", "cap"),
    (r"\rightarrow", "to"), (r"\to", "to"),
    (r"\Rightarrow", "implies"),
)


def _expand_latex_fractions(value: str) -> str:
    r"""Turn ``\dfrac{A}{B}`` into ``((A)/(B))`` for semantic comparison.

    Replacing the command itself with ``/`` puts division before the
    numerator's internal operators and creates false operator-order changes.
    This small balanced-brace parser preserves the actual infix position and
    recursively handles nested fractions. Malformed commands are left intact
    and will be rejected by the independent KaTeX/professional gates.
    """
    source = str(value or "")

    def braced(start: int):
        index = start
        while index < len(source) and source[index].isspace():
            index += 1
        if index >= len(source) or source[index] != "{":
            return None
        depth = 1
        cursor = index + 1
        while cursor < len(source) and depth:
            if source[cursor] == "{" and source[cursor - 1] != "\\":
                depth += 1
            elif source[cursor] == "}" and source[cursor - 1] != "\\":
                depth -= 1
            cursor += 1
        if depth:
            return None
        return source[index + 1:cursor - 1], cursor

    pieces: list[str] = []
    index = 0
    while index < len(source):
        command = next(
            (candidate for candidate in (r"\dfrac", r"\frac") if source.startswith(candidate, index)),
            None,
        )
        if command is None:
            pieces.append(source[index])
            index += 1
            continue
        numerator = braced(index + len(command))
        denominator = braced(numerator[1]) if numerator else None
        if not numerator or not denominator:
            pieces.append(command)
            index += len(command)
            continue
        pieces.append(
            "((" + _expand_latex_fractions(numerator[0]) + ")/("
            + _expand_latex_fractions(denominator[0]) + "))"
        )
        index = denominator[1]
    return "".join(pieces)
_MATH_FRAGMENT_RE = re.compile(r"(?<!\\)(\$\$|\$)(.+?)(?<!\\)\1", re.DOTALL)


def _math_fragments(value: str) -> list[str]:
    """Return only explicitly delimited source formulas, in source order."""
    return [match.group(2) for match in _MATH_FRAGMENT_RE.finditer(str(value or ""))]


def _outside_math(value: str) -> str:
    """Replace every explicit math fragment with the same opaque marker."""
    index = 0

    def marker(_match: re.Match) -> str:
        nonlocal index
        result = f"@@MATH_{index}@@"
        index += 1
        return result

    return _MATH_FRAGMENT_RE.sub(marker, str(value or ""))


def _normalise_existing_math(value: str) -> str:
    """Allow only harmless formatting differences in an already-delimited formula."""
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = value.replace(r"\dfrac", r"\frac")
    value = value.replace(r"\left", "").replace(r"\right", "")
    value = re.sub(r"\^([A-Za-z0-9])(?=[^A-Za-z0-9]|$)", r"^{\1}", value)
    value = re.sub(r"_([A-Za-z0-9])(?=[^A-Za-z0-9]|$)", r"_{\1}", value)
    return re.sub(r"\s+", "", value)


def strict_source_projection_check(source: str, display: str) -> tuple[bool, str]:
    """Prove that existing `$...$` source fragments and surrounding prose survived.

    This is intentionally stricter than mathematical equivalence.  If source
    already has LaTeX delimiters, a display formatter must preserve the number,
    order and structure of those fragments; only `\\frac` → `\\dfrac` and
    whitespace are accepted as presentation-only changes.  A model cannot
    silently regroup an exponent, replace an operator, or paraphrase prose.
    """
    source_fragments = _math_fragments(source)
    if not source_fragments:
        return True, ""

    display_fragments = _math_fragments(display)
    # Old delimiters are an immutable projection and must survive in order.
    # The model may additionally delimit mathematics that was raw prose in a
    # legacy value, therefore the output is allowed to contain extra blocks.
    source_index = 0
    for rendered in display_fragments:
        if (
            source_index < len(source_fragments)
            and _normalise_existing_math(source_fragments[source_index])
            == _normalise_existing_math(rendered)
        ):
            source_index += 1
    if source_index != len(source_fragments):
        return False, "semantic_existing_math_fragment_changed"

    # The formatter may add delimiters around a formula that was previously
    # plain text (for example ``25-15=10`` -> ``$(25-15=10)$``).  Comparing
    # the raw text outside *only the old* delimiters would treat that valid
    # presentation change as a prose rewrite.  Existing formula boundaries
    # are already proven above; the token-level invariant below proves that
    # all remaining words, numbers and operators survived unchanged.
    return True, ""


def _semantic_text(value: str, *, is_latex: bool) -> str:
    result = unicodedata.normalize("NFKC", str(value or ""))
    # Python/CSV imports historically interpreted the ``\f`` prefix of
    # ``\frac`` as a form-feed control character. Restore only that unmistakable
    # command shell for comparison; the RAW column itself remains untouched.
    result = result.replace("\f" + "rac", r"\frac")
    result = result.replace("\r" + "ight", r"\right")
    result = result.replace("\r" + "ho", r"\rho")
    result = result.replace("\t" + "au", r"\tau")
    result = result.replace("\b" + "eta", r"\beta")
    # OCR imports occasionally separated control words with a space (\le q, \ge qslant)
    result = re.sub(r"\\le\s*q\s*slant\b", r"\\leqslant", result)
    result = re.sub(r"\\ge\s*q\s*slant\b", r"\\geqslant", result)
    result = re.sub(r"\\le\s*q\b", r"\\leq", result)
    result = re.sub(r"\\ge\s*q\b", r"\\geq", result)
    # Another legacy delimiter loss changed an opening `$` before a function
    # name into `=` (for example ``функция =f(x)=...$``). A leading equality
    # with no left operand is presentation damage, not a mathematical operator.
    result = re.sub(
        r"(?<![A-Za-z0-9_)])=(?=[A-Za-z]+(?:\^\{?-?\d+\}?)?\s*\()",
        "", result,
    )
    # Historical imports encoded a decimal comma as either ``{,}`` or even
    # ``{$,$}``.  All of these are the same numeric fact as a plain comma;
    # canonicalise them before braces and delimiters become presentation-only.
    result = re.sub(r"(?<=\d)\{\s*\$\s*,\s*\$\s*\}(?=\d)", ",", result)
    result = re.sub(r"(?<=\d)\{\s*,\s*\}(?=\d)", ",", result)
    result = re.sub(
        r"(?<=\d)\$\s*([,.])\s*\$(?=\d)",
        lambda match: match.group(1), result,
    )
    result = result.translate(_UNICODE_SEMANTIC_MAP)
    # Historical generators frequently used the ASCII-like ``=>`` spelling
    # for implication.  A display formatter is expected to render precisely
    # that same relation as ``\Rightarrow``; canonicalise both spellings to
    # one semantic token before comparing letters and operators.
    result = result.replace("=>", "implies").replace("->", "to")
    if is_latex:
        # Ellipsis is a presentation choice; ``...`` and ``\dots`` carry
        # the same educational content.  Without this, a professional LaTeX
        # normalisation of a numerical sequence is rejected as text drift.
        result = result.replace(r"\dots", "...").replace(r"\ldots", "...")
        result = _expand_latex_fractions(result)
        # A frequent legacy import merged the variable immediately after an
        # implication command (``\Rightarrowx``).  Separate that unambiguous
        # command boundary for comparison only; the source column is untouched.
        result = re.sub(r"\\(Rightarrow|rightarrow)(?=[A-Za-z])", r"\\\1 ", result)
        for command, replacement in _LATEX_OPERATOR_MAP:
            # Some legacy rows lost the separator after a control word
            # (``\Rightarrowx``, ``\lev``). Accept the unambiguous case where
            # the suffix is exactly one Latin variable; do not use a broad
            # prefix match that could turn ``\left`` into ``<=ft``.
            if command in {
                r"\Rightarrow", r"\rightarrow", r"\leqslant", r"\geqslant",
                r"\leq", r"\geq", r"\neq", r"\le", r"\ge",
                r"\cdot", r"\times", r"\div", r"\pm",
            }:
                result = re.sub(
                    re.escape(command) + r"(?=[A-Za-z](?![A-Za-z]))",
                    replacement, result,
                )
            # A command boundary is essential: ``\le`` must not rewrite the
            # prefix of the presentation command ``\left``.
            result = re.sub(re.escape(command) + r"(?![A-Za-z])", replacement, result)

        # Environments and alignment tokens express layout, not educational
        # facts.  A formatter may safely turn two source equations into a
        # professional cases block or a serialized table into an array.
        environment = r"(?:cases|aligned|alignedat|array|matrix|pmatrix|bmatrix|vmatrix|Vmatrix|gathered|split)"
        result = re.sub(
            rf"\\begin\s*\{{{environment}\}}(?:\s*\{{[^{{}}]*\}})?", "|", result,
        )
        result = re.sub(rf"\\end\s*\{{{environment}\}}", "|", result)
        result = re.sub(r"\\(?:hline|cline\s*\{[^{}]*\})", "|", result)
        result = re.sub(r"\\\\(?:\[[^\]]*\])?", "|", result)
        # Keep an opaque separator so neighbouring table cells cannot collapse
        # into a different numeric literal after whitespace is removed.
        result = result.replace("&", "|")

        # Remove only known presentation commands while retaining their
        # arguments. Semantic commands such as \sqrt, \sin, \alpha or \log
        # remain and therefore still participate in the invariant.
        result = re.sub(
            r"\\(?:left|right|text|textrm|textsf|texttt|mathrm|mathbf|mathit|mathsf|mathtt|mathbb|operatorname|displaystyle|limits|nolimits|phantom|vphantom|hphantom)\b",
            "", result,
        )
        result = re.sub(r"\\[,;:!]", "", result)

        # Markdown table separator rows are another presentation-only legacy
        # encoding and legitimately disappear when the LLM emits an array.
        result = re.sub(r"(?<!\w)-{3,}(?!\w)", "", result)
        # Keep a non-semantic separator between command arguments so `15` and
        # `8` in \dfrac{15}{8} cannot collapse into a false literal `158`.
        result = result.replace("$", "").replace("{", "|").replace("}", "|")
    # Preserve an opaque boundary for whitespace. Otherwise legacy ``x^2 2x``
    # collapses to ``x^22x`` before the numeric invariant is computed.
    return re.sub(r"\s+", "|", result).casefold()


def _is_subsequence(needle: str, haystack: str) -> bool:
    """Allow inserted LaTeX commands while requiring every raw letter to survive."""
    pos = 0
    for char in needle:
        pos = haystack.find(char, pos)
        if pos < 0:
            return False
        pos += 1
    return True


def semantic_preservation_check(
    source: str, display: str, *, allow_legacy_markup_repair: bool = False,
) -> tuple[bool, str]:
    """Check source facts expected to remain invariant under pure formatting."""
    if not allow_legacy_markup_repair:
        strict_ok, strict_reason = strict_source_projection_check(source, display)
        if not strict_ok:
            return False, strict_reason

    # A legacy source field can already contain `$...$` formulas.  Interpret
    # those as LaTeX too; otherwise `\\frac` and `\\dfrac` would falsely look
    # different to the lower-level token check despite the strict projection
    # above having proved them presentation-equivalent.
    # Older distractor values frequently store a bare LaTeX expression such as
    # ``-\frac{5}{4}`` without outer `$...$`.  It is still mathematical source,
    # not prose containing the letters "frac".  Recognising this form keeps
    # the semantic gate strict while permitting the safe `\frac → \dfrac`
    # display normalization that the formatter is explicitly allowed to make.
    source_is_latex = bool(_math_fragments(source)) or bool(re.search(r"\\[A-Za-z]+", source))
    raw = _semantic_text(source, is_latex=source_is_latex)
    rendered = _semantic_text(display, is_latex=True)

    # Compare ordered digit groups. This survives presentation-only decimal,
    # coordinate and legacy delimiter repairs while still rejecting any digit
    # insertion, deletion, replacement or reordering.
    # ``$60\$,$000$`` is a damaged historical thousands separator.  Its
    # professional display is ``$60\,000$``; after presentation commands are
    # removed one side is ``60\,000`` and the other ``60000``.  Join only this
    # unmistakable escaped-comma pattern before comparing numeric facts.
    raw_for_numbers = re.sub(r"(?<=\d)\\,(?=\d)", "", raw)
    rendered_for_numbers = re.sub(r"(?<=\d)\\,(?=\d)", "", rendered)
    raw_numbers = re.findall(r"\d+", raw_for_numbers)
    rendered_numbers = re.findall(r"\d+", rendered_for_numbers)
    if raw_numbers != rendered_numbers:
        return False, "semantic_number_sequence_changed"

    raw_letters = "".join(re.findall(r"[a-zа-яё]", raw))
    rendered_letters = "".join(re.findall(r"[a-zа-яё]", rendered))
    if raw_letters != rendered_letters:
        return False, "semantic_text_sequence_changed"

    # Explicit ``\cdot`` and conventional adjacency (``xy``) are equivalent
    # multiplication spellings. Multiplication is therefore proved by the
    # unchanged ordered operands, while +, -, division and relations remain
    # strict. This still rejects x+y -> x*y and x*y -> x/y.
    operator_re = r"(?:<=|>=|!=|\+\-|[+/=<>-])"
    if re.findall(operator_re, raw) != re.findall(operator_re, rendered):
        return False, "semantic_operator_sequence_changed"
    return True, ""


# ═══════════════════════════════════════════════════════════════
# ВЫЗОВ DEEPSEEK — семафор на уровне задачи. Один запрос получает полный
# неизменяемый контекст и возвращает display-проекции всех её полей.
# ═══════════════════════════════════════════════════════════════

def call_deepseek_latex(prompt: str) -> str:
    return _call_deepseek(prompt, model="deepseek-v4-flash", temperature=0.0, max_tokens=1000)


def call_deepseek_task_bundle(prompt: str) -> str:
    """One complete task needs a bounded, source-proportional output budget.

    A fixed 6k cap made small tasks unnecessarily slow on Azure.  The output
    is a display projection of the supplied source, so a bounded budget that
    scales with that source is sufficient.  A truncated response is rejected
    by the parser and never written; it can then be retried as review work.
    """
    output_budget = max(1200, min(4000, len(prompt) // 3))
    return _call_deepseek(
        prompt,
        system_prompt=(
            "Ты — точный нормализатор display-LaTeX для школьских заданий. "
            "Следуй формату и ограничениям из пользовательского сообщения; "
            "не объясняй ход работы и не изменяй образовательный смысл."
        ),
        model=LATEX_BACKFILL_MODEL,
        temperature=0.0,
        max_tokens=output_budget,
        timeout=90,
        # Transport retries are orchestrated by ``_paced_task_bundle_call``.
        # Keeping this low-level call to exactly one HTTP attempt makes the
        # global RPM limiter a real provider-request limit rather than a
        # best-effort limit that retries could silently exceed.
        max_retries=1,
    )


class AsyncRequestPacer:
    """Start no more than a configured number of LLM requests per minute.

    A semaphore bounds simultaneous in-flight requests, but by itself allows a
    burst that can exceed the provider's per-minute limit.  This pacer spaces
    *all* primary and self-check requests evenly, so a single Backfill process
    remains safely below the configured service limit without sacrificing
    concurrency while earlier calls are still in flight.
    """

    def __init__(self, requests_per_minute: int):
        if not 1 <= int(requests_per_minute) <= 250:
            raise ValueError("requests_per_minute must be between 1 and 250")
        self.requests_per_minute = int(requests_per_minute)
        self._interval_seconds = 60.0 / self.requests_per_minute
        self._next_start_at = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            start_at = max(now, self._next_start_at)
            self._next_start_at = start_at + self._interval_seconds
        delay = start_at - now
        if delay > 0:
            await asyncio.sleep(delay)


async def _paced_task_bundle_call(
    prompt: str, request_pacer=None, *, transport_attempts: int = 2,
) -> str:
    """Make up to two paced physical HTTP attempts for one formatter call."""
    last_error = None
    for attempt in range(transport_attempts):
        try:
            if request_pacer is not None:
                await request_pacer.acquire()
            return await asyncio.to_thread(call_deepseek_task_bundle, prompt)
        except Exception as exc:
            last_error = exc
            if attempt + 1 >= transport_attempts:
                raise
            log.warning(
                "DeepSeek transport attempt %d/%d failed; retrying through RPM pacer: %s",
                attempt + 1, transport_attempts, exc,
            )
    raise last_error or RuntimeError("No DeepSeek transport attempt made")


async def format_latex(text_str: str, semaphore: asyncio.Semaphore) -> dict:
    if not text_str or not text_str.strip():
        return {"canonical": text_str, "confidence": "high",
                "ambiguity_reason": None, "katex_ok": True, "katex_error": "",
                "semantic_ok": True, "semantic_error": ""}

    async with semaphore:
        try:
            prompt = PROMPT_PREFIX + text_str.strip()
            raw = await asyncio.to_thread(call_deepseek_latex, prompt)
            parsed = parse_llm_response(raw.strip(), fallback=text_str)
        except Exception as e:
            log.error("DeepSeek call failed: %s", e)
            return {"canonical": text_str, "confidence": "low",
                    "ambiguity_reason": f"llm_error: {e}",
                    "katex_ok": False, "katex_error": "not_validated_due_to_llm_error",
                    "semantic_ok": False, "semantic_error": "not_checked_due_to_llm_error"}

    katex_ok, katex_error = validate_with_katex(parsed["canonical"])
    semantic_ok, semantic_error = semantic_preservation_check(text_str, parsed["canonical"])

    return {
        **parsed,
        "katex_ok": katex_ok,
        "katex_error": katex_error,
        "semantic_ok": semantic_ok,
        "semantic_error": semantic_error,
    }


def _professional_latex_diagnostics(display: str) -> list[str]:
    """Describe style violations to the LLM without synthesizing a repair."""
    findings: list[str] = []
    for fragment in _math_fragments(display):
        findings.extend(f"unbraced_script:{m.group(0)}" for m in _UNBRACED_SCRIPT_RE.finditer(fragment))
        if _has_main_style_frac(fragment):
            findings.append(r"command:\frac_outside_script")
        if r"\times" in fragment:
            findings.append(r"command:\times")
        placeholder_positions = _placeholder_asterisk_positions(fragment)
        if placeholder_positions:
            findings.append("placeholder_asterisk:*")
        if any(
            position not in placeholder_positions
            for position, character in enumerate(fragment)
            if character == "*"
        ):
            findings.append("operator:*")
        findings.extend(
            f"bare_fraction:{example}"
            for example in _bare_math_slash_examples(fragment)
        )
        findings.extend(f"unicode_math:{m.group(0)}" for m in _UNICODE_MATH_STYLE_RE.finditer(fragment))
        if r"\leqslant" in fragment:
            findings.append(r"command:\leqslant")
        if r"\geqslant" in fragment:
            findings.append(r"command:\geqslant")
    return list(dict.fromkeys(findings))


def _bundle_prompt(
    context_fields: dict[str, str], current_displays: dict[str, str], output_fields: dict[str, dict],
) -> str:
    target_labels = list(output_fields)
    relevant_labels: set[str] = set(target_labels)
    relevant_labels.update(label for label in ("question", "answer") if label in context_fields)
    for target_label in target_labels:
        dmeta_match = re.fullmatch(r"dmeta\[(\d+)]\.(?:value|description)", target_label)
        if dmeta_match:
            prefix = f"dmeta[{dmeta_match.group(1)}]."
            relevant_labels.update(
                label for label in context_fields if label.startswith(prefix)
            )

    parts = [SINGLE_FIELD_PROMPT_PREFIX, "@@TARGET_FIELD: " + ", ".join(target_labels)]
    for label, source in context_fields.items():
        if label not in relevant_labels:
            continue
        target_boundary_diagnostics = (
            _math_boundary_diagnostics(source) if label in output_fields else []
        )
        target_decimal_boundary_diagnostics = (
            _split_decimal_math_boundary_diagnostics(source)
            if label in output_fields else []
        )
        target_punctuation_only_diagnostics = (
            _punctuation_only_math_fragment_diagnostics(source)
            if label in output_fields else []
        )
        target_style_locations = (
            _professional_latex_diagnostics(source) if label in output_fields else []
        )
        rebuild_legacy_display = bool(
            target_boundary_diagnostics
            or target_decimal_boundary_diagnostics
            or target_punctuation_only_diagnostics
            or target_style_locations
        )
        prompt_source = (
            re.sub(r"(?<!\\)\$", "", source)
            if rebuild_legacy_display else source
        )
        raw_marker = (
            "@@RAW_WITHOUT_LEGACY_DELIMITERS:"
            if rebuild_legacy_display else "@@RAW:"
        )
        field_parts = [
            f"@@FIELD_CONTEXT: {label}",
            raw_marker, prompt_source,
            "@@CURRENT_LATEX:", current_displays.get(label, ""),
        ]
        if label in output_fields:
            current = current_displays.get(label, "")
            raw_value = str(output_fields[label]["raw"])
            raw_diagnostics: list[str] = []
            raw_katex_ok, raw_katex_error = validate_with_katex(raw_value)
            if not raw_katex_ok:
                raw_diagnostics.append(raw_katex_error)
            raw_contract_ok, raw_contract_error = validate_display_contract(
                label, raw_value, raw_value,
            )
            if not raw_contract_ok:
                raw_diagnostics.append(raw_contract_error)
            raw_professional_ok, raw_professional_error = validate_professional_latex(raw_value)
            if not raw_professional_ok:
                raw_diagnostics.append(raw_professional_error)
            raw_style_locations = target_style_locations
            if raw_diagnostics:
                field_parts.extend((
                    "@@RAW_DISPLAY_DIAGNOSTICS:",
                    "FAIL " + "; ".join(dict.fromkeys(raw_diagnostics)),
                ))
            if raw_style_locations:
                field_parts.extend((
                    "@@RAW_STYLE_LOCATIONS:",
                    "\n".join(raw_style_locations),
                ))
            boundary_diagnostics = target_boundary_diagnostics
            if boundary_diagnostics:
                field_parts.extend((
                    "@@RAW_BOUNDARY_LOCATIONS:",
                    "\n".join(boundary_diagnostics),
                ))
            if target_decimal_boundary_diagnostics:
                field_parts.extend((
                    "@@LEGACY_DECIMAL_BOUNDARY_CANDIDATES:",
                    "\n".join(target_decimal_boundary_diagnostics),
                ))
            if target_punctuation_only_diagnostics:
                field_parts.extend((
                    "@@LEGACY_PUNCTUATION_ONLY_MATH:",
                    "\n".join(target_punctuation_only_diagnostics),
                ))
            validation_reasons: list[str] = []
            if not current.strip():
                validation_reasons.append("missing_display_value")
            katex_ok, katex_error = validate_with_katex(current)
            if not katex_ok:
                validation_reasons.append(katex_error)
            contract_ok, contract_error = validate_display_contract(label, raw_value, current)
            if not contract_ok:
                validation_reasons.append(contract_error)
            professional_ok, professional_error = validate_professional_latex(current)
            if not professional_ok:
                findings = ", ".join(_professional_latex_diagnostics(current)) or professional_error
                validation_reasons.append(f"{professional_error}; occurrences: {findings}")
            semantic_ok, semantic_error = semantic_preservation_check(
                raw_value, current, allow_legacy_markup_repair=True,
            )
            if not semantic_ok:
                validation_reasons.append(semantic_error)
            if validation_reasons:
                field_parts.extend((
                    "@@REQUIRED_DECISION: REPLACE",
                    "@@CURRENT_VALIDATION:",
                    "FAIL " + "; ".join(dict.fromkeys(validation_reasons)),
                ))
        field_parts.append("@@END_FIELD_CONTEXT")
        parts.extend(field_parts)
    parts.append("@@OUTPUT_FIELDS: " + ", ".join(output_fields))
    return "\n".join(parts)


async def format_task_bundle(
    context_fields: dict[str, str], current_displays: dict[str, str],
    output_fields: dict[str, dict], semaphore: asyncio.Semaphore,
    request_pacer=None, *, llm_self_review: bool = True,
) -> tuple[dict[str, dict], float]:
    """Format each requested field independently with full immutable context.

    A single large completion made the model spread its attention across the
    question, answer, options and all distractor descriptions.  One malformed
    block then frequently accompanied several omitted or weak blocks.  Every
    field now gets its own request, while still seeing the complete task, so
    the model can compare the projection with its source without inventing
    context.  The shared semaphore remains the single global concurrency cap.
    """
    if not output_fields:
        return {}, 0.0

    def validate_item(label: str, field: dict, item: dict) -> dict:
        current = field["current"]
        # The model is the sole author of display delimiters.  Applying a
        # post-model regex here previously rewrote correct prose such as
        # ``($10$ л)`` into a broken cross-boundary fragment.  Deterministic
        # code validates the candidate but never synthesises or moves `$`.
        canonical = _normalize_candidate_markup(label, str(item.get("canonical") or ""))
        keep_exact = item.get("decision") != "KEEP" or canonical == current
        katex_ok, katex_error = validate_with_katex(canonical)
        contract_ok, contract_error = validate_display_contract(
            label, field["raw"], canonical,
        )
        professional_ok, professional_error = validate_professional_latex(canonical)
        if not keep_exact:
            contract_ok, contract_error = False, "keep_value_changed"
        semantic_ok, semantic_error = semantic_preservation_check(
            field["raw"], canonical,
            allow_legacy_markup_repair=item.get("decision") in ("KEEP", "REPLACE"),
        )
        return {
            **item,
            "canonical": canonical,
            "katex_ok": katex_ok,
            "katex_error": katex_error,
            "contract_ok": contract_ok,
            "contract_error": contract_error,
            "professional_ok": professional_ok,
            "professional_error": professional_error,
            "semantic_ok": semantic_ok,
            "semantic_error": semantic_error,
        }

    def feedback_prompt(
        base_prompt: str, label: str, result: dict, raw_target: str,
    ) -> str:
        reasons = [
            result.get("katex_error"), result.get("contract_error"),
            result.get("professional_error"),
        ]
        reasons = list(dict.fromkeys(str(reason) for reason in reasons if reason))
        candidate = str(result.get("canonical") or "")
        locations = (
            _math_boundary_diagnostics(candidate)
            + _professional_latex_diagnostics(candidate)
        )
        repair_steps: list[str] = []
        if "professional_style_requires_dfrac" in reasons:
            repair_steps.append(
                "- professional_style_requires_dfrac: найди КАЖДУЮ основную "
                "дробь: это может быть символ `/` ИЛИ команда `\\frac{...}{...}` "
                "вне степени/индекса. Перестрой её в "
                "`\\dfrac{числитель}{знаменатель}`. Не оставляй `/`, не оставляй "
                "основной `\\frac` и не заменяй деление на `:`. Для вложенного "
                "деления используй вложенные `\\dfrac`, сохранив исходный порядок "
                "всех операндов. Команда `\\frac` допустима только внутри уже "
                "оформленной степени или индекса. Если source/candidate содержит "
                "группу `A/(B)`, круглые скобки задают весь знаменатель: "
                "перестрой её ровно в `\\dfrac{A}{B}`; например, "
                "`1/(3\\cdot4)` -> `\\dfrac{1}{3\\cdot4}`."
            )
        if "professional_style_requires_braced_script" in reasons:
            repair_steps.append(
                "- professional_style_requires_braced_script: найди КАЖДЫЙ "
                "верхний и нижний индекс. Оформи даже односимвольный индекс "
                "строго как `x^{2}`, `x_{1}`, `a^{n}`; не оставляй `x^2`, "
                "`x_1` или `a^n`. Буквы, числа и порядок RAW не меняй."
            )
        if "professional_style_requires_placeholder_asterisk" in reasons:
            repair_steps.append(
                "- professional_style_requires_placeholder_asterisk: здесь `*` "
                "однозначно является маской неизвестной цифры, а не умножением. "
                "Сохрани саму позицию маски и оформи её как `\\ast`: например, "
                "`24*` -> `$24\\ast$`. Нельзя заменять её на `\\cdot`, удалять "
                "или превращать в цифру."
            )
        if "professional_style_requires_cdot" in reasons:
            repair_steps.append(
                "- professional_style_requires_cdot: внутри формулы замени "
                "каждый АРИФМЕТИЧЕСКИЙ `*` или `\\times` на `\\cdot`; числа, "
                "буквы, скобки и порядок множителей оставь без изменений. Если "
                "`*` в полном RAW — маска неизвестной цифры в записи числа, это "
                "исключение: оформи её как `\\ast`, а не как `\\cdot`."
            )
        if "pure_math_value_must_be_one_inline_formula" in reasons:
            repair_steps.append(
                "- pure_math_value_must_be_one_inline_formula: это поле — "
                "чистый математический ответ без кириллицы (число, корни, координаты, множество). "
                "Все математические элементы, включая разделительные точки с запятой и запятые между координатами/корнями, "
                "должны находиться внутри ЕДИНОЙ пары `$...$` (например: `$(10; 2), (-8; \\dfrac{-5}{2})$` или `$x_1 = 1, \\; x_2 = 2$`). "
                "Не разрывай формулу на несколько фрагментов!"
            )
        if "professional_style_requires_display_operator" in reasons:
            repair_steps.append(
                "- professional_style_requires_display_operator: если в "
                "текстовом поле есть интеграл или предел, вынеси всю формулу в "
                "отдельный блок `$$...$$`, сохранив все операнды и границы."
            )
        if "professional_style_requires_latex_commands" in reasons:
            repair_steps.append(
                "- professional_style_requires_latex_commands: замени только "
                "Unicode-математические символы на эквивалентные LaTeX-команды "
                "внутри `$...$`; не меняй числа, буквы или математический смысл."
            )
        if "professional_style_requires_text_outside_math" in reasons:
            repair_steps.append(
                "- professional_style_requires_text_outside_math: русские "
                "единицы и слова не могут находиться внутри `$...$`. Оставь "
                "формулой только число/выражение, а единицу и закрывающую "
                "скобку снаружи: строго `($10$ л)`, `$9{,}8$ литров`, "
                "`$40$ см`. Не склеивай число с единицей и не переноси "
                "закрывающую скобку внутрь формулы."
            )
        if "latex_command_outside_math_delimiters" in reasons:
            repair_steps.append(
                "- latex_command_outside_math_delimiters: команда с обратным "
                "слэшем вне `$...$` рендерится как буквальный текст. Если это "
                "`\\text{...}` — заверни ровно эту команду в `$...$`, не меняя "
                "её содержимое: `\\text{верно}` → `$\\text{верно}$`. Если это "
                "`\\begin{tabular}...\\end{tabular}` — KaTeX не поддерживает "
                "`tabular`; замени ровно на `\\begin{array}{...}` с той же "
                "спецификацией колонок и тем же содержимым строк/ячеек, оберни "
                "весь блок в `$$...$$`, и ничего не добавляй и не убирай."
            )
        if "unbalanced_parentheses" in reasons:
            repair_steps.append(
                "- unbalanced_parentheses: пересобери формулы из RAW. Каждая "
                "круглая и квадратная скобка должна иметь парную скобку; если "
                "скобки охватывают текст и несколько формул, обе оставь снаружи "
                "math-границ. По умолчанию не добавляй и не удаляй скобки RAW. "
                "Исключение допустимо только для одной явно утраченной парной "
                "скобки, если её единственная позиция однозначно определяется "
                "концом той же фразы или перечисления; при иной неоднозначности "
                "верни REVIEW."
            )
        if "parenthesis_crosses_math_boundary" in reasons:
            repair_steps.append(
                "- parenthesis_crosses_math_boundary: не копируй позиции `$` из "
                "candidate. Возьми буквальный RAW_WITHOUT_LEGACY_DELIMITERS и "
                "расставь формулы заново. Ни одна скобка не может открываться "
                "внутри `$...$`, а закрываться снаружи или в другой формуле. "
                "Если скобки охватывают несколько формул и слова между ними, "
                "обе скобки оставь снаружи: `($a$ или $b$)`. В ЭТОМ СЛУЧАЕ "
                "запрещены `\\left`, `\\right`, `\\left.` и `\\right.`: "
                "не имитируй скобку через две math-области. Например, верни "
                "`($\\sqrt{...}$ и $\\dfrac{...}{...}$)`, а не "
                "`$\\left(\\sqrt{...}\\right.$ и $\\left.\\dfrac{...}{...}\\right)$`. "
                "Если после числа есть русская единица, она тоже снаружи: "
                "`($10$ л)`, а не `($10л)$`, `(до $10л) $` или `($10л) $`."
            )
        if re.search(r"(?<![A-Za-zА-Яа-яЁё0-9])'([A-Za-z])'(?=\s*\()", str(raw_target or "")):
            repair_steps.append(
                "- legacy_quoted_variable: одинарные кавычки вокруг одной "
                "латинской переменной непосредственно перед формулой — "
                "историческая повреждённая разметка. Сверь букву с неизменяемым "
                "контекстом задания и, только если это однозначно переменная, "
                "верни `$a$ (` в соответствующей букве без кавычек. Не удаляй "
                "кавычки, если они могут быть обычной цитатой; тогда REVIEW."
            )
        if "legacy_split_decimal_math_boundary" in reasons:
            repair_steps.append(
                "- legacy_split_decimal_math_boundary: старая запись вида "
                "`$5$, $2` не может остаться в candidate. По полному контексту "
                "и правильному ответу определи, является ли запятая десятичной. "
                "Если да, объедини соседние цифры внутри одной формулы через "
                "`{,}`; если нет, вынеси запятую из математики как пунктуацию. "
                "Не изменяй цифры, операции или слова."
            )
        if "legacy_punctuation_only_math_fragment" in reasons:
            repair_steps.append(
                "- legacy_punctuation_only_math_fragment: убери `$` только вокруг "
                "одиночного знака пунктуации (`.`, `,`, `;` или `:`). Сам знак "
                "пунктуации сохрани в обычном тексте; не добавляй формулу."
            )
        # Any technical failure gets a clean one-field reconstruction.  A
        # long all-task context was especially harmful after a second review:
        # the reviewer could turn a valid pure answer into two formulas or
        # re-introduce a house-style violation it was supposed to remove.
        # ``keep_value_changed`` is deliberately excluded: that is a protocol
        # violation, not a field-reconstruction request.
        focused_technical_rebuild = bool(reasons) and "keep_value_changed" not in reasons
        repair_block = (
            "\n@@ОБЯЗАТЕЛЬНЫЙ_АЛГОРИТМ_ИСПРАВЛЕНИЯ:\n" + "\n".join(repair_steps)
            if repair_steps else ""
        )
        location_block = (
            "\n@@ТОЧНЫЕ_ТЕХНИЧЕСКИЕ_МЕСТА:\n" + "\n".join(locations)
            if locations else ""
        )
        parenthesis_hint = _single_missing_closing_parenthesis_hint(raw_target)
        parenthesis_hint_block = (
            "\n@@ДОПУСК_НА_ВОССТАНОВЛЕНИЕ_СКОБКИ:\n" + parenthesis_hint
            if parenthesis_hint else ""
        )

        # A description of a wrong answer is not self-contained: phrases such
        # as "он выбрал" or "получил" derive their meaning from the task and
        # the distractor value.  Keep this immutable context small and clearly
        # reference-only, so a focused repair can fix delimiters without
        # guessing educational meaning or rewriting surrounding fields.
        context_labels: list[str] = []
        for context_label in ("question", "answer"):
            if context_label in context_fields and context_label != label:
                context_labels.append(context_label)
        dmeta_match = re.fullmatch(r"dmeta\[(\d+)]\.(?:value|description)", label)
        if dmeta_match:
            prefix = f"dmeta[{dmeta_match.group(1)}]."
            context_labels.extend(
                context_label
                for context_label in context_fields
                if context_label.startswith(prefix) and context_label != label
            )
        focused_context = "\n".join(
            f"@@CONTEXT_FIELD: {context_label}\n{context_fields[context_label]}"
            for context_label in dict.fromkeys(context_labels)
        )
        focused_context_block = (
            "\n\n@@IMMUTABLE_REFERENCE_CONTEXT:\n"
            + focused_context
            + "\n@@END_IMMUTABLE_REFERENCE_CONTEXT\n"
              "Контекст нужен только для проверки смысла SOURCE. Не включай его "
              "в ответ и не меняй его значения."
            if focused_context else ""
        )
        # This deliberately sends only the immutable source of the target field
        # to the model; Python never reconstructs or writes the display text.
        if focused_technical_rebuild:
            # Remove legacy delimiters only when this field actually has a
            # delimiter-boundary defect. For ordinary style repair the model
            # sees the source verbatim, which preserves authored math context.
            source_has_legacy_delimiter_damage = bool(
                _math_boundary_diagnostics(str(raw_target or ""))
                or _split_decimal_math_boundary_diagnostics(str(raw_target or ""))
                or _punctuation_only_math_fragment_diagnostics(str(raw_target or ""))
            )
            focused_raw = (
                re.sub(r"(?<!\\)\$", "", str(raw_target or ""))
                if source_has_legacy_delimiter_damage else str(raw_target or "")
            )
            return (
                "Верни только готовый русский display-текст без пояснений. "
                "Не меняй ни одного слова, числа, операции или знака из SOURCE. "
                "Скобки сохраняй; восстановить можно только одну явно утраченную "
                "парную скобку, если обязательный алгоритм ниже указывает на "
                "однозначную позицию. "
                + (
                    "Старые символы `$` удалены: расставь их заново.\n\n"
                    if source_has_legacy_delimiter_damage else
                    "Сохрани корректные границы `$` из SOURCE и исправь только "
                    "указанное оформление.\n\n"
                )
                +
                "Оформи математические выражения профессионально: дробь через "
                "`\\dfrac`, умножение через `\\cdot`, степени и индексы через "
                "фигурные скобки. Десятичная запятая внутри числа — `{,}`. "
                "Русские единицы вне формулы: `$10$ л`, `$9{,}8$ литров`.\n\n"
                "Ключевое правило скобок: если круглые скобки SOURCE охватывают "
                "несколько математических фрагментов, ОБЕ скобки остаются обычным "
                "текстом снаружи всех `$...$`. Например, `(80+12=92, 92*2=184)` "
                "обязан стать `($80+12=92$, $92\\cdot 2=184$)`, никогда "
                "`$(80+12=92$, $92\\cdot2=184)$`."
                + repair_block
                + location_block
                + parenthesis_hint_block
                + "\n\nSOURCE:\n"
                + focused_raw
                + focused_context_block
                + "\n\nВерни только полный готовый display-текст: без `@@`-маркеров, "
                  "JSON, markdown и пояснений."
            )
        # Showing a boundary-broken candidate again strongly anchors smaller
        # formatter models to the same misplaced dollars.  The immutable RAW
        # and RAW_WITHOUT_LEGACY_DELIMITERS remain in the base prompt, so omit
        # only the invalid display draft for this repair class.
        omit_invalid_candidate = any(
            reason in reasons for reason in (
                "parenthesis_crosses_math_boundary",
                "unbalanced_parentheses",
                "legacy_split_decimal_math_boundary",
                "legacy_punctuation_only_math_fragment",
            )
        )
        candidate_block = (
            "@@PREVIOUS_CANDIDATE:\n"
            "OMITTED_DUE_TO_BROKEN_LEGACY_DELIMITERS; rebuild from "
            "RAW_WITHOUT_LEGACY_DELIMITERS"
            if omit_invalid_candidate
            else "@@PREVIOUS_CANDIDATE:\n" + candidate
        )
        return (
            base_prompt
            + "\n\nФИНАЛЬНАЯ LLM-САМОПРОВЕРКА ПЕРЕД ЗАПИСЬЮ:\n"
              "Посимвольно сравни candidate с RAW-каркасом: слова, буквы, числа, "
              "операции и их порядок должны совпадать. Проверь каждую формулу, "
              "границу `$`, скобку, дробь, степень и house-style. Если candidate "
              "полностью корректен, верни его ДОСЛОВНО с decision REPLACE. Если "
              "нет — верни полностью исправленный TEXT.\n"
            + candidate_block
            + "\n@@CANDIDATE_VALIDATION:\n"
            + ("FAIL " + "; ".join(reasons) if reasons else "PASS deterministic_gates")
            + ("\n@@CANDIDATE_ERROR_LOCATIONS:\n" + "\n".join(locations) if locations else "")
            + repair_block
            + "\nВерни заново один полный блок "
              f"@@FIELD: {label}; не объясняй исправление вне протокола."
        )

    def second_pass_prompt(base_prompt: str, label: str, result: dict) -> str:
        """Ask the formatter to independently audit its completed candidate.

        This is a contextual second authoring pass. The reviewer compares the
        candidate against RAW and may correct legacy OCR/delimiter damage when
        necessary. The model, rather than a token heuristic, is the final
        authority on whether a number or operator change is a normalisation.
        """
        candidate = str(result.get("canonical") or "")
        return (
            base_prompt
            + "\n\n@@SECOND_PASS_INDEPENDENT_REVIEW:\n"
              "Это вторая независимая проверка уже подготовленного TEXT. "
              "Не доверяй ему автоматически: сопоставь его с RAW посимвольно. "
              "Проверь все слова, буквы, числа, операции, порядок, границы `$`, "
              "скобки, LaTeX-синтаксис и house-style.\n"
              "Если TEXT полностью корректен, верни его ДОСЛОВНО. Если нашёл "
              "ошибку, верни полный исправленный TEXT. Исправляй только когда "
              "контекст однозначно подтверждает нормализацию старой/OCR-разметки; "
              "при двух разумных прочтениях верни REVIEW, не угадывай. Верни "
              "REPLACE, если TEXT отличается от CURRENT_LATEX; KEEP допустим "
              "только при дословном равенстве CURRENT_LATEX.\n"
            + "@@CANDIDATE_TO_AUDIT:\n" + candidate
            + "\n@@FIRST_PASS_VALIDATION:\nPASS deterministic_gates\n"
              "Верни заново один полный блок "
              f"@@FIELD: {label}; не объясняй исправление вне протокола."
        )

    async def format_one(label: str, field: dict) -> tuple[str, dict, float]:
        """Produce a display projection, then separately certify its final form.

        A repair draft is deliberately never the terminal state. Even after a
        focused repair passes KaTeX and house-style gates, a fresh structured
        model response must audit the exact repaired text against immutable
        task context before persistence becomes possible.
        """
        one_field = {label: field}
        base_prompt = _bundle_prompt(context_fields, current_displays, one_field)
        trace: list[dict[str, object]] = []

        def trace_event(stage: str, prompt: str, response: str | None, *, error: Exception | None = None) -> None:
            trace.append({
                "stage": stage,
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "response_sha256": (
                    hashlib.sha256(response.encode("utf-8")).hexdigest()
                    if response is not None else None
                ),
                "error": type(error).__name__ if error is not None else None,
            })

        def reviewer_requested_human(result: dict) -> bool:
            return result.get("decision") == "REVIEW"

        def finalize_metadata(
            result: dict, *, first_pass_valid: bool, repairs: int,
            final_reviews: int, accepted: bool, verdict: str,
        ) -> dict:
            result["llm_self_review_required"] = bool(llm_self_review)
            result["llm_self_check_used"] = bool(final_reviews)
            result["llm_self_review_ok"] = bool(accepted) if llm_self_review else True
            result["llm_self_review_attempts"] = final_reviews
            result["llm_repair_attempts"] = repairs
            result["llm_self_review_first_pass_acceptable"] = first_pass_valid
            result["llm_trace"] = trace
            result["final_review"] = {
                "required": bool(llm_self_review),
                "completed": bool(final_reviews),
                "accepted": bool(accepted),
                "verdict": verdict,
                "model": LATEX_BACKFILL_MODEL,
                "prompt_version": LATEX_BACKFILL_PROMPT_VERSION,
            }
            return result

        async with semaphore:
            # Measure only transport/model time after acquiring the global
            # slot; queue time is not mislabeled as a slow LLM response.
            request_started_at = time.monotonic()

            async def ask(stage: str, prompt: str, *, allow_bare: bool = False) -> dict:
                try:
                    raw = await _paced_task_bundle_call(prompt, request_pacer)
                    trace_event(stage, prompt, raw)
                    parsed = parse_task_bundle_response(
                        raw.strip(), one_field, allow_bare_single_field=allow_bare,
                    )[label]
                    parsed.setdefault("response_protocol", "structured")
                    return parsed
                except Exception as exc:
                    trace_event(stage, prompt, None, error=exc)
                    raise

            try:
                candidate = validate_item(label, field, await ask("initial", base_prompt))
            except Exception as exc:
                log.error("DeepSeek field failed label=%s: %s", label, exc)
                candidate = validate_item(label, field, {
                    "canonical": field["current"],
                    "decision": "REVIEW",
                    "confidence": "low",
                    "ambiguity_reason": f"llm_error: {exc}",
                })

            first_pass_valid = field_has_valid_display_projection(candidate)
            if not first_pass_valid:
                log.info(
                    "LaTeX first pass rejected: field=%s katex=%s contract=%s professional=%s semantic=%s",
                    label,
                    candidate.get("katex_error") or "ok",
                    candidate.get("contract_error") or "ok",
                    candidate.get("professional_error") or "ok",
                    candidate.get("semantic_error") or "ok",
                )

            if not llm_self_review:
                request_seconds = time.monotonic() - request_started_at
                return label, finalize_metadata(
                    candidate, first_pass_valid=first_pass_valid, repairs=0,
                    final_reviews=0, accepted=field_has_valid_display_projection(candidate),
                    verdict="diagnostic_self_review_skipped",
                ), request_seconds

            repairs = 0
            final_reviews = 0
            accepted = False
            verdict = "unresolved"
            # At most two repairs and two independent final-review passes.
            # A final review which introduces a technical defect becomes a new
            # repair candidate and must itself be reviewed again after repair.
            while True:
                if reviewer_requested_human(candidate):
                    verdict = "model_requested_human_review"
                    break
                if not field_has_valid_display_projection(candidate):
                    if repairs >= 2:
                        verdict = "repair_attempts_exhausted"
                        break
                    repair_prompt = feedback_prompt(base_prompt, label, candidate, field["raw"])
                    try:
                        candidate = validate_item(
                            label, field,
                            await ask(f"repair_{repairs + 1}", repair_prompt, allow_bare=True),
                        )
                    except Exception as exc:
                        log.error("DeepSeek repair failed label=%s: %s", label, exc)
                        candidate = validate_item(label, field, {
                            "canonical": field["current"],
                            "decision": "REVIEW",
                            "confidence": "low",
                            "ambiguity_reason": f"llm_repair_error: {exc}",
                        })
                    repairs += 1
                    continue

                if final_reviews >= 2:
                    verdict = "final_review_attempts_exhausted"
                    break
                final_prompt = second_pass_prompt(base_prompt, label, candidate)
                try:
                    reviewed = validate_item(
                        label, field,
                        # A final review must be an explicit protocol response.
                        await ask(f"final_review_{final_reviews + 1}", final_prompt),
                    )
                except Exception as exc:
                    log.error("DeepSeek final review failed label=%s: %s", label, exc)
                    candidate = validate_item(label, field, {
                        "canonical": field["current"],
                        "decision": "REVIEW",
                        "confidence": "low",
                        "ambiguity_reason": f"llm_final_review_error: {exc}",
                    })
                    verdict = "final_review_unavailable"
                    break
                final_reviews += 1

                if reviewer_requested_human(reviewed):
                    candidate = reviewed
                    verdict = "final_model_requested_human_review"
                    break
                if (
                    field_has_valid_display_projection(reviewed)
                    and reviewed.get("confidence") in ("high", "medium")
                    and not reviewed.get("requires_explicit_final_review", False)
                ):
                    candidate = reviewed
                    accepted = True
                    verdict = "accepted_after_independent_final_review"
                    break
                if field_has_valid_display_projection(reviewed):
                    candidate = reviewed
                    verdict = "final_review_insufficient_confidence"
                    break
                candidate = reviewed

            request_seconds = time.monotonic() - request_started_at
            return label, finalize_metadata(
                candidate, first_pass_valid=first_pass_valid, repairs=repairs,
                final_reviews=final_reviews, accepted=accepted, verdict=verdict,
            ), request_seconds

    formatted = await asyncio.gather(*[
        format_one(label, field) for label, field in output_fields.items()
    ])
    results = {label: item for label, item, _seconds in formatted}
    # Sum of actual occupied LLM slots is useful for cost/throughput analysis;
    # it deliberately excludes time waiting behind other fields/tasks.
    request_seconds = sum(seconds for _label, _item, seconds in formatted)

    # answer_options and distractor_meta intentionally overlap in part of the
    # historical corpus. If the RAW value is byte-for-byte identical, an
    # already independently final-reviewed projection may be reused. The audit
    # provenance is retained; a merely technical candidate can never lend its
    # approval to another field.
    value_labels = [
        label for label in context_fields
        if _MATH_VALUE_LABEL_RE.fullmatch(label)
    ]

    def validated_duplicate(target_label: str, raw: str, candidate: str) -> dict:
        candidate = str(candidate or "").strip()
        if not candidate:
            return None
        katex_ok, katex_error = validate_with_katex(candidate)
        contract_ok, contract_error = validate_display_contract(target_label, raw, candidate)
        professional_ok, professional_error = validate_professional_latex(candidate)
        if not (katex_ok and contract_ok and professional_ok):
            return None
        return {
            "canonical": candidate,
            "decision": "REPLACE",
            "confidence": "high",
            "ambiguity_reason": None,
            "katex_ok": katex_ok,
            "katex_error": katex_error,
            "contract_ok": contract_ok,
            "contract_error": contract_error,
            "professional_ok": professional_ok,
            "professional_error": professional_error,
            "semantic_ok": True,
            "semantic_error": "",
            "projection_source": "exact_raw_duplicate",
        }

    for target_label in value_labels:
        if target_label not in output_fields or field_is_acceptable(results[target_label]):
            continue
        target_raw = str(context_fields[target_label]).strip()
        for source_label in value_labels:
            if source_label == target_label or str(context_fields[source_label]).strip() != target_raw:
                continue
            source_result = results.get(source_label)
            source_final_review = (
                source_result.get("final_review", {}) if source_result else {}
            )
            if not source_final_review.get("accepted", False):
                continue
            source_display = (
                source_result["canonical"]
                if source_result is not None and field_is_acceptable(source_result)
                else current_displays.get(source_label, "")
            )
            replacement = validated_duplicate(target_label, target_raw, source_display)
            if replacement is not None:
                replacement.update({
                    "llm_self_review_required": True,
                    "llm_self_check_used": True,
                    "llm_self_review_ok": True,
                    "llm_self_review_attempts": source_result.get("llm_self_review_attempts", 0),
                    "llm_repair_attempts": 0,
                    "llm_self_review_first_pass_acceptable": True,
                    "llm_trace": list(source_result.get("llm_trace", [])),
                    "final_review": {
                        **source_final_review,
                        "reused_for_exact_raw_duplicate": source_label,
                    },
                })
                results[target_label] = replacement
                break
    return results, request_seconds


def field_has_valid_display_projection(result: dict) -> bool:
    """Check only renderability and display contract, never model approval."""
    return (
        result.get("decision") in ("KEEP", "REPLACE")
        and result.get("katex_ok", False)
        and result.get("contract_ok", False)
        and result.get("professional_ok", False)
    )


def field_is_acceptable(result: dict) -> bool:
    """Return whether a model-reviewed display projection may be persisted.

    Semantic comparison remains available as context for the model's second
    pass, but it is intentionally not a deterministic rejection gate. Legacy
    source strings frequently split decimals, Unicode scripts and formula
    boundaries in ways that require a contextual reading to normalise.
    """
    return (
        result.get("confidence") in ("high", "medium")
        and not result.get("requires_explicit_final_review", False)
        and field_has_valid_display_projection(result)
        and (
            not result.get("llm_self_review_required", False)
            or result.get("llm_self_review_ok", False)
        )
    )


def field_failure_reason(result: dict) -> str:
    return (
        result.get("ambiguity_reason")
        or result.get("contract_error")
        or result.get("professional_error")
        or result.get("semantic_error")
        or result.get("katex_error")
        or "unacceptable_result"
    )


def stored_task_has_non_katex_gate_issue(
    question_text, question_latex, correct_answer, correct_answer_latex,
    distractor_meta, answer_options, answer_options_latex,
) -> bool:
    """Fast prefilter for stale verified rows before any LLM/API work.

    Stored ``verified`` already passed the historical KaTeX syntax gate.  This
    prefilter finds rows that fail the newer source/display contract or
    professional house style.  It intentionally avoids the expensive semantic
    comparison across every field in the full verified corpus; the selected
    rows still pass the complete KaTeX-and-semantic gate inside
    ``process_task`` before any status can be written.
    """
    def invalid(label: str, source: object, display: object) -> bool:
        raw = str(source or "").strip()
        if not raw:
            return False
        rendered = str(display or "").strip()
        if not rendered:
            return True
        return not (
            validate_display_contract(label, raw, rendered)[0]
            and validate_professional_latex(rendered)[0]
        )

    if invalid("question", question_text, question_latex):
        return True
    if invalid("answer", correct_answer, correct_answer_latex):
        return True

    dmeta = distractor_meta if isinstance(distractor_meta, list) else []
    for index, item in enumerate(dmeta):
        if not isinstance(item, dict):
            continue
        value = item.get("value") or item.get("text") or item.get("content")
        value_latex = item.get("value_latex") or item.get("text_latex") or item.get("content_latex")
        if invalid(f"dmeta[{index}].value", value, value_latex):
            return True
        source_key, display_key = (
            ("error_logic", "error_logic_latex")
            if str(item.get("error_logic") or "").strip()
            else ("explanation", "explanation_latex")
        )
        if invalid(f"dmeta[{index}].description", item.get(source_key), item.get(display_key)):
            return True

    raw_options = answer_options if isinstance(answer_options, list) else []
    display_options = answer_options_latex if isinstance(answer_options_latex, list) else []
    for index, option in enumerate(raw_options):
        value = (
            option.get("value") or option.get("text") or option.get("content")
            if isinstance(option, dict) else option
        )
        display = display_options[index] if index < len(display_options) else ""
        if invalid(f"option[{index}]", value, display):
            return True
    return False


# ═══════════════════════════════════════════════════════════════
# ОБРАБОТКА ОДНОЙ ЗАДАЧИ — все поля обрабатываются независимо.
# Canonical-поля никогда не являются результатом работы LLM: для
# description создаются отдельные *_latex-поля.
# ═══════════════════════════════════════════════════════════════

async def process_task(
    tid,
    qt,
    question_latex,
    ans,
    correct_answer_latex,
    dmeta_json,
    answer_options,
    answer_options_latex,
    semaphore: asyncio.Semaphore,
    *,
    force_reformat: bool = False,
    repair_invalid: bool = False,
    revalidate_only: bool = False,
    request_pacer=None,
    llm_self_review: bool = True,
    run_context: dict | None = None,
):
    context_fields: dict[str, str] = {}
    current_displays: dict[str, str] = {}
    output_fields: dict[str, dict] = {}

    def needs_display_repair(label: str, source_value: object, display_value: object) -> bool:
        # Used after a deterministic gate is corrected.  It re-certifies every
        # final field through ``save_result`` without asking the LLM to rewrite
        # already stored display content.  Invalid fields remain partial; only
        # independently valid projections may be promoted to verified.
        if revalidate_only:
            return False
        if force_reformat or not str(display_value or "").strip():
            return True
        if not repair_invalid:
            return False
        display_text = _normalize_candidate_markup(label, str(display_value))
        if not validate_with_katex(display_text)[0]:
            return True
        if not validate_display_contract(label, str(source_value or ""), display_text)[0]:
            return True
        if not validate_professional_latex(display_text)[0]:
            return True
        # Semantic token comparison is advisory only. A two-pass model review
        # makes the contextual decision; it must not by itself re-open a field
        # that already meets every technical display requirement.
        return False

    def shown_current(display_value: object) -> str:
        # A shell of bare, near-empty ``$`` pairs is not existing content to
        # repair — showing it to the model as "the current display" invites
        # a patch attempt that preserves fragments of the shell.  Presenting
        # an empty current value instead asks for a clean regeneration from
        # the immutable raw source, exactly like a field that was never
        # populated.  ``needs_display_repair`` already flags this field
        # regardless (it fails ``validate_display_contract``); only what the
        # model is shown as "current" changes here.
        text = str(display_value or "")
        return "" if _is_garbled_legacy_dollar_soup(text) else text

    if qt:
        context_fields["question"] = str(qt)
        current_displays["question"] = shown_current(question_latex)
        if needs_display_repair("question", qt, question_latex):
            output_fields["question"] = {"raw": str(qt), "current": shown_current(question_latex)}
    if ans:
        context_fields["answer"] = str(ans)
        current_displays["answer"] = shown_current(correct_answer_latex)
        if needs_display_repair("answer", ans, correct_answer_latex):
            output_fields["answer"] = {"raw": str(ans), "current": shown_current(correct_answer_latex)}

    dmeta = []
    if dmeta_json:
        try:
            dmeta = json.loads(dmeta_json) if isinstance(dmeta_json, str) else dmeta_json
            if isinstance(dmeta, list):
                for i, d in enumerate(dmeta):
                    if not isinstance(d, dict):
                        continue
                    value = str(d.get("value") or d.get("text") or d.get("content") or "").strip()
                    value_latex = str(d.get("value_latex") or d.get("text_latex") or d.get("content_latex") or "").strip()
                    if value:
                        context_fields[f"dmeta[{i}].value"] = value
                        current_displays[f"dmeta[{i}].value"] = shown_current(value_latex)
                        if needs_display_repair(f"dmeta[{i}].value", value, value_latex):
                            output_fields[f"dmeta[{i}].value"] = {"raw": value, "current": shown_current(value_latex)}

                    # explanation is a documented legacy mirror of
                    # error_logic, not a second user-facing description.
                    # Prefer the pedagogical error_logic and fall back only
                    # when legacy content has no such key.
                    source_key, display_key = (
                        ("error_logic", "error_logic_latex")
                        if str(d.get("error_logic") or "").strip()
                        else ("explanation", "explanation_latex")
                    )
                    description = str(d.get(source_key) or "").strip()
                    display = str(d.get(display_key) or "").strip()
                    if description:
                        context_fields[f"dmeta[{i}].description"] = description
                        current_displays[f"dmeta[{i}].description"] = shown_current(display)
                        if needs_display_repair(f"dmeta[{i}].description", description, display):
                            output_fields[f"dmeta[{i}].description"] = {"raw": description, "current": shown_current(display)}
        except Exception as e:
            log.error("Failed to parse dmeta for %s: %s", tid, e)

    raw_options = answer_options if isinstance(answer_options, list) else []
    display_options = answer_options_latex if isinstance(answer_options_latex, list) else []
    for i, option in enumerate(raw_options):
        if isinstance(option, dict):
            value = str(option.get("value") or option.get("text") or option.get("content") or "").strip()
        else:
            value = str(option or "").strip()
        if not value:
            continue
        label = f"option[{i}]"
        context_fields[label] = value
        display = str(display_options[i] or "").strip() if i < len(display_options) else ""
        current_displays[label] = shown_current(display)
        if needs_display_repair(label, value, display):
            output_fields[label] = {"raw": value, "current": shown_current(display)}

    queued_at = time.monotonic()
    field_results, llm_seconds = await format_task_bundle(
        context_fields, current_displays, output_fields, semaphore, request_pacer,
        llm_self_review=llm_self_review,
    )
    for label, result in field_results.items():
        if not field_is_acceptable(result):
            log.info(
                "LaTeX held for review: task=%s field=%s first_pass_ok=%s reason=%s",
                tid,
                label,
                result.get("llm_self_review_first_pass_acceptable"),
                field_failure_reason(result),
            )
    total_bundle_seconds = time.monotonic() - queued_at

    return {
        "task_id": tid,
        "original": {
            "question": qt,
            "question_latex": question_latex,
            "answer": ans,
            "correct_answer_latex": correct_answer_latex,
            "answer_options": answer_options,
            "answer_options_latex": answer_options_latex,
        },
        "field_results": field_results,
        "llm_seconds": llm_seconds,
        "queue_seconds": max(0.0, total_bundle_seconds - llm_seconds) if output_fields else 0.0,
        # Preserve the exact DB representation for the optimistic display
        # check and write path. In particular, SQL NULL must not silently turn
        # into an empty JSON array in the raw distractor_meta column.
        "dmeta_original": copy.deepcopy(dmeta_json),
        "canonical_fingerprint": canonical_fingerprint(qt, ans, dmeta, raw_options),
        "run_context": copy.deepcopy(run_context) if run_context else None,
    }


# ═══════════════════════════════════════════════════════════════
# ЗАПИСЬ В БД: изменяются строго display-поля. Перед записью и под
# row-lock проверяем canonical fingerprint, поэтому raw-контент не может
# быть случайно переписан даже при конкурентной правке задания.
# ═══════════════════════════════════════════════════════════════

_DISPLAY_DMETA_SUFFIX = "_latex"


def _canonical_dmeta(dmeta):
    """Return distractors without derived display values, preserving raw data."""
    if not isinstance(dmeta, list):
        return dmeta
    return [
        {
            key: value
            for key, value in item.items()
            if not str(key).endswith(_DISPLAY_DMETA_SUFFIX)
        }
        if isinstance(item, dict) else item
        for item in dmeta
    ]


def _canonical_options(options):
    if not isinstance(options, list):
        return options
    return [
        {
            key: value
            for key, value in item.items()
            if not str(key).endswith("_latex") and str(key) != "latex"
        }
        if isinstance(item, dict) else item
        for item in options
    ]


def canonical_fingerprint(question_text, correct_answer, distractor_meta, answer_options=None) -> str:
    """Stable proof that the educational source data was not changed."""
    payload = {
        "question_text": question_text or "",
        "correct_answer": correct_answer or "",
        # PostgreSQL JSONB NULL and an empty JSON array both mean that this
        # task has no distractors. ``process_task`` works with an empty list,
        # so the lock-time comparison must use the same canonical form.
        "distractor_meta": _canonical_dmeta(distractor_meta if distractor_meta is not None else []),
        "answer_options": _canonical_options(answer_options or []),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def display_snapshot(
    question_latex: object,
    correct_answer_latex: object,
    distractor_meta: object,
    answer_options_latex: object,
    latex_status: object,
) -> dict[str, object]:
    """Capture exactly the learner-facing columns a backfill may replace.

    Raw source fields intentionally do not appear here. Their immutable
    fingerprint is stored alongside the snapshot, which makes a restore fail
    safely if a human changed the educational source in the meantime.
    """
    return {
        "question_latex": copy.deepcopy(question_latex),
        "correct_answer_latex": copy.deepcopy(correct_answer_latex),
        "distractor_meta": copy.deepcopy(distractor_meta),
        "answer_options_latex": copy.deepcopy(answer_options_latex),
        "latex_status": str(latex_status) if latex_status is not None else None,
    }


def display_snapshot_fingerprint(snapshot: dict[str, object]) -> str:
    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _field_audit_payload(field_results: dict[str, dict]) -> dict[str, dict]:
    """Persist decision evidence without storing raw prompts or model replies."""
    keep = (
        "decision", "confidence", "ambiguity_reason", "katex_ok", "katex_error",
        "contract_ok", "contract_error", "professional_ok", "professional_error",
        "semantic_ok", "semantic_error", "requires_explicit_final_review",
        "response_protocol", "llm_self_review_required", "llm_self_review_ok",
        "llm_self_review_attempts", "llm_repair_attempts", "final_review", "llm_trace",
        "projection_source",
    )
    return {
        label: {key: copy.deepcopy(value[key]) for key in keep if key in value}
        for label, value in field_results.items()
    }


def record_latex_change_audit(
    conn,
    result: dict,
    before_snapshot: dict[str, object],
    after_snapshot: dict[str, object],
    review_issues: dict[str, dict[str, str]],
    *,
    event_type: str = "write",
    rollback_of: str | None = None,
) -> str | None:
    """Append a revision in the same transaction as the display update.

    Unit-level callers without a run context intentionally remain side-effect
    free. Production ``--execute`` always supplies one and therefore requires
    the migration-created audit tables to be present.
    """
    run_context = result.get("run_context") or {}
    run_id = run_context.get("run_id")
    if not run_id:
        return None
    audit_id = str(uuid.uuid4())
    validation = {
        "field_results": _field_audit_payload(result.get("field_results") or {}),
        "final_review_issues": copy.deepcopy(review_issues),
        "stored_status": result.get("stored_status"),
        "model": run_context.get("model", LATEX_BACKFILL_MODEL),
        "prompt_version": run_context.get("prompt_version", LATEX_BACKFILL_PROMPT_VERSION),
        "policy_version": run_context.get("policy_version", LATEX_BACKFILL_POLICY_VERSION),
    }
    conn.execute(text("""
        INSERT INTO task_latex_change_audit (
            audit_id, run_id, task_id, event_type, rollback_of,
            source_fingerprint_sha256, before_snapshot, after_snapshot,
            before_display_sha256, after_display_sha256, validation
        ) VALUES (
            :audit_id, :run_id, :task_id, :event_type, :rollback_of,
            :source_fingerprint, CAST(:before_snapshot AS jsonb), CAST(:after_snapshot AS jsonb),
            :before_display_fingerprint, :after_display_fingerprint, CAST(:validation AS jsonb)
        )
    """), {
        "audit_id": audit_id,
        "run_id": str(run_id),
        "task_id": str(result["task_id"]),
        "event_type": event_type,
        "rollback_of": rollback_of,
        "source_fingerprint": result["canonical_fingerprint"],
        "before_snapshot": json.dumps(before_snapshot, ensure_ascii=False, default=str),
        "after_snapshot": json.dumps(after_snapshot, ensure_ascii=False, default=str),
        "before_display_fingerprint": display_snapshot_fingerprint(before_snapshot),
        "after_display_fingerprint": display_snapshot_fingerprint(after_snapshot),
        "validation": json.dumps(validation, ensure_ascii=False, default=str),
    })
    result["audit_id"] = audit_id
    return audit_id


def _string_display_value(value: object) -> str:
    """Preserve an exact scalar display/source value for an attestation."""
    return "" if value is None else str(value)


def _dmeta_value(item: object) -> str:
    if not isinstance(item, dict):
        return ""
    for key in ("value", "text", "content"):
        if item.get(key) is not None:
            return _string_display_value(item[key])
    return ""


def _dmeta_display_value(item: object) -> str:
    if not isinstance(item, dict):
        return ""
    for key in ("value_latex", "text_latex", "content_latex"):
        if item.get(key) is not None:
            return _string_display_value(item[key])
    return ""


def _attestation_source_display_pair(
    result: dict, after_snapshot: dict[str, object], label: str,
) -> tuple[str, str] | None:
    """Return the exact raw/display pair for one independently reviewed field.

    This deliberately models fields, not a task-wide status.  A good question
    must remain eligible even if an unrelated distractor explanation still
    needs manual review, while an editor changing this exact field invalidates
    the attestation at read time.
    """
    original = result.get("original") or {}
    if label == "question":
        return (
            _string_display_value(original.get("question")),
            _string_display_value(after_snapshot.get("question_latex")),
        )
    if label == "answer":
        return (
            _string_display_value(original.get("answer")),
            _string_display_value(after_snapshot.get("correct_answer_latex")),
        )

    dmeta_match = re.fullmatch(r"dmeta\[(\d+)\]\.(value|description)", label)
    if dmeta_match:
        index, part = int(dmeta_match.group(1)), dmeta_match.group(2)
        raw_items = _json_list(result.get("dmeta_original"))
        display_items = _json_list(after_snapshot.get("distractor_meta"))
        if index >= len(raw_items) or index >= len(display_items):
            return None
        raw_item, display_item = raw_items[index], display_items[index]
        if part == "value":
            return _dmeta_value(raw_item), _dmeta_display_value(display_item)
        if not isinstance(raw_item, dict) or not isinstance(display_item, dict):
            return None
        source_key, display_key = (
            ("error_logic", "error_logic_latex")
            if _string_display_value(raw_item.get("error_logic")).strip()
            else ("explanation", "explanation_latex")
        )
        return (
            _string_display_value(raw_item.get(source_key)),
            _string_display_value(display_item.get(display_key)),
        )

    option_match = re.fullmatch(r"option\[(\d+)\]", label)
    if option_match:
        index = int(option_match.group(1))
        raw_options = _json_list(original.get("answer_options"))
        display_options = _json_list(after_snapshot.get("answer_options_latex"))
        if index >= len(raw_options) or index >= len(display_options):
            return None
        raw_option = raw_options[index]
        raw_value = _dmeta_value(raw_option) if isinstance(raw_option, dict) else _string_display_value(raw_option)
        return raw_value, _string_display_value(display_options[index])
    return None


def _attestation_is_eligible(field: dict) -> bool:
    """A trusted projection requires a structured independent final review."""
    final_review = field.get("final_review") or {}
    return (
        field_is_acceptable(field)
        and field.get("response_protocol", "structured") == "structured"
        and final_review.get("required") is True
        and final_review.get("completed") is True
        and final_review.get("accepted") is True
    )


def record_latex_projection_attestations(
    conn,
    result: dict,
    after_snapshot: dict[str, object],
    *,
    audit_id: str | None,
) -> list[str]:
    """Append field-level evidence for projections safe to render as trusted.

    The API never trusts historical ``latex_status``.  It compares the current
    raw/display values to the exact pair recorded here, and only then exposes
    a readiness flag to the frontend.  This write happens in the same
    transaction as its display revision (or a successful no-op review).
    """
    run_context = result.get("run_context") or {}
    run_id = run_context.get("run_id")
    if not run_id:
        return []

    recorded: list[str] = []
    for label, field in (result.get("field_results") or {}).items():
        if not _attestation_is_eligible(field):
            continue
        pair = _attestation_source_display_pair(result, after_snapshot, label)
        if pair is None:
            log.warning("No field pair for LaTeX projection attestation task=%s field=%s", result["task_id"], label)
            continue
        source_value, display_value = pair
        if display_value != _string_display_value(field.get("canonical")):
            log.warning(
                "Refusing mismatched LaTeX projection attestation task=%s field=%s",
                result["task_id"], label,
            )
            continue

        # A new independent review supersedes only the attestation for this
        # field. Other fields in the task can remain safely renderable.
        conn.execute(text("""
            UPDATE task_latex_display_attestations
            SET status = 'revoked', revoked_at = NOW(),
                revocation_reason = 'superseded_by_new_final_review'
            WHERE task_id = :task_id
              AND field_key = :field_key
              AND status = 'active'
        """), {"task_id": str(result["task_id"]), "field_key": label})

        attestation_id = str(uuid.uuid4())
        review_metadata = _field_audit_payload({label: field})[label]
        conn.execute(text("""
            INSERT INTO task_latex_display_attestations (
                attestation_id, task_id, field_key, run_id, audit_id, status,
                source_value, display_value, source_sha256, display_sha256,
                review_metadata
            ) VALUES (
                :attestation_id, :task_id, :field_key, :run_id, :audit_id, 'active',
                :source_value, :display_value, :source_sha256, :display_sha256,
                CAST(:review_metadata AS jsonb)
            )
        """), {
            "attestation_id": attestation_id,
            "task_id": str(result["task_id"]),
            "field_key": label,
            "run_id": str(run_id),
            "audit_id": audit_id,
            "source_value": source_value,
            "display_value": display_value,
            "source_sha256": hashlib.sha256(source_value.encode("utf-8")).hexdigest(),
            "display_sha256": hashlib.sha256(display_value.encode("utf-8")).hexdigest(),
            "review_metadata": json.dumps(review_metadata, ensure_ascii=False, default=str),
        })
        recorded.append(label)
    result["projection_attestations"] = recorded
    return recorded


def revoke_latex_projection_attestations(conn, task_id: str, reason: str) -> None:
    """Safely withdraw all trusted projections before an audited rollback."""
    conn.execute(text("""
        UPDATE task_latex_display_attestations
        SET status = 'revoked', revoked_at = NOW(), revocation_reason = :reason
        WHERE task_id = :task_id
          AND status = 'active'
    """), {"task_id": str(task_id), "reason": str(reason)[:240]})


def _json_list(value: object) -> list:
    """Read a JSONB/list value without treating malformed data as display-safe."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def final_display_issues(
    question_text: object,
    question_latex: object,
    correct_answer: object,
    correct_answer_latex: object,
    distractor_meta: object,
    answer_options: object,
    answer_options_latex: object,
) -> tuple[dict[str, dict[str, str]], int]:
    """Certify the complete stored RAW -> LaTeX projection.

    This is deliberately shared by the backfill writer and Smart Verify.  A
    task is never promoted merely because a field is non-empty: every display
    value must parse, meet its rendering contract and satisfy the house style.
    Meaning is decided by the mandatory model self-review because historical
    source strings contain context-dependent OCR and delimiter damage.
    """
    issues: dict[str, dict[str, str]] = {}
    required_labels: set[str] = set()

    def check(label: str, source: object, display: object) -> None:
        raw_text = str(source or "").strip()
        if not raw_text:
            return
        required_labels.add(label)
        display_text = str(display or "").strip()
        if not display_text:
            issues[label] = {"reason": "missing_display_value", "confidence": "low"}
            return
        katex_ok, katex_error = validate_with_katex(display_text)
        contract_ok, contract_error = validate_display_contract(label, raw_text, display_text)
        professional_ok, professional_error = validate_professional_latex(display_text)
        # Retain this comparison for observability and prompt diagnostics, but
        # do not let a token-level heuristic overrule the model's contextual
        # review of legacy OCR/formatting defects.
        _semantic_ok, _semantic_error = semantic_preservation_check(
            raw_text, display_text, allow_legacy_markup_repair=True,
        )
        if not (katex_ok and contract_ok and professional_ok):
            issues[label] = {
                "reason": contract_error or professional_error or katex_error or "invalid_display_value",
                "confidence": "low",
            }

    check("question", question_text, question_latex)
    check("answer", correct_answer, correct_answer_latex)
    for idx, item in enumerate(_json_list(distractor_meta)):
        if not isinstance(item, dict):
            continue
        value = str(item.get("value") or item.get("text") or item.get("content") or "").strip()
        value_latex = str(item.get("value_latex") or item.get("text_latex") or item.get("content_latex") or "").strip()
        check(f"dmeta[{idx}].value", value, value_latex)
        source_key, display_key = (
            ("error_logic", "error_logic_latex")
            if str(item.get("error_logic") or "").strip()
            else ("explanation", "explanation_latex")
        )
        check(f"dmeta[{idx}].description", item.get(source_key), item.get(display_key))

    raw_options = _json_list(answer_options)
    display_options = _json_list(answer_options_latex)
    for idx, option in enumerate(raw_options):
        value = (
            str(option.get("value") or option.get("text") or option.get("content") or "").strip()
            if isinstance(option, dict) else str(option or "").strip()
        )
        display = str(display_options[idx] or "").strip() if idx < len(display_options) else ""
        check(f"option[{idx}]", value, display)
    return issues, len(required_labels)


def latex_status_from_issues(issues: dict[str, dict[str, str]], required_count: int) -> str:
    if not issues:
        return "verified"
    return "failed" if required_count and len(issues) == required_count else "partial"


def sync_latex_review_queue(conn, task_id: object, status: str, issues: dict[str, dict[str, str]]) -> None:
    """Keep review diagnostics aligned with the currently stored display data."""
    if status == "verified":
        conn.execute(text("""
            UPDATE review_queue
            SET status = 'resolved'
            WHERE item_type = 'task'
              AND item_id = :tid
              AND status = 'pending'
              AND review_reason IN (
                  'latex_backfill_field_failed',
                  'answer_options_latex_backfill_failed'
              )
        """), {"tid": str(task_id)})
        return
    if not issues:
        return
    suggestion = json.dumps(issues, ensure_ascii=False)
    conn.execute(text("""
        UPDATE review_queue
        SET ai_suggestion = :suggestion,
            priority = 'high'
        WHERE item_type = 'task'
          AND item_id = :tid
          AND review_reason = 'latex_backfill_field_failed'
          AND status = 'pending'
    """), {"tid": str(task_id), "suggestion": suggestion})
    conn.execute(text("""
        INSERT INTO review_queue (item_type, item_id, review_reason, priority, status, ai_suggestion)
        SELECT 'task', :tid, 'latex_backfill_field_failed', 'high', 'pending', :suggestion
        WHERE NOT EXISTS (
            SELECT 1 FROM review_queue
            WHERE item_type = 'task'
              AND item_id = :tid
              AND review_reason = 'latex_backfill_field_failed'
              AND status = 'pending'
        )
    """), {"tid": str(task_id), "suggestion": suggestion})


def recertify_stored_latex_status(conn, task_id: object) -> tuple[str, dict[str, dict[str, str]]]:
    """Recompute one stored task after an external writer changed display data.

    It never writes RAW educational columns.  Call it in the same transaction
    as Smart Verify so a completed distractor update cannot leave stale
    ``latex_status='partial'`` behind.
    """
    row = conn.execute(text("""
        SELECT question_text, question_latex, correct_answer,
               correct_answer_latex, distractor_meta, answer_options,
               answer_options_latex, latex_status
        FROM tasks_master
        WHERE id = :id
        FOR UPDATE
    """), {"id": task_id}).fetchone()
    if row is None:
        raise RuntimeError(f"Task {task_id} disappeared before LaTeX recertification")
    issues, required_count = final_display_issues(*row[:7])
    status = latex_status_from_issues(issues, required_count)
    if row[7] != status:
        conn.execute(text("""
            UPDATE tasks_master
            SET latex_status = :status,
                latex_normalized_at = NOW()
            WHERE id = :id
        """), {"id": task_id, "status": status})
    sync_latex_review_queue(conn, task_id, status, issues)
    return status, issues


class ConcurrentTaskChangeError(RuntimeError):
    """The row changed after it was read; stale display output must not be saved."""

def resolve_projected_outcome(result: dict) -> tuple[str, dict[str, dict[str, str]], int, dict[str, dict], dict[str, object]]:
    """Determine the final stored display values and resulting latex_status.

    Shared between save_result and dry-run accounting so that preview numbers
    precisely mirror actual database outcomes.
    """
    fr = result.get("field_results") or {}
    original_dmeta_snapshot = copy.deepcopy(result.get("dmeta_original"))
    dmeta = [] if original_dmeta_snapshot is None else copy.deepcopy(original_dmeta_snapshot)
    failed_fields = {}

    def resolve(label, original_value):
        r = fr.get(label)
        if r is None:
            norm_orig = _normalize_candidate_markup(label, str(original_value or "")) if original_value else original_value
            return (norm_orig if norm_orig else original_value), True
        if field_is_acceptable(r):
            return r["canonical"], True
        failed_fields[label] = {
            "reason": field_failure_reason(r),
            "confidence": r.get("confidence", "low"),
        }
        return original_value, False

    new_question, _ = resolve("question", result["original"]["question_latex"])
    new_answer, _ = resolve("answer", result["original"]["correct_answer_latex"])

    for i, d in enumerate(dmeta):
        if not isinstance(d, dict):
            continue
        existing_val_latex = d.get("value_latex") or d.get("text_latex") or d.get("content_latex")
        val_to_resolve = existing_val_latex if existing_val_latex else (d.get("value") or d.get("text") or d.get("content"))
        new_val, ok = resolve(f"dmeta[{i}].value", val_to_resolve)
        if ok and new_val:
            d["value_latex"] = new_val
        source_key, display_key = (
            ("error_logic", "error_logic_latex")
            if str(d.get("error_logic") or "").strip()
            else ("explanation", "explanation_latex")
        )
        existing_desc = d.get(display_key) or d.get("explanation_latex") or d.get("error_logic_latex")
        val_to_resolve = existing_desc if existing_desc else (d.get(source_key) or d.get("explanation") or d.get("error_logic"))
        new_description, ok = resolve(f"dmeta[{i}].description", val_to_resolve)
        if ok and new_description:
            d[display_key] = new_description

    raw_options = result["original"].get("answer_options")
    raw_options = raw_options if isinstance(raw_options, list) else []
    original_option_latex = result["original"].get("answer_options_latex")
    original_option_latex = original_option_latex if isinstance(original_option_latex, list) else []
    new_options_latex: list[str] = []
    for i, _option in enumerate(raw_options):
        original_display = (
            str(original_option_latex[i] or "").strip()
            if i < len(original_option_latex) else ""
        )
        opt_to_resolve = original_display if original_display else str(_option or "").strip()
        new_display, ok = resolve(f"option[{i}]", opt_to_resolve)
        new_options_latex.append(new_display if ok else (original_display or str(_option or "").strip()))

    final_issues, final_required_count = final_display_issues(
        result["original"]["question"], new_question,
        result["original"]["answer"], new_answer,
        dmeta, raw_options, new_options_latex,
    )
    status = latex_status_from_issues(final_issues, final_required_count)
    resolved = {
        "new_question": new_question,
        "new_answer": new_answer,
        "dmeta": dmeta,
        "new_options_latex": new_options_latex,
        "raw_options": raw_options,
    }
    return status, final_issues, final_required_count, failed_fields, resolved


def save_result(conn, result: dict):
    tid = result["task_id"]
    fr = result.get("field_results") or {}
    status, final_issues, final_required_count, failed_fields, resolved = resolve_projected_outcome(result)
    new_question = resolved["new_question"]
    new_answer = resolved["new_answer"]
    dmeta = resolved["dmeta"]
    new_options_latex = resolved["new_options_latex"]
    raw_options = resolved["raw_options"]

    total_attempted = len(fr)
    total_failed = len(failed_fields)

    if canonical_fingerprint(
        result["original"]["question"], result["original"]["answer"], dmeta, raw_options,
    ) != result["canonical_fingerprint"]:
        raise RuntimeError(f"Canonical data changed in memory for task {tid}; refusing to write")

    # Lock and compare source data immediately before the update. This protects
    # a human/editor update that happened after the backfill selected this row.
    current = conn.execute(text("""
        SELECT question_text, correct_answer, distractor_meta, answer_options,
               question_latex, correct_answer_latex, answer_options_latex,
               latex_status
        FROM tasks_master
        WHERE id = :id
        FOR UPDATE
    """), {"id": tid}).fetchone()
    if current is None:
        raise RuntimeError(f"Task {tid} disappeared before backfill write")
    if canonical_fingerprint(current[0], current[1], current[2], current[3]) != result["canonical_fingerprint"]:
        raise ConcurrentTaskChangeError(
            f"Canonical data changed concurrently for task {tid}; refusing to write"
        )

    # Do not overwrite a display edit made after this task was selected.
    original_dmeta = result.get("dmeta_original")
    if (
        current[2] != original_dmeta
        or current[4] != result["original"]["question_latex"]
        or current[5] != result["original"]["correct_answer_latex"]
        or current[6] != result["original"].get("answer_options_latex")
    ):
        raise ConcurrentTaskChangeError(
            f"Display data changed concurrently for task {tid}; refusing to write"
        )

    result["stored_status"] = status
    dmeta_for_storage = None if original_dmeta is None else dmeta
    displays_unchanged = (
        current[2] == dmeta_for_storage
        and current[4] == new_question
        and current[5] == new_answer
        and current[6] == new_options_latex
        and current[7] == status
    )
    review_issues = copy.deepcopy(final_issues)
    # Preserve both truths: why the final stored value is still invalid and
    # why this particular LLM attempt was discarded.  Without this, an old
    # pending review row could misleadingly continue to report a timeout after
    # a later attempt failed for a different, field-specific reason.
    for label, issue in review_issues.items():
        attempted = failed_fields.get(label)
        if attempted:
            issue["attempt_reason"] = attempted["reason"]

    if displays_unchanged and not review_issues:
        # A successful KEEP audit must not physically rewrite already-correct
        # display data or move latex_normalized_at for no reason.  It can still
        # produce a new field-level trust attestation: the model independently
        # reviewed this exact unchanged projection in the current run.
        unchanged_snapshot = display_snapshot(
            new_question, new_answer, dmeta_for_storage, new_options_latex, status,
        )
        attested_labels = record_latex_projection_attestations(
            conn, result, unchanged_snapshot, audit_id=None,
        )
        if attested_labels:
            conn.execute(text("""
                UPDATE tasks_master
                SET tags = jsonb_set(
                    jsonb_set(
                        COALESCE(tags, '{}'::jsonb),
                        '{latex_attested_fields}',
                        CAST(:attested_json AS jsonb)
                    ),
                    '{content_quality,latex_attested_fields}',
                    CAST(:attested_json AS jsonb)
                )
                WHERE id = :id
            """), {"id": tid, "attested_json": json.dumps(attested_labels)})
        sync_latex_review_queue(conn, tid, status, review_issues)
        result["database_write"] = "skipped_unchanged"
        return

    before_snapshot = display_snapshot(
        current[4], current[5], current[2], current[6], current[7],
    )
    after_snapshot = display_snapshot(
        new_question, new_answer, dmeta_for_storage, new_options_latex, status,
    )

    # ВАЖНО: question_text / correct_answer и raw distractor fields НЕ трогаем.
    conn.execute(text("""
        UPDATE tasks_master
        SET question_latex = :ql,
            correct_answer_latex = :cal,
            distractor_meta = :dmeta,
            answer_options_latex = :aol,
            latex_status = :status,
            latex_normalized_at = NOW()
        WHERE id = :id
    """), {
        "ql": new_question,
        "cal": new_answer,
        "dmeta": (
            json.dumps(dmeta_for_storage, ensure_ascii=False)
            if dmeta_for_storage is not None else None
        ),
        "aol": json.dumps(new_options_latex, ensure_ascii=False),
        "status": status,
        "id": tid,
    })
    result["database_write"] = "updated"
    audit_id = record_latex_change_audit(
        conn, result, before_snapshot, after_snapshot, review_issues,
    )
    attested_labels = record_latex_projection_attestations(
        conn, result, after_snapshot, audit_id=audit_id,
    )
    if attested_labels:
        conn.execute(text("""
            UPDATE tasks_master
            SET tags = jsonb_set(
                jsonb_set(
                    COALESCE(tags, '{}'::jsonb),
                    '{latex_attested_fields}',
                    CAST(:attested_json AS jsonb)
                ),
                '{content_quality,latex_attested_fields}',
                CAST(:attested_json AS jsonb)
            )
            WHERE id = :id
        """), {"id": tid, "attested_json": json.dumps(attested_labels)})
    sync_latex_review_queue(conn, tid, status, review_issues)


def start_latex_backfill_run(engine, run_context: dict) -> None:
    """Create the durable manifest before the first display write."""
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO latex_backfill_runs (
                run_id, label, actor, status, model, prompt_version,
                policy_version, config, queue_sha256
            ) VALUES (
                :run_id, :label, :actor, 'running', :model, :prompt_version,
                :policy_version, CAST(:config AS jsonb), :queue_sha256
            )
        """), {
            "run_id": run_context["run_id"],
            "label": run_context["label"],
            "actor": run_context["actor"],
            "model": run_context["model"],
            "prompt_version": run_context["prompt_version"],
            "policy_version": run_context["policy_version"],
            "config": json.dumps(run_context["config"], ensure_ascii=False, sort_keys=True),
            "queue_sha256": run_context.get("queue_sha256"),
        })


def finish_latex_backfill_run(engine, run_context: dict, status: str, summary: dict) -> None:
    """Close a manifest regardless of whether records needed manual review."""
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE latex_backfill_runs
            SET status = :status,
                summary = CAST(:summary AS jsonb),
                finished_at = NOW()
            WHERE run_id = :run_id
              AND status = 'running'
        """), {
            "run_id": run_context["run_id"],
            "status": status,
            "summary": json.dumps(summary, ensure_ascii=False, sort_keys=True),
        })


def _snapshot_as_jsonb(value: object) -> str | None:
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def rollback_latex_backfill_run(
    engine,
    source_run_id: str,
    rollback_context: dict | None,
    *,
    dry_run: bool,
) -> dict[str, int]:
    """Restore one run's display snapshots without overwriting newer work.

    Each task is locked and checked against both the raw-source fingerprint and
    the exact display fingerprint produced by the audited run. A later editor
    or backfill change therefore becomes a visible conflict rather than an
    accidental overwrite.
    """
    with engine.connect() as conn:
        events = conn.execute(text("""
            SELECT audit_id, task_id, source_fingerprint_sha256,
                   before_snapshot, after_snapshot, after_display_sha256
            FROM task_latex_change_audit
            WHERE run_id = :run_id
              AND event_type = 'write'
              AND NOT EXISTS (
                  SELECT 1
                  FROM task_latex_change_audit rollback_event
                  WHERE rollback_event.rollback_of = task_latex_change_audit.audit_id
              )
            ORDER BY created_at DESC
        """), {"run_id": source_run_id}).fetchall()

    summary = {"eligible": 0, "restored": 0, "conflicts": 0, "already_rolled_back": 0}
    for audit_id, task_id, source_sha, before, _after, after_sha in events:
        with engine.begin() as conn:
            row = conn.execute(text("""
                SELECT question_text, correct_answer, distractor_meta, answer_options,
                       question_latex, correct_answer_latex, answer_options_latex,
                       latex_status
                FROM tasks_master
                WHERE id = :id
                FOR UPDATE
            """), {"id": task_id}).fetchone()
            if row is None:
                summary["conflicts"] += 1
                continue
            current_source_sha = canonical_fingerprint(row[0], row[1], row[2], row[3])
            current_display = display_snapshot(row[4], row[5], row[2], row[6], row[7])
            if current_source_sha != source_sha or display_snapshot_fingerprint(current_display) != after_sha:
                summary["conflicts"] += 1
                continue
            summary["eligible"] += 1
            if dry_run:
                continue
            if not isinstance(before, dict):
                raise RuntimeError(f"Audit {audit_id} has no valid before snapshot")
            restored_question = before.get("question_latex")
            restored_answer = before.get("correct_answer_latex")
            restored_dmeta = before.get("distractor_meta")
            restored_options = before.get("answer_options_latex")
            issues, required_count = final_display_issues(
                row[0], restored_question, row[1], restored_answer,
                restored_dmeta, row[3], restored_options,
            )
            restored_status = latex_status_from_issues(issues, required_count)
            restored_snapshot = display_snapshot(
                restored_question, restored_answer, restored_dmeta,
                restored_options, restored_status,
            )
            # A rollback deliberately changes the learner-facing projection.
            # Even a prior independently reviewed field can no longer be
            # trusted until the restored value passes a fresh final review.
            revoke_latex_projection_attestations(
                conn, str(task_id), f"rolled_back_audit:{audit_id}",
            )
            conn.execute(text("""
                UPDATE tasks_master
                SET question_latex = :question_latex,
                    correct_answer_latex = :correct_answer_latex,
                    distractor_meta = CAST(:distractor_meta AS jsonb),
                    answer_options_latex = CAST(:answer_options_latex AS jsonb),
                    latex_status = :latex_status,
                    tags = (COALESCE(tags, '{}'::jsonb) - 'latex_attested_fields')
                           #- '{content_quality,latex_attested_fields}',
                    latex_normalized_at = NOW(),
                    updated_at = NOW()
                WHERE id = :id
            """), {
                "id": task_id,
                "question_latex": restored_question,
                "correct_answer_latex": restored_answer,
                "distractor_meta": _snapshot_as_jsonb(restored_dmeta),
                "answer_options_latex": _snapshot_as_jsonb(restored_options),
                "latex_status": restored_status,
            })
            rollback_result = {
                "task_id": str(task_id),
                "canonical_fingerprint": current_source_sha,
                "field_results": {},
                "stored_status": restored_status,
                "run_context": rollback_context,
            }
            record_latex_change_audit(
                conn, rollback_result, current_display, restored_snapshot, issues,
                event_type="rollback", rollback_of=str(audit_id),
            )
            sync_latex_review_queue(conn, task_id, restored_status, issues)
            summary["restored"] += 1
    return summary


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def build_task_filter(task_ids: list[str], *, exact_set_mode: bool = False) -> str:
    """Build a safe SQL predicate for optional or exact task selections.

    Maintenance modes own an exact precomputed set.  An empty exact set must
    therefore match nothing; silently dropping the predicate would fall back
    to the ordinary queue and process unrelated tasks.
    """
    if task_ids:
        return "AND tm.id = ANY(:task_ids)"
    return "AND FALSE" if exact_set_mode else ""


def load_audit_display_selection(path: str) -> tuple[list[str], dict[str, str], str]:
    """Load an immutable display-repair selection exported by the audit.

    The writer must never infer a production queue from a broad maintenance
    switch: the read-only audit is the source of truth.  Status-only records
    are deliberately excluded because they do not need an LLM call. The raw
    fingerprint at audit time is retained and checked before asking the model
    to touch a task; an edited source must receive a fresh audit instead.
    """
    try:
        with open(path, "rb") as handle:
            payload = handle.read()
        audit = json.loads(payload.decode("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read audit queue file: {exc}") from exc
    if not isinstance(audit, dict) or audit.get("mode") != "read_only":
        raise ValueError("Audit queue must be a read-only audit JSON document")
    records = audit.get("records")
    if not isinstance(records, list):
        raise ValueError("Audit queue does not contain a records list")
    ids: list[str] = []
    seen: set[str] = set()
    fingerprints: dict[str, str] = {}
    for record in records:
        if not isinstance(record, dict) or record.get("kind") != "display_repair":
            continue
        task_id = str(record.get("task_id") or "").strip()
        if not task_id:
            raise ValueError("Audit queue contains a display-repair record without task_id")
        audit_fingerprint = str(record.get("canonical_fingerprint_sha256") or "").strip()
        if audit_fingerprint and not re.fullmatch(r"[0-9a-f]{64}", audit_fingerprint):
            raise ValueError(f"Audit queue contains an invalid fingerprint for task {task_id}")
        if task_id in fingerprints and audit_fingerprint and fingerprints[task_id] != audit_fingerprint:
            raise ValueError(f"Audit queue contains conflicting fingerprints for task {task_id}")
        if audit_fingerprint:
            fingerprints[task_id] = audit_fingerprint
        if task_id not in seen:
            seen.add(task_id)
            ids.append(task_id)
    if not ids:
        raise ValueError("Audit queue contains no display-repair tasks")
    return ids, fingerprints, hashlib.sha256(payload).hexdigest()


def load_audit_display_ids(path: str) -> list[str]:
    """Compatibility helper for callers that need only the ordered IDs."""
    return load_audit_display_selection(path)[0]

async def main():
    run_started_at = time.monotonic()
    ap = argparse.ArgumentParser()
    ap.add_argument("--class-level", type=int)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=8, help="Макс. одновременных запросов DeepSeek (по задачам)")
    ap.add_argument(
        "--requests-per-minute", type=int, default=240,
        help="Ровный лимит стартов запросов DeepSeek в минуту (1–250; по умолчанию 240)",
    )
    ap.add_argument(
        "--batch-size", type=int, default=25,
        help="Сколько задач составляет один контролируемый терминальный батч (по умолчанию: 25)",
    )
    ap.add_argument("--execute", action="store_true")
    ap.add_argument(
        "--skip-llm-self-review", action="store_true",
        help=(
            "Diagnostic dry-run only: omit the mandatory second DeepSeek review. "
            "This option is forbidden together with --execute."
        ),
    )
    ap.add_argument(
        "--plan-only", action="store_true",
        help="Только построить и вывести точный набор задач; не вызывать LLM и не писать в БД",
    )
    ap.add_argument("--force-reformat", action="store_true", help="Reformat populated display fields; use only after manual review")
    ap.add_argument("--repair-invalid", action="store_true", help="Repair only populated display fields that fail KaTeX validation")
    ap.add_argument(
        "--only-partial",
        action="store_true",
        help="Process only tasks with latex_status=partial and revalidate every display field",
    )
    ap.add_argument(
        "--revalidate-only",
        action="store_true",
        help="Run deterministic gates only; never call LLM or rewrite display fields",
    )
    ap.add_argument(
        "--include-verified",
        action="store_true",
        help="Explicit maintenance override: allow already verified tasks to be selected",
    )
    ap.add_argument(
        "--repair-stale-verified",
        action="store_true",
        help=(
            "Prefilter active verified rows by the current non-KaTeX gates, "
            "then run full repair only for stale rows"
        ),
    )
    ap.add_argument(
        "--revalidate-stale-verified",
        action="store_true",
        help=(
            "Prefilter stale verified rows, then re-certify stored display "
            "fields only (no LLM and no display-content rewrite)"
        ),
    )
    ap.add_argument("--show-samples", type=int, default=10)
    ap.add_argument("--show-full", action="store_true", help="Print complete LLM display text in dry-run output")
    ap.add_argument("--task-id", action="append", default=[], help="Restrict to an exact task ID (repeatable)")
    ap.add_argument(
        "--audit-queue-file",
        help=(
            "Read-only JSON produced by audit_display_quality_queue.py. "
            "Selects exactly its display_repair records and excludes status-only records."
        ),
    )
    ap.add_argument(
        "--include-inactive",
        action="store_true",
        help="Include inactive tasks (is_active=false) matching selection/audit queue",
    )
    ap.add_argument(
        "--run-id",
        help="Optional UUID for this durable manifest; a UUID is generated when omitted.",
    )
    ap.add_argument(
        "--run-label",
        default="latex-display-backfill",
        help="Human-readable label stored with the audit manifest.",
    )
    ap.add_argument(
        "--rollback-run",
        help=(
            "Restore the display snapshots written by one earlier run ID. "
            "Use alone with --execute after a dry-run; newer edits are skipped safely."
        ),
    )
    ap.add_argument(
        "--after-id",
        help="Exclusive lexicographic cursor for a reproducible reviewed batch; print the last processed ID as the next cursor",
    )
    ap.add_argument(
        "--descending",
        action="store_true",
        help="Process task IDs from the end (useful for controlled complex-task batches)",
    )
    args = ap.parse_args()
    if not 1 <= args.requests_per_minute <= 250:
        ap.error("--requests-per-minute must be between 1 and 250")
    if args.execute and args.skip_llm_self_review:
        ap.error("--execute requires the mandatory DeepSeek self-review")
    if args.rollback_run:
        conflicting = (
            args.audit_queue_file or args.task_id or args.class_level or args.after_id
            or args.only_partial or args.force_reformat or args.repair_invalid
            or args.revalidate_only or args.repair_stale_verified
            or args.revalidate_stale_verified or args.include_verified
        )
        if conflicting:
            ap.error("--rollback-run cannot be combined with selection or formatting options")
    audit_source_fingerprints: dict[str, str] = {}
    audit_queue_sha256: str | None = None
    if args.audit_queue_file:
        if args.task_id or args.class_level or args.after_id:
            ap.error("--audit-queue-file owns the exact target set; do not combine it with task/class/cursor filters")
        try:
            args.task_id, audit_source_fingerprints, audit_queue_sha256 = load_audit_display_selection(
                args.audit_queue_file,
            )
        except ValueError as exc:
            ap.error(str(exc))
        args.include_verified = True
        args.repair_invalid = True
        log.info("Загружена точная очередь display_repair из аудита: задач=%d", len(args.task_id))

    db_url = os.environ.get("DATABASE_URL") or "postgresql://algo:algo_password@127.0.0.1:5434/algo_content"
    engine = create_engine(db_url)
    if args.rollback_run:
        rollback_context = None
        if args.execute:
            run_id = args.run_id or str(uuid.uuid4())
            try:
                uuid.UUID(run_id)
            except ValueError:
                ap.error("--run-id must be a UUID")
            rollback_context = {
                "run_id": run_id,
                "label": args.run_label,
                "actor": "latex_backfill_cli",
                "model": LATEX_BACKFILL_MODEL,
                "prompt_version": LATEX_BACKFILL_PROMPT_VERSION,
                "policy_version": LATEX_BACKFILL_POLICY_VERSION,
                "queue_sha256": None,
                "config": {"mode": "rollback", "source_run_id": args.rollback_run},
            }
            start_latex_backfill_run(engine, rollback_context)
        summary = rollback_latex_backfill_run(
            engine, args.rollback_run, rollback_context, dry_run=not args.execute,
        )
        if rollback_context:
            finish_latex_backfill_run(
                engine, rollback_context,
                "completed_with_review" if summary["conflicts"] else "completed",
                summary,
            )
            log.info("Rollback manifest run_id=%s", rollback_context["run_id"])
        log.info(
            "Rollback %s: eligible=%d, restored=%d, conflicts=%d",
            "completed" if args.execute else "dry-run",
            summary["eligible"], summary["restored"], summary["conflicts"],
        )
        return
    stale_verified_mode = (
        args.repair_stale_verified or args.revalidate_stale_verified
    )
    active_filter = "" if (args.include_inactive or args.audit_queue_file or args.task_id) else "AND is_active = TRUE"
    tm_active_filter = "" if (args.include_inactive or args.audit_queue_file or args.task_id) else "AND tm.is_active = true"

    if stale_verified_mode:
        if args.repair_stale_verified and args.revalidate_stale_verified:
            ap.error("Choose only one stale-verified maintenance mode")
        if args.only_partial:
            ap.error("--only-partial cannot be combined with stale-verified maintenance")
        if args.revalidate_only:
            ap.error("--revalidate-only is implied by --revalidate-stale-verified")
        if args.task_id or args.class_level or args.after_id:
            ap.error("stale-verified maintenance owns its exact target set; do not combine it with task/class/cursor filters")
        with engine.connect() as conn:
            verified_rows = conn.execute(text(f"""
                SELECT id, question_text, question_latex,
                       correct_answer, correct_answer_latex, distractor_meta,
                       answer_options, answer_options_latex
                FROM tasks_master
                WHERE verification_status = 'verified'
                  AND latex_status = 'verified'
                  {active_filter}
                ORDER BY id
            """)).fetchall()
        args.task_id = [
            str(row[0]) for row in verified_rows
            if stored_task_has_non_katex_gate_issue(
                row[1], row[2], row[3], row[4], row[5], row[6], row[7],
            )
        ]
        args.include_verified = True
        if args.revalidate_stale_verified:
            args.revalidate_only = True
        else:
            args.repair_invalid = True
        log.info(
            "Усиленная prefilter-проверка verified: просмотрено=%d, stale=%d",
            len(verified_rows), len(args.task_id),
        )
    if args.revalidate_only and not (args.only_partial or args.revalidate_stale_verified):
        ap.error("--revalidate-only requires --only-partial or --revalidate-stale-verified")
    grade_filter = """
        AND EXISTS (
            SELECT 1
            FROM textbook_toc toc
            JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
            WHERE toc.id = tm.toc_id AND tb.class_level = :lvl
        )
    """ if args.class_level else ""
    if args.only_partial:
        # A partial status certifies that at least one final display field did
        # not pass a gate.  Re-run every invalid or missing field, including
        # populated ones; the ordinary missing-only queue would skip those.
        args.repair_invalid = True
        status_filter = "AND tm.latex_status = 'partial'"
    else:
        status_filter = "" if args.include_verified else "AND tm.latex_status IS DISTINCT FROM 'verified'"
    task_filter = build_task_filter(
        args.task_id, exact_set_mode=stale_verified_mode,
    )
    order_direction = "DESC" if args.descending else "ASC"
    cursor_operator = "<" if args.descending else ">"

    # Проверяем ВСЕ элементы distractor_meta, не только [0]
    needs_display = """
                (COALESCE(btrim(tm.question_text), '') <> '' AND COALESCE(btrim(tm.question_latex), '') = '')
                OR (COALESCE(btrim(tm.correct_answer), '') <> '' AND COALESCE(btrim(tm.correct_answer_latex), '') = '')
                OR EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(COALESCE(tm.distractor_meta, '[]'::jsonb)) AS d
                    WHERE (
                        COALESCE(
                            NULLIF(btrim(d->>'value'), ''),
                            NULLIF(btrim(d->>'text'), ''),
                            NULLIF(btrim(d->>'content'), ''),
                            ''
                        ) <> ''
                        AND COALESCE(
                            NULLIF(btrim(d->>'value_latex'), ''),
                            NULLIF(btrim(d->>'text_latex'), ''),
                            NULLIF(btrim(d->>'content_latex'), ''),
                            ''
                        ) = ''
                    ) OR (
                        COALESCE(
                            NULLIF(btrim(d->>'error_logic'), ''),
                            NULLIF(btrim(d->>'explanation'), ''),
                            ''
                        ) <> ''
                        AND CASE
                            WHEN NULLIF(btrim(d->>'error_logic'), '') IS NOT NULL
                                THEN COALESCE(NULLIF(btrim(d->>'error_logic_latex'), ''), '')
                            ELSE COALESCE(NULLIF(btrim(d->>'explanation_latex'), ''), '')
                        END = ''
                    )
                )
                OR EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(
                        CASE WHEN jsonb_typeof(tm.answer_options) = 'array'
                             THEN tm.answer_options ELSE '[]'::jsonb END
                    ) WITH ORDINALITY AS opt(item, idx)
                    WHERE COALESCE(
                        NULLIF(btrim(opt.item->>'value'), ''),
                        NULLIF(btrim(opt.item->>'text'), ''),
                        NULLIF(btrim(opt.item->>'content'), ''),
                        NULLIF(btrim(opt.item #>> '{}'), ''),
                        ''
                    ) <> ''
                      AND COALESCE(
                          NULLIF(btrim(
                              CASE WHEN jsonb_typeof(tm.answer_options_latex) = 'array'
                                   THEN tm.answer_options_latex ->> ((opt.idx - 1)::int)
                                   ELSE '' END
                          ), ''),
                          ''
                      ) = ''
                )
    """
    selection = "TRUE" if (args.force_reformat or args.repair_invalid) else f"({needs_display})"
    base_params = {"task_ids": args.task_id} if args.task_id else {}
    if args.class_level:
        base_params["lvl"] = args.class_level

    def cursor_sql(cursor) -> str:
        return f"AND tm.id {cursor_operator} :cursor" if cursor is not None else ""

    def fetch_page(cursor, page_limit: int):
        sql_text = f"""
            SELECT tm.id, tm.question_text, tm.question_latex,
                   tm.correct_answer, tm.correct_answer_latex, tm.distractor_meta,
                   tm.answer_options, tm.answer_options_latex
            FROM tasks_master tm
            WHERE tm.verification_status = 'verified'
              {tm_active_filter}
              {status_filter}
              AND ({selection})
              {grade_filter}
              {task_filter}
              {cursor_sql(cursor)}
            ORDER BY tm.id {order_direction}
            LIMIT :page_limit
        """
        params = {**base_params, "page_limit": page_limit}
        if cursor is not None:
            params["cursor"] = cursor
        with engine.connect() as conn:
            return conn.execute(text(sql_text), params).fetchall()

    def fetch_fresh_task(task_id: str):
        """Reload one conflicting task from the source of truth for one retry."""
        sql_text = f"""
            SELECT tm.id, tm.question_text, tm.question_latex,
                   tm.correct_answer, tm.correct_answer_latex, tm.distractor_meta,
                   tm.answer_options, tm.answer_options_latex
            FROM tasks_master tm
            WHERE tm.id = :retry_id
              AND tm.verification_status = 'verified'
              {tm_active_filter}
              {status_filter}
              AND ({selection})
              {grade_filter}
              {task_filter}
        """
        with engine.connect() as conn:
            return conn.execute(
                text(sql_text), {**base_params, "retry_id": task_id},
            ).fetchone()

    initial_cursor = args.after_id
    count_sql = f"""
        SELECT count(*)
        FROM tasks_master tm
        WHERE tm.verification_status = 'verified'
          {tm_active_filter}
          {status_filter}
          AND ({selection})
          {grade_filter}
          {task_filter}
          {cursor_sql(initial_cursor)}
    """
    count_params = dict(base_params)
    if initial_cursor is not None:
        count_params["cursor"] = initial_cursor
    with engine.connect() as conn:
        total_candidates = int(conn.execute(text(count_sql), count_params).scalar_one())
    total_target = min(total_candidates, args.limit) if args.limit else total_candidates

    log.info("Найдено задач: %d", total_target)
    log.info("Режим чтения: свежая keyset-страница перед каждым батчем")
    if args.plan_only:
        log.info("PLAN ONLY — LLM не вызывается, в базу ничего не записывается.")
        return
    if not args.execute:
        log.info("DRY RUN — в базу ничего не пишется.")

    run_context = None
    if args.execute:
        run_id = args.run_id or str(uuid.uuid4())
        try:
            uuid.UUID(run_id)
        except ValueError:
            ap.error("--run-id must be a UUID")
        run_context = {
            "run_id": run_id,
            "label": args.run_label,
            "actor": "latex_backfill_cli",
            "model": LATEX_BACKFILL_MODEL,
            "prompt_version": LATEX_BACKFILL_PROMPT_VERSION,
            "policy_version": LATEX_BACKFILL_POLICY_VERSION,
            "queue_sha256": audit_queue_sha256,
            "config": {
                "mode": "backfill",
                "selection": "audit_queue" if args.audit_queue_file else "cli_filter",
                "target_count": total_target,
                "batch_size": args.batch_size,
                "concurrency": args.concurrency,
                "requests_per_minute": args.requests_per_minute,
                "repair_invalid": bool(args.repair_invalid),
                "force_reformat": bool(args.force_reformat),
                "only_partial": bool(args.only_partial),
                "include_verified": bool(args.include_verified),
            },
        }
        start_latex_backfill_run(engine, run_context)
        log.info("Создан audit manifest run_id=%s", run_context["run_id"])

    field_semaphore = asyncio.Semaphore(args.concurrency)
    request_pacer = AsyncRequestPacer(args.requests_per_minute)
    log.info(
        "Лимит API: %d запросов/мин, равномерный старт каждые %.3fs",
        args.requests_per_minute, 60.0 / args.requests_per_minute,
    )

    async def process_row(row):
        expected_source_fingerprint = audit_source_fingerprints.get(str(row[0]))
        if expected_source_fingerprint:
            current_source_fingerprint = canonical_fingerprint(row[1], row[3], row[5], row[6])
            if current_source_fingerprint != expected_source_fingerprint:
                log.warning(
                    "Audit source changed before processing task=%s; skipped until a fresh audit", row[0],
                )
                return {
                    "task_id": row[0],
                    "field_results": {},
                    "llm_seconds": 0.0,
                    "preflight_conflict": True,
                    "stored_status": "conflict",
                }
        return await process_task(
            row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], field_semaphore,
            force_reformat=args.force_reformat,
            repair_invalid=args.repair_invalid,
            revalidate_only=args.revalidate_only,
            request_pacer=request_pacer,
            llm_self_review=not args.skip_llm_self_review,
            run_context=run_context,
        )

    # This is a controlled persistence/checkpoint group. API concurrency is
    # still governed independently by ``--concurrency``.
    batch_size = max(1, args.batch_size)
    total_batches = (total_target + batch_size - 1) // batch_size if total_target else 0
    status_counts = {"verified": 0, "partial": 0, "failed": 0, "conflict": 0}
    all_durations: list[float] = []
    processed = 0
    cursor = initial_cursor
    batch_number = 0
    printed = 0

    while processed < total_target:
        page_limit = min(batch_size, total_target - processed)
        batch_rows = fetch_page(cursor, page_limit)
        if not batch_rows:
            log.info("Новых подходящих задач после cursor=%s больше нет", cursor)
            break
        batch_number += 1
        log.info(
            "Запуск батча %d/%d: задач=%d, диапазон=%s … %s",
            batch_number, total_batches, len(batch_rows), batch_rows[0][0], batch_rows[-1][0],
        )
        pending_rows = {
            asyncio.create_task(process_row(row)): str(row[0])
            for row in batch_rows
        }
        batch_results = []
        for completed in asyncio.as_completed(pending_rows):
            result = await completed
            batch_results.append(result)
            log.info(
                "Батч %d/%d: готова задача=%s, LLM=%.1fs",
                batch_number, total_batches, result["task_id"], result.get("llm_seconds", 0.0),
            )

        durations = sorted(res.get("llm_seconds", 0.0) for res in batch_results)
        all_durations.extend(value for value in durations if value > 0)
        if durations:
            log.info(
                "Время LLM в батче: avg=%.1fs, max=%.1fs",
                sum(durations) / len(durations), durations[-1],
            )
            for res in batch_results:
                if res.get("llm_seconds", 0.0) >= 30:
                    log.warning(
                        "Медленный LLM-ответ: task=%s, %.1fs",
                        res["task_id"], res["llm_seconds"],
                    )

        for res in batch_results:
            if res.get("preflight_conflict"):
                status_counts["conflict"] += 1
                processed += 1
                continue
            proj_st, issues, req_cnt, failed_flds, _ = resolve_projected_outcome(res)
            res["projected_status"] = proj_st
            if not args.execute and printed < args.show_samples:
                printed += 1
                print(f"\n{'='*70}\nTASK {res['task_id']} [ИТОГ: {proj_st.upper()}]")
                if not res["field_results"]:
                    print("  ℹ️ Все display-поля уже соответствуют KaTeX и контракту отображения (готово к верификации).")
                for label, r in res["field_results"].items():
                    status = "✅" if field_is_acceptable(r) else "⚠️"
                    print(
                        f"  {status} [{label}] decision={r.get('decision', 'N/A')} "
                        f"confidence={r['confidence']} katex_ok={r['katex_ok']}"
                    )
                    rendered = r["canonical"] if args.show_full else r["canonical"][:150]
                    print(f"     AFTER: {rendered}")
                    if not field_is_acceptable(r):
                        print(f"     причина: {field_failure_reason(r)}")
                if issues:
                    print(f"  Остающиеся замечания: {list(issues.keys())}")

        if args.execute:
            for index, res in enumerate(batch_results):
                final_result = res
                if final_result.get("preflight_conflict"):
                    status_counts["conflict"] += 1
                    batch_results[index] = final_result
                    continue
                try:
                    # One task per transaction: a conflict cannot roll back the
                    # other 24 successfully validated tasks in this batch.
                    with engine.begin() as conn:
                        save_result(conn, final_result)
                except ConcurrentTaskChangeError as exc:
                    log.warning("%s; перечитываю только эту задачу", exc)
                    fresh_row = fetch_fresh_task(str(res["task_id"]))
                    if fresh_row is None:
                        final_result["stored_status"] = "conflict"
                        log.warning(
                            "Конфликт task=%s уже обработан другим процессом или больше не подходит; пропуск",
                            res["task_id"],
                        )
                    else:
                        final_result = await process_row(fresh_row)
                        retry_seconds = final_result.get("llm_seconds", 0.0)
                        if retry_seconds > 0:
                            all_durations.append(retry_seconds)
                        try:
                            with engine.begin() as conn:
                                save_result(conn, final_result)
                            log.info("Конфликт task=%s безопасно повторён по свежему RAW", res["task_id"])
                        except ConcurrentTaskChangeError as retry_exc:
                            final_result["stored_status"] = "conflict"
                            log.error("Повторный конфликт task=%s: %s; продолжаю batch", res["task_id"], retry_exc)
                batch_results[index] = final_result
                stored = str(final_result.get("stored_status") or "conflict")
                status_counts[stored if stored in status_counts else "conflict"] += 1
        else:
            for res in batch_results:
                proj_st = str(res.get("projected_status") or "failed")
                status_counts[proj_st if proj_st in status_counts else "failed"] += 1

        processed += len(batch_rows)
        cursor = str(batch_rows[-1][0])
        log.info("Батч %d/%d ЗАВЕРШЁН; следующий cursor=%s", batch_number, total_batches, cursor)
        await asyncio.sleep(0.3)

    verified = status_counts["verified"]
    partial = status_counts["partial"]
    failed = status_counts["failed"]
    log.info("═" * 50)
    log.info(
        "Итого: verified=%d, partial=%d, failed=%d, conflicts=%d, задач всего=%d",
        verified, partial, failed, status_counts["conflict"], processed,
    )
    all_durations.sort()
    if all_durations:
        p95_index = min(len(all_durations) - 1, max(0, int(len(all_durations) * 0.95) - 1))
        log.info(
            "Производительность: elapsed=%.1fs, llm_avg=%.1fs, llm_p95=%.1fs, llm_max=%.1fs",
            time.monotonic() - run_started_at,
            sum(all_durations) / len(all_durations),
            all_durations[p95_index],
            all_durations[-1],
        )
    if not args.execute:
        log.info("Dry-run завершён. Проверьте примеры выше, затем запустите с --execute.")
    else:
        run_summary = {
            "processed": processed,
            "verified": verified,
            "partial": partial,
            "failed": failed,
            "conflicts": status_counts["conflict"],
            "elapsed_seconds": round(time.monotonic() - run_started_at, 3),
        }
        final_run_status = (
            "completed_with_review"
            if partial or failed or status_counts["conflict"] else "completed"
        )
        finish_latex_backfill_run(engine, run_context, final_run_status, run_summary)
        log.info("Audit manifest closed run_id=%s status=%s", run_context["run_id"], final_run_status)
        log.info("ПРОЦЕСС ЗАВЕРШЁН: все выбранные батчи обработаны и сохранены")


if __name__ == "__main__":
    asyncio.run(main())
