"""
ALGO — Раздел «Ответы» книги (инвариант И2)
src/pipeline/answer_key.py

Инвариант: **сгенерированное никогда не перекрывает напечатанное.**

Порядок разрешения ответа фиксирован и задаётся `provenance.ANSWER_AUTHORITY`:
    книга → решебник → вывод SymPy → генерация моделью.
`AIAnswerSolver` не удаляется — он остаётся фолбэком для книг без раздела
«Ответы», но становится **последним** в цепочке, а не первым и единственным.

Порт `newocr/mathocr/structure/answers.py` с одной существенной адаптацией.
В прототипе join шёл по номеру в пределах книги. Здесь так делать нельзя:
в учебнике нумерация упражнений **сбрасывается в каждом параграфе**, и join
только по номеру раздал бы ответы от «§3 упр. 12» задаче «§7 упр. 12».
Это ровно тот класс тихой порчи, ради которого затевался провенанс, поэтому
стратегия выбирается по факту (`choose_join_strategy`), а неоднозначность
отказывает в join, а не угадывает.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from src.pipeline import provenance as prov
from src.pipeline.models import ExtractedTask

log = logging.getLogger("pipeline")

# Снять форматный мусор с КРАЁВ номера: звёздочки, точки, градусы, скобки, пробелы.
# Внутренние точки («1.5») сохраняются — режем только по краям.
_EDGE_JUNK = re.compile(r"^[\s.*°)(]+|[\s.*°)(]+$")

#: Начало ответа. Разделитель подставляется — см. `_answer_line_re`.
#:
#: Пробел после разделителя необязателен: в книге встречается
#: «60.1) 15 тетрадей» и «61.18 и 12 карандашей». Ложные срабатывания на
#: десятичных дробях внутри ответа снимает монотонность, а не регулярка.
_ANSWER_LINE_TMPL = r"(?:^|(?<=[\s.;)\n]))(\d{{1,4}}[а-яa-z]?){sep}\s*(?=\S)"

#: Разделитель по умолчанию, когда угадывать не по чему.
_DOT = r"\."
_PAREN = r"\)"


def _answer_line_re(sep: str) -> "re.Pattern[str]":
    return re.compile(_ANSWER_LINE_TMPL.format(sep=sep), re.IGNORECASE)


def choose_answer_separator(text: str) -> str:
    """Каким знаком в этом разделе отделён номер задачи — точкой или скобкой.

    Выбор по факту, а не по предположению — та же логика, что в
    `choose_join_strategy`. Знаки несут разный смысл и путать их нельзя:
    в «56. 2) 80 и 40 орехов; 3) 44 страницы» точка отделяет номер задачи,
    а скобки — подпункты её ответа. Пока принимались оба, эта строка
    разбиралась на три «ответа» (56, 2 и 3), и два уезжали к чужим задачам:
    на `textzadachi5` выходило 507 «ответов» вместо ~440.

    Поэтому: есть точечная нумерация — она и есть номера задач, скобки внутри
    считаем подпунктами. Точек нет вовсе — значит книга нумерует скобкой.
    """
    body = text or ""
    n_dot = len(_answer_line_re(_DOT).findall(body))
    n_paren = len(_answer_line_re(_PAREN).findall(body))
    # Точка выигрывает при равенстве: она и есть обычная нумерация задач,
    # а скобка чаще оказывается подпунктом внутри ответа.
    return _DOT if n_dot >= n_paren else _PAREN

#: Значения, которые встречаются вместо ответа и ответом не являются.
_EMPTY_ANSWERS = {"", "—", "-", "–", "?", "...", "…", "н/д", "нет"}


def norm_number(number: object) -> str:
    """Нормализовать номер для join: `542.*` → `542`, `29.°` → `29`, `142а)` → `142а`.

    Это НЕ fuzzy-матч: снимается только форматный мусор с краёв, суть номера
    не трогается. Fuzzy-матчинг сознательно не используется — расхождение должно
    быть видно в отчёте, а не замазано похожестью.
    """
    return _EDGE_JUNK.sub("", str(number or "")).strip().lower()


def is_empty_answer(value: object) -> bool:
    """Ответ отсутствует по существу (пустой или заполнитель-прочерк)."""
    return str(value or "").strip().lower() in _EMPTY_ANSWERS


# ---------------------------------------------------------------------------
# Детекция и разбор раздела «Ответы»
# ---------------------------------------------------------------------------


def detect_answer_pages(
    task_pages: Iterable[int], all_pages: Sequence[int]
) -> List[int]:
    """Страницы раздела «Ответы» — хвостовой ряд страниц без извлечённых задач.

    Идём с последней страницы книги назад, собирая страницы, на которых извлечение
    не дало ни одной задачи; останавливаемся на первой странице с задачами.
    """
    with_tasks = {int(p) for p in task_pages}
    answer_pages: List[int] = []
    for pg in sorted((int(p) for p in all_pages), reverse=True):
        if pg in with_tasks:
            break
        answer_pages.append(pg)
    return sorted(answer_pages)


def _monotonic(items: List[Dict], start_from: int = 0) -> List[Dict]:
    """Оставить только номера, идущие по возрастанию.

    Нумерация в разделе ответов монотонна — это свойство самой книги, и оно
    даёт бесплатный фильтр ложных срабатываний. Десятичная дробь внутри ответа
    («74.73 км») дала бы кандидата с номером 74 или 73; тот, что меньше уже
    принятого, отбрасывается. Ошибиться в другую сторону (принять лишнее)
    фильтр может, но он не может увести ответ к задаче с меньшим номером,
    а это как раз тот случай, который портит join молча.
    """
    out: List[Dict] = []
    last = start_from
    for it in items:
        n = int_prefix(it["number"])
        if n is None or n < last:
            continue
        out.append(it)
        last = n
    return out


def int_prefix(number: object) -> Optional[int]:
    """Целочисленный префикс номера: `142а` → 142, `A` → None."""
    m = re.match(r"\d+", str(number or "").strip())
    return int(m.group()) if m else None


def parse_answer_section(text: str, source_page: Optional[int] = None) -> List[Dict]:
    """Разобрать плотный список ответов в записи {number, answer_md, source_page}.

    Разбор детерминированный (регулярка), а не через модель, и это осознанно:
    раздел ответов — регулярная нумерованная структура, на ней правило точнее и
    дешевле вызова, а главное — воспроизводимо. Модель здесь добавила бы ровно тот
    недетерминизм, от которого мы уходим.
    """
    if not text or not text.strip():
        return []

    marks = list(_answer_line_re(choose_answer_separator(text)).finditer(text))
    out: List[Dict] = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.end():end].strip()
        if not body or is_empty_answer(body):
            continue
        out.append(
            {
                "number": m.group(1),
                "answer_md": body,
                "source_page": source_page,
            }
        )
    return _monotonic(out)


# ---------------------------------------------------------------------------
# Стратегия join
# ---------------------------------------------------------------------------

#: Join по номеру в пределах книги. Допустим, только если номера уникальны.
BY_NUMBER = "number"
#: Join по паре (параграф, номер). Нужен, когда нумерация сбрасывается.
BY_PARAGRAPH_NUMBER = "paragraph_number"


#: Доля повторяющихся номеров, выше которой книга считается «со сбросом
#: нумерации» и join по одному номеру запрещается целиком.
#: Порог, а не «первый дубль»: в реальных выгрузках единичные дубли — это
#: форматный мусор («2)», «б)»), затёкший в поле номера, а не настоящий сброс.
#: Замерено 2026-08-28 на выгрузке прототипа: ДТМ2020 — 731 задача на 110
#: уникальных номеров (85% дублей, настоящий сброс), textzadachi5 — 12 дублей
#: на 590 (2%, мусор). Между этими режимами порог и разводит.
DUPLICATE_NUMBER_THRESHOLD = 0.20


def duplicate_numbers(tasks: Sequence[ExtractedTask]) -> set:
    """Номера, принадлежащие более чем одной задаче книги. Join их не трогает.

    От этой функции зависят **обе** защиты И2 сразу — выбор стратегии в
    `choose_join_strategy` и поштучный отказ по неоднозначному номеру в
    `join_answers`, — поэтому один её пропуск выключает их разом.

    Ровно это и было B38. Записи с подпунктом просто пропускались
    (`if sub: continue`), и у книги со сбросом нумерации по параграфам, чьи
    задачи разложены извлечением на «43.а/43.б», множество дублей выходило
    **пустым**: стратегия выбиралась `number`, отказов не было ни одного.
    Воспроизведено выполнением — §7 №43.а и §7 №43.б получали ответы от §3 и
    помечались `book_key` с `confidence.answer = 1.0`, то есть максимальным
    авторитетом: провенанс подтверждал то, чего не было.

    Различие, которое нужно было провести, — не «есть подпункт или нет», а
    **одной ли задаче книги принадлежат записи**:

    * «43.а» и «43.б» в §7 — подпункты одной задачи, не дубль;
    * «43» в §3 и «43.а» в §7 — два разных упражнения под одним номером, дубль;
    * два безподпунктных «43» в одном параграфе — дефект сегментации, дубль.

    Владелец номера — параграф. Параграфа нет ни у кого (сквозная нумерация
    без разметки) — тогда все записи лежат в одной группе, и функция сводится
    к прежнему поведению: ловит повторы, не считая подпункты дублями.
    """
    owners: Dict[str, set] = {}
    seen_whole: set = set()
    dups: set = set()
    for t in tasks:
        key, sub = split_number_sub(t.exercise_number)
        if not key:
            continue
        para = norm_number(t.paragraph_number)
        # Две записи под одним номером в одном параграфе, и хотя бы одна из них
        # — задача целиком: подпунктами одного упражнения это быть не может.
        if (para, key) in seen_whole:
            dups.add(key)
        if not sub:
            seen_whole.add((para, key))
        paragraphs = owners.setdefault(key, set())
        paragraphs.add(para)
        if len(paragraphs) > 1:
            dups.add(key)
    return dups


def choose_join_strategy(tasks: Sequence[ExtractedTask]) -> str:
    """Выбрать ключ join по факту, а не по предположению.

    Номера в книге в основном уникальны (сквозная нумерация) → можно по номеру,
    а единичные повторы отказываются поштучно в `join_answers`.
    Номера массово повторяются (сброс в каждом параграфе) → только по паре
    с параграфом, иначе ответ уедет не к той задаче.
    """
    numbered = [split_number_sub(t.exercise_number)[0] for t in tasks]
    numbered = [n for n in numbered if n]
    if not numbered:
        return BY_NUMBER
    dups = duplicate_numbers(tasks)
    # Доля считается по ЗАДАЧАМ, а не по различным номерам. Разница
    # существенная: в ДТМ2020 повторяющихся номеров ~90 штук, но задач под
    # ними 713 из 731. По различным номерам получилось бы 12% и книга прошла
    # бы как «сквозная нумерация» — при том что почти каждый её номер
    # неоднозначен.
    affected = sum(1 for n in numbered if n in dups)
    ratio = affected / len(numbered)
    return BY_PARAGRAPH_NUMBER if ratio > DUPLICATE_NUMBER_THRESHOLD else BY_NUMBER


@dataclass
class JoinReport:
    """Сводка join'а — то, из чего считается `answer_join_coverage`."""

    strategy: str = BY_NUMBER
    matched: int = 0
    n_tasks: int = 0
    n_answers: int = 0
    dup_answers: int = 0
    #: Ответ есть, задачи под таким номером нет — почти всегда дефект сегментации.
    unmatched_answers: List[str] = field(default_factory=list)
    #: Пропущено, потому что у задачи уже был более авторитетный источник.
    skipped_outranked: int = 0
    #: Не удалось применить стратегию (нет параграфа у задачи или у ответа).
    ambiguous: int = 0

    @property
    def coverage(self) -> Optional[float]:
        """Доля задач, получивших ответ из книги. None — считать не по чему."""
        if not self.n_tasks:
            return None
        return round(self.matched / self.n_tasks, 4)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy,
            "matched": self.matched,
            "n_tasks": self.n_tasks,
            "n_answers": self.n_answers,
            "dup_answers": self.dup_answers,
            "coverage": self.coverage,
            "skipped_outranked": self.skipped_outranked,
            "ambiguous": self.ambiguous,
            "unmatched_answers": list(self.unmatched_answers),
        }


