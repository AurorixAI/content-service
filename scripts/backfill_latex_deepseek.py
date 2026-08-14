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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('APP_ENV', 'production')

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from sqlalchemy import create_engine, text
from src.pipeline.deepseek_client import call_deepseek as _call_deepseek

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backfill_latex_deepseek")

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
- В полях question и dmeta[n].description системы, интегралы и пределы
  являются крупными конструкциями и обязаны находиться внутри `$$...$$` с
  новой строки. Вариант `$\\begin{cases}...$` или
  `$\\displaystyle\\int...$` в этих текстовых полях запрещён.
- В чистых компактных значениях answer, dmeta[n].value и option[n] действует
  правило одной внешней пары `$...$` даже для системы, интеграла или предела:
  кнопки/карточки ответа не превращай в выносные блоки `$$...$$`.
- Повреждённый разделитель разрядов `$45\\$,$672$` означает число 45672.
  Правильно: `$45\\,672$`. Никогда не пиши `$45{,}672$`: это десятичная
  запятая и она меняет представление числа. Аналогично
  `$149\\$,$597\\$,$870$` -> `$149\\,597\\,870$`.

ОБЯЗАТЕЛЬНАЯ РЕАКЦИЯ НА @@CURRENT_VALIDATION:
- `pure_math_value_must_be_one_inline_formula` -> ровно одна внешняя пара `$`;
- `professional_style_requires_dfrac` -> удали КАЖДЫЙ арифметический `/` из
  математических фрагментов: собери его операнды в `\\dfrac{...}{...}`; если
  это единица или разделитель слов, вынеси `/` из `$...$` как обычный текст;
- `professional_style_requires_cases_for_system` -> `\\begin{cases}` в `$$`;
- `professional_style_requires_display_system` -> в question/description
  перенеси всю систему в `$$`;
- `professional_style_requires_display_operator` -> в question/description
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
3. Не добавляй и не удаляй круглые/квадратные скобки RAW. Разрешено переносить
   `$` через существующую скобку: `$(0x=18$` -> `($0x=18$), а
   `(значение $0)` -> `(значение $0$)`. Это исправление границы, не содержания.
4. CURRENT_LATEX — только черновик. Если он пуст или нарушает
   CURRENT_VALIDATION, обязательно REPLACE. REVIEW допустим только при двух
   реально разных математических прочтениях RAW, а не из-за сломанного LaTeX.

HOUSE STYLE:
- inline-математика `$...$`; крупная система/интеграл/предел в текстовом поле
  — отдельный `$$...$$`; чистое значение ответа — одна пара `$...$`;
- основные дроби `\dfrac{a}{b}`, компактный `\frac` только внутри степени или
  индекса; арифметические `/`, `*`, `\times` запрещены, используй `\dfrac` и
  `\cdot` без изменения операции;
- никогда не заменяй исходное арифметическое деление `/` двоеточием `:`.
  Оформи те же операнды через `\dfrac`; двоеточие допустимо только тогда,
  когда оно уже было в RAW;
- `\sqrt{x}`, `x^{2}`, `x_{1}`, стандартные `\alpha`, `\leq`, `\geq`,
  `\neq`, `\infty`; Unicode-математические символы запрещены;
- русский текст остаётся вне математики либо оформляется `\text{...}`;
- системы оформляй `\begin{cases}...\end{cases}`.

ОБЯЗАТЕЛЬНАЯ ФИНАЛЬНАЯ ПРОВЕРКА ИМЕННО ВОЗВРАЩАЕМОГО TEXT:
- каждая пара `$` закрыта; русский текст не попал внутрь формулы;
- каждая `(`, `)`, `[`, `]` открывается и закрывается на одной стороне
  LaTeX-границы: либо обе внутри одной формулы, либо обе вне её;
- если одна пара скобок охватывает несколько формул и текст между ними,
  обе скобки обязаны быть снаружи: `($6+10$ или $6+11-1$)`. Варианты
  `$(6+10$ или $6+11-1)$` и `$(6+10$ или `$6+11-1)$` запрещены;
- внутри математики нет арифметических `/`, `*`, `\times`, основной `\frac`,
  Unicode-знаков и степеней/индексов без `{}`;
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


def parse_task_bundle_response(raw: str, expected_fields: dict[str, dict]) -> dict[str, dict]:
    """Parse an unescaped multi-field response while retaining every backslash."""
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
            "canonical": match.group(5).strip(),
            "decision": match.group(2).upper(),
            "confidence": match.group(3).lower(),
            "ambiguity_reason": None if reason_raw.upper() == "NONE" else reason_raw,
        }
    result: dict[str, dict] = {}
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

KATEX_VALIDATE_JS = """
const katex = require('/Users/arslan/Desktop/ALGO/algo-front/node_modules/katex');
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

NODE_BIN = os.environ.get("NODE_BIN") or shutil.which("node") or "/Users/arslan/.nvm/versions/node/v20.20.2/bin/node"
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
    list_markers = re.findall(r"(?:^|[;\n]\s*)\$?[0-9A-Za-zА-Яа-яЁё]+[.)]", raw)
    if len(list_markers) >= 2 or len(_math_fragments(raw)) >= 2:
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
            if re.search(r"\\(?:int|lim)(?![A-Za-z])", inline_fragment):
                return False, "professional_style_requires_display_operator"
    return True, ""


_UNICODE_MATH_STYLE_RE = re.compile(
    r"[√×÷≤≥≠∞±αβγδεθλμπρστφω²³⁰¹⁴⁵⁶⁷⁸⁹]"
)
_UNBRACED_SCRIPT_RE = re.compile(r"(?:\^|_)(?:[A-Za-z0-9]|\\[A-Za-z]+)")
_BARE_MATH_SLASH_RE = re.compile(r"(?<!\\)/")
_TEXT_COMMAND_RE = re.compile(r"\\(?:text|textrm|textsf|texttt)\{[^{}]*\}")
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
        # A left brace plus ``array`` is a legacy way of drawing a system.  It
        # renders, but is not our semantic/typographic representation; the LLM
        # must rewrite it as ``cases`` without changing any equation.
        if re.search(r"\\left\s*\\\{\s*\\begin\{array\}", fragment):
            return False, "professional_style_requires_cases_for_system"
        if _has_main_style_frac(fragment):
            return False, "professional_style_requires_dfrac"
        if _UNBRACED_SCRIPT_RE.search(fragment):
            return False, "professional_style_requires_braced_script"
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


def _validate_parenthesis_math_boundaries(display: str) -> tuple[bool, str]:
    """Reject parentheses whose two sides live on opposite sides of ``$``.

    KaTeX validates each formula independently and therefore accepts both
    ``$(25-15=10$ чисел)`` and ``(текст ... $441)$``. They are visually broken
    even though the formula fragment itself parses. This scanner is only a
    safety gate; the LLM remains responsible for producing the repair.
    """
    scope: tuple[str, int] | None = None
    next_scope_id = 0
    opened_in: list[tuple[str, int] | None] = []
    text_value = str(display or "")
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
            if not opened_in:
                if char == ")" and scope is None and re.search(
                    r"(?:^|[:;\n]\s*)[0-9A-Za-zА-Яа-яЁё]+$", text_value[:index],
                ):
                    index += 1
                    continue
                return False, "unbalanced_parentheses"
            if opened_in.pop() != scope:
                return False, "parenthesis_crosses_math_boundary"
        index += 1
    if opened_in or scope is not None:
        return False, "unbalanced_parentheses"
    return True, ""


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
    "√": "sqrt", "²": "2", "³": "3", "⁰": "0", "¹": "1",
    "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon",
    "θ": "theta", "λ": "lambda", "μ": "mu", "π": "pi", "ρ": "rho",
    "σ": "sigma", "τ": "tau", "φ": "phi", "ω": "omega",
})
_LATEX_OPERATOR_MAP = (
    (r"\div", "/"),
    (r"\cdot", "*"), (r"\times", "*"),
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
        model="deepseek-v4-flash",
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
        if "*" in fragment:
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
    request_pacer=None,
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
        canonical = repair_unambiguous_enumeration_marker_boundary(
            field["raw"], item.get("canonical") or "",
        )
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

    def feedback_prompt(base_prompt: str, label: str, result: dict) -> str:
        reasons = [
            result.get("katex_error"), result.get("contract_error"),
            result.get("professional_error"), result.get("semantic_error"),
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
                "- professional_style_requires_dfrac: найди КАЖДЫЙ символ `/` "
                "внутри каждой формулы и перестрой его два операнда в "
                "`\\dfrac{числитель}{знаменатель}`. Не оставляй `/` и не заменяй "
                "его на `:`. Для вложенного деления используй вложенные "
                "`\\dfrac`, сохранив исходный порядок всех операндов."
            )
        if "professional_style_requires_cdot" in reasons:
            repair_steps.append(
                "- professional_style_requires_cdot: внутри формулы замени "
                "каждый арифметический `*` или `\\times` на `\\cdot`; числа, "
                "буквы, скобки и порядок множителей оставь без изменений."
            )
        if "pure_math_value_must_be_one_inline_formula" in reasons:
            repair_steps.append(
                "- pure_math_value_must_be_one_inline_formula: это поле — "
                "чистый ответ. Верни ровно одну формулу `$...$`; вынеси точку, "
                "запятую и иной обычный текст за её пределы, не меняя значение."
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
        if "unbalanced_parentheses" in reasons:
            repair_steps.append(
                "- unbalanced_parentheses: пересобери формулы из RAW. Каждая "
                "круглая и квадратная скобка должна иметь парную скобку; если "
                "скобки охватывают текст и несколько формул, обе оставь снаружи "
                "math-границ. Не добавляй и не удаляй скобки RAW."
            )
        if any(reason in reasons for reason in (
            "semantic_text_sequence_changed",
            "semantic_number_sequence_changed",
            "semantic_operator_sequence_changed",
        )):
            repair_steps.append(
                "- semantic_*_sequence_changed: перепиши candidate строго из "
                "RAW без перефразирования. Сохрани все слова, буквы, числа, "
                "операторы и их порядок; меняй исключительно LaTeX-разметку."
            )
        if "parenthesis_crosses_math_boundary" in reasons:
            repair_steps.append(
                "- parenthesis_crosses_math_boundary: не копируй позиции `$` из "
                "candidate. Возьми буквальный RAW_WITHOUT_LEGACY_DELIMITERS и "
                "расставь формулы заново. Ни одна скобка не может открываться "
                "внутри `$...$`, а закрываться снаружи или в другой формуле. "
                "Если скобки охватывают несколько формул и слова между ними, "
                "обе скобки оставь снаружи: `($a$ или $b$)`."
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
        repair_block = (
            "\n@@ОБЯЗАТЕЛЬНЫЙ_АЛГОРИТМ_ИСПРАВЛЕНИЯ:\n" + "\n".join(repair_steps)
            if repair_steps else ""
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

    async def format_one(label: str, field: dict) -> tuple[str, dict, float]:
        one_field = {label: field}
        base_prompt = _bundle_prompt(context_fields, current_displays, one_field)
        async with semaphore:
            # Measure only transport/model time after acquiring the global
            # slot; queue time is not mislabeled as a slow LLM response.
            request_started_at = time.monotonic()
            try:
                raw = await _paced_task_bundle_call(base_prompt, request_pacer)
                parsed_item = parse_task_bundle_response(raw.strip(), one_field)[label]
            except Exception as exc:
                log.error("DeepSeek field failed label=%s: %s", label, exc)
                parsed_item = {
                    "canonical": field["current"],
                    "decision": "REVIEW",
                    "confidence": "low",
                    "ambiguity_reason": f"llm_error: {exc}",
                }
            validated = validate_item(label, field, parsed_item)
            transport_failed = str(validated.get("ambiguity_reason") or "").startswith("llm_error:")
            genuine_review = (
                validated.get("decision") == "REVIEW"
                and validated.get("confidence") in ("high", "medium")
                and validated.get("ambiguity_reason")
            )
            # One contextual LLM call per target field.  The prompt itself
            # requires a self-check, while independent deterministic gates
            # remain the only authority for acceptance.  A second LLM review
            # was intentionally removed: it doubled latency/cost without
            # proving more than the source/display/KaTeX gates below.
            if not transport_failed and not genuine_review:
                validated["llm_self_check_used"] = False
            request_seconds = time.monotonic() - request_started_at
        return label, validated, request_seconds

    formatted = await asyncio.gather(*[
        format_one(label, field) for label, field in output_fields.items()
    ])
    results = {label: item for label, item, _seconds in formatted}
    # Sum of actual occupied LLM slots is useful for cost/throughput analysis;
    # it deliberately excludes time waiting behind other fields/tasks.
    request_seconds = sum(seconds for _label, _item, seconds in formatted)

    # answer_options and distractor_meta intentionally overlap in part of the
    # historical corpus.  If the RAW value is byte-for-byte identical, reuse a
    # display projection that independently passes every target-field gate when
    # the model omitted/rejected the duplicate block.  No LaTeX is synthesized
    # here and no merely-similar values are matched.
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
        semantic_ok, semantic_error = semantic_preservation_check(
            raw, candidate, allow_legacy_markup_repair=True,
        )
        if not (katex_ok and contract_ok and professional_ok and semantic_ok):
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
            "semantic_ok": semantic_ok,
            "semantic_error": semantic_error,
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
            source_display = (
                source_result["canonical"]
                if source_result is not None and field_is_acceptable(source_result)
                else current_displays.get(source_label, "")
            )
            replacement = validated_duplicate(target_label, target_raw, source_display)
            if replacement is not None:
                results[target_label] = replacement
                break
    return results, request_seconds


def field_is_acceptable(result: dict) -> bool:
    return (
        result["confidence"] in ("high", "medium")
        and result.get("decision") in ("KEEP", "REPLACE")
        and result["katex_ok"]
        and result.get("contract_ok", False)
        and result.get("professional_ok", False)
        and result.get("semantic_ok", False)
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


_LEGACY_ENUMERATION_MARKER_RE = re.compile(r"\$\s*([0-9A-Za-zА-Яа-яЁё])\)\s*([^$]*)\$")


def repair_unambiguous_enumeration_marker_boundary(raw: object, display: object) -> str:
    """Move a legacy ``$b) x$`` marker out of its formula, display-only.

    The same marker must occur in RAW. The transformation is restricted to
    delimiter placement: ``$b) x$`` becomes ``b) $x$`` and ``$a)$`` becomes
    ``a)``. It cannot change the educational source or mathematical value.
    """
    source_markers = set(re.findall(r"\$\s*([0-9A-Za-zА-Яа-яЁё])\)", str(raw or "")))
    if not source_markers:
        return str(display or "")

    def replace(match: re.Match) -> str:
        marker, tail = match.group(1), match.group(2)
        if marker not in source_markers:
            return match.group(0)
        tail = tail.strip()
        return f"{marker})" if not tail else f"{marker}) ${tail}$"

    return _LEGACY_ENUMERATION_MARKER_RE.sub(replace, str(display or ""))


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
        display_text = str(display_value)
        if not validate_with_katex(display_text)[0]:
            return True
        if not validate_display_contract(label, str(source_value or ""), display_text)[0]:
            return True
        if not validate_professional_latex(display_text)[0]:
            return True
        # KaTeX can parse two fragments separately even when an older formatter
        # split one source formula with a nested `$`.  Require the display to
        # retain the source formula boundaries as well as valid syntax.
        semantic_ok, _ = semantic_preservation_check(str(source_value or ""), display_text)
        return not semantic_ok

    if qt:
        context_fields["question"] = str(qt)
        current_displays["question"] = str(question_latex or "")
        if needs_display_repair("question", qt, question_latex):
            output_fields["question"] = {"raw": str(qt), "current": str(question_latex or "")}
    if ans:
        context_fields["answer"] = str(ans)
        current_displays["answer"] = str(correct_answer_latex or "")
        if needs_display_repair("answer", ans, correct_answer_latex):
            output_fields["answer"] = {"raw": str(ans), "current": str(correct_answer_latex or "")}

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
                        current_displays[f"dmeta[{i}].value"] = value_latex
                        if needs_display_repair(f"dmeta[{i}].value", value, value_latex):
                            output_fields[f"dmeta[{i}].value"] = {"raw": value, "current": value_latex}

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
                        current_displays[f"dmeta[{i}].description"] = display
                        if needs_display_repair(f"dmeta[{i}].description", description, display):
                            output_fields[f"dmeta[{i}].description"] = {"raw": description, "current": display}
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
        current_displays[label] = display
        if needs_display_repair(label, value, display):
            output_fields[label] = {"raw": value, "current": display}

    queued_at = time.monotonic()
    field_results, llm_seconds = await format_task_bundle(
        context_fields, current_displays, output_fields, semaphore, request_pacer,
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
    value must parse, preserve its RAW source and satisfy the house style.
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
        semantic_ok, semantic_error = semantic_preservation_check(
            raw_text, display_text, allow_legacy_markup_repair=True,
        )
        if not (katex_ok and contract_ok and professional_ok and semantic_ok):
            issues[label] = {
                "reason": contract_error or professional_error or semantic_error or katex_error or "invalid_display_value",
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


def save_result(conn, result: dict):
    tid = result["task_id"]
    fr = result["field_results"]
    original_dmeta_snapshot = copy.deepcopy(result.get("dmeta_original"))
    dmeta = [] if original_dmeta_snapshot is None else copy.deepcopy(original_dmeta_snapshot)

    failed_fields = {}

    def resolve(label, original_value):
        r = fr.get(label)
        if r is None:
            return original_value, True  # поле не обрабатывалось — не трогаем, не считаем failed
        if field_is_acceptable(r):
            return r["canonical"], True
        failed_fields[label] = {
            "reason": field_failure_reason(r),
            "confidence": r["confidence"],
        }
        return original_value, False  # оставляем как было, НЕ портим

    new_question, _ = resolve("question", result["original"]["question_latex"])
    new_answer, _ = resolve("answer", result["original"]["correct_answer_latex"])

    for i, d in enumerate(dmeta):
        if not isinstance(d, dict):
            continue
        new_val, ok = resolve(f"dmeta[{i}].value", d.get("value") or d.get("text") or d.get("content"))
        if ok and f"dmeta[{i}].value" in fr:
            # `value` is the canonical answer used by the diagnostic evaluator.
            # Never replace it with display LaTeX: a selected MCQ option must be
            # compared with the same stable value the task was authored with.
            d["value_latex"] = new_val
        source_key, display_key = (
            ("error_logic", "error_logic_latex")
            if str(d.get("error_logic") or "").strip()
            else ("explanation", "explanation_latex")
        )
        new_description, ok = resolve("dmeta[%d].description" % i, d.get(display_key))
        if ok and f"dmeta[{i}].description" in fr:
            # Raw explanation/error_logic remain untouched. One explicitly
            # selected display projection prevents duplicate UI content.
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
        new_display, ok = resolve(f"option[{i}]", original_display)
        new_options_latex.append(new_display if ok else original_display)

    total_attempted = len(fr)
    total_failed = len(failed_fields)

    final_issues, final_required_count = final_display_issues(
        result["original"]["question"], new_question,
        result["original"]["answer"], new_answer,
        dmeta, raw_options, new_options_latex,
    )
    # Status certifies the final stored display contract, not whether an LLM
    # suggestion was usable. An unusable suggestion is discarded; if the
    # pre-existing display still passes every independent gate, it remains
    # genuinely verified. If an invalid/missing field remains, only then does
    # the task becomes partial. It is failed only when every required display
    # field is unusable, i.e. the task has no valid rendered projection at all.
    status = latex_status_from_issues(final_issues, final_required_count)

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
    dmeta_for_storage = None if original_dmeta_snapshot is None else dmeta
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
        # display data or move latex_normalized_at for no reason.
        sync_latex_review_queue(conn, tid, status, review_issues)
        result["database_write"] = "skipped_unchanged"
        return

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
    sync_latex_review_queue(conn, tid, status, review_issues)


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

    db_url = os.environ.get("DATABASE_URL") or "postgresql://algo:algo_password@127.0.0.1:5434/algo_content"
    engine = create_engine(db_url)
    stale_verified_mode = (
        args.repair_stale_verified or args.revalidate_stale_verified
    )
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
            verified_rows = conn.execute(text("""
                SELECT id, question_text, question_latex,
                       correct_answer, correct_answer_latex, distractor_meta,
                       answer_options, answer_options_latex
                FROM tasks_master
                WHERE is_active = TRUE
                  AND verification_status = 'verified'
                  AND latex_status = 'verified'
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
            WHERE tm.is_active = true
              AND tm.verification_status = 'verified'
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
              AND tm.is_active = true
              AND tm.verification_status = 'verified'
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
        WHERE tm.is_active = true
          AND tm.verification_status = 'verified'
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

    field_semaphore = asyncio.Semaphore(args.concurrency)
    request_pacer = AsyncRequestPacer(args.requests_per_minute)
    log.info(
        "Лимит API: %d запросов/мин, равномерный старт каждые %.3fs",
        args.requests_per_minute, 60.0 / args.requests_per_minute,
    )

    async def process_row(row):
        return await process_task(
            row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], field_semaphore,
            force_reformat=args.force_reformat,
            repair_invalid=args.repair_invalid,
            revalidate_only=args.revalidate_only,
            request_pacer=request_pacer,
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
            if not args.execute and printed < args.show_samples:
                printed += 1
                print(f"\n{'='*70}\nTASK {res['task_id']}")
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

        if args.execute:
            for index, res in enumerate(batch_results):
                final_result = res
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
                acceptable = sum(field_is_acceptable(value) for value in res["field_results"].values())
                attempted = len(res["field_results"])
                if attempted and acceptable == attempted:
                    status_counts["verified"] += 1
                elif acceptable:
                    status_counts["partial"] += 1
                else:
                    status_counts["failed"] += 1

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
        log.info("ПРОЦЕСС ЗАВЕРШЁН: все выбранные батчи обработаны и сохранены")


if __name__ == "__main__":
    asyncio.run(main())