#: Номер вида «43.а» / «46.1»: задача книги, разложенная извлечением на подпункты.
_NUM_WITH_SUB = re.compile(r"^(\d{1,4})[.\-–]([а-яa-z0-9]{1,3})$", re.IGNORECASE)

#: Помеченная часть ответа: «а) 215 мужских часов; б) 265 т.»
_LABELED_PART = re.compile(
    r"(?:^|[;.])\s*([а-яa-z0-9]{1,3})\)\s*([^;]+)",
    re.IGNORECASE,
)


def split_number_sub(number: object) -> tuple[str, str]:
    """Разложить номер на задачу книги и подпункт: «43.а» → («43», «а»).

    Извлечение заводит отдельную запись на каждый подпункт, а раздел ответов
    нумерует задачи целиком: в книге напечатано «43. а) 215 …; б) 265 …».
    Без этого разбора точный join не совпадает **ни разу** — при 427 честно
    разобранных ответах покрытие вышло бы нулевым.

    Это не fuzzy-матчинг: подпункт отрезается по явной структуре номера,
    суть номера не меняется. Не подошло под шаблон — возвращаем как есть.
    """
    raw = norm_number(number)
    m = _NUM_WITH_SUB.match(raw)
    return (m.group(1), m.group(2).lower()) if m else (raw, "")


def split_labeled_answer(text: str) -> Dict[str, str]:
    """Разобрать ответ на помеченные части: «а) 215; б) 265» → {а: …, б: …}.

    Пусто, если пометок нет — тогда ответ относится к задаче целиком.
    """
    out: Dict[str, str] = {}
    for label, body in _LABELED_PART.findall(text or ""):
        key = label.strip().lower()
        value = body.strip().rstrip(".;").strip()
        if key and value and key not in out:
            out[key] = value
    return out


def answer_for_subtask(answer_md: str, sub: str) -> str:
    """Часть ответа, относящаяся к подпункту.

    Три случая, и третий важнее прочих:

    * подпункта нет — ответ относится к задаче целиком;
    * ответ не размечен на части — он относится ко всем подпунктам;
    * ответ размечен, но **нужной метки в нём нет** — значит книга ответ для
      этого подпункта не напечатала. Возвращаем пусто.

    Последнее — не педантизм. В книге встречается «2. б) 76 страниц.»: часть
    «а)» не напечатана. Отдать сюда весь ответ означает выдать задаче `2.а`
    ответ, принадлежащий `2.б` — тихая порча ровно того рода, ради которой
    заводился провенанс. Пусто честнее: задача останется с ответом модели,
    помеченным `ai_solved`, и уйдёт человеку на проверку.
    """
    if not sub:
        return answer_md
    parts = split_labeled_answer(answer_md)
    if not parts:
        return answer_md
    return parts.get(sub, "")


def _task_key(task: ExtractedTask, strategy: str) -> Optional[str]:
    # Ключ — базовый номер задачи книги: подпункт «43.а» ищет ответ к «43».
    num, _sub = split_number_sub(task.exercise_number)
    if not num:
        return None
    if strategy == BY_NUMBER:
        return num
    para = norm_number(task.paragraph_number)
    if not para:
        return None
    return f"{para}/{num}"


def _answer_key(answer: Dict, strategy: str) -> Optional[str]:
    num = norm_number(answer.get("number"))
    if not num:
        return None
    if strategy == BY_NUMBER:
        return num
    para = norm_number(answer.get("paragraph_number"))
    if not para:
        return None
    return f"{para}/{num}"


def join_answers(
    tasks: Sequence[ExtractedTask],
    answers: Sequence[Dict],
    *,
    strategy: Optional[str] = None,
) -> JoinReport:
    """Пришить ответы из книги к задачам. Мутирует `tasks`.

    Пишет `answer_raw` только если источник книги авторитетнее того, что уже
    стоит в задаче (`provenance.outranks`). Поэтому повторный прогон не портит
    данные, а ИИ-ответ, если он там уже был, будет **вытеснен** книжным.
    """
    strategy = strategy or choose_join_strategy(tasks)
    report = JoinReport(strategy=strategy, n_tasks=len(tasks))

    # Неоднозначные ключи отказываются ПОШТУЧНО, а не роняют join целиком:
    # номер, принадлежащий нескольким задачам, не даёт понять, чей это ответ,
    # поэтому он не джойнится ни к одной. Угадывать здесь — ровно тот тихий
    # способ испортить банк, ради которого затевался провенанс.
    ambiguous_keys = duplicate_numbers(tasks) if strategy == BY_NUMBER else set()

    by_key: Dict[str, Dict] = {}
    for a in answers:
        key = _answer_key(a, strategy)
        if key is None:
            report.ambiguous += 1
            continue
        if key in by_key:
            report.dup_answers += 1
            continue  # первый выигрывает; повтор — в счётчик, не в данные
        by_key[key] = a
    report.n_answers = len(by_key)

    task_keys: set[str] = set()
    for t in tasks:
        key = _task_key(t, strategy)
        if key is None:
            report.ambiguous += 1
            continue
        task_keys.add(key)

        if key in ambiguous_keys:
            report.ambiguous += 1
            continue

        a = by_key.get(key)
        if a is None:
            continue

        value = str(a.get("answer_md") or "").strip()
        if is_empty_answer(value):
            continue

        # Часть под подпункт вычисляем ДО проверки на пустоту: у задачи `2.а`
        # ответ книги может быть напечатан только для `б)`, и тогда книжного
        # ответа для неё нет — засчитывать такое совпадение нельзя.
        _base, sub = split_number_sub(t.exercise_number)
        value = answer_for_subtask(value, sub)
        if is_empty_answer(value):
            continue

        if not prov.outranks(prov.BOOK_KEY, t.answer_source):
            report.skipped_outranked += 1
            continue

        t.answer_raw = value
        t.answer_source = prov.BOOK_KEY
        t.answer_source_page = a.get("source_page")
        t.confidence = dict(t.confidence or {})
        t.confidence["answer"] = 1.0
        report.matched += 1

    report.unmatched_answers = sorted(k for k in by_key if k not in task_keys)
    return report


# ---------------------------------------------------------------------------
# Резолвер порядка источников
# ---------------------------------------------------------------------------


def mark_existing_answers(
    tasks: Iterable[ExtractedTask], source: str = prov.BOOK_OCR
) -> int:
    """Проставить провенанс задачам, пришедшим из извлечения без пометки.

    Задача, у которой ответ уже есть, а `answer_source` пуст, — это ответ,
    напечатанный рядом с условием в теле книги. Он книжный, но не из раздела
    «Ответы», поэтому `book_solution`, а не `book_key`.
    """
    n = 0
    for t in tasks:
        if t.answer_source != prov.ABSENT:
            continue
        if is_empty_answer(t.answer_raw):
            continue
        t.answer_source = prov.BOOK_SOLUTION
        n += 1
    return n


def needs_ai_answer(task: ExtractedTask) -> bool:
    """Нужно ли звать модель за ответом.

    Единственное место, откуда `AIAnswerSolver` должен получать разрешение.
    Модель зовём, только когда ни книга, ни SymPy ответа не дали — то есть
    когда генерация ничего не перекрывает.
    """
    if not is_empty_answer(task.answer_raw):
        return False
    return task.answer_source in (prov.ABSENT,)


def answer_join_coverage(tasks: Sequence[ExtractedTask]) -> Optional[float]:
    """Доля ответов, взятых **из книги**, а не сгенерированных ИИ.

    Это реализация метрики `answer_join_coverage`, до сих пор стоявшей заглушкой
    `None` в `src/eval/metrics.py`.
    """
    if not tasks:
        return None
    from_book = sum(1 for t in tasks if prov.is_from_book(t.answer_source))
    return round(from_book / len(tasks), 4)
