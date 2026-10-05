"""N01 wave 1: source-checked repairs; export contains no pupil records.

Run with the bounded stage educational export. Generates only a reviewable
change manifest, never connects to a database. More N01 candidates remain in
the length-review queue; this is deliberately not an assertion about all 153.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.content_review.guarded_repair import candidate, fingerprint, validate_choices, validate_entry

BATCH = "n01-source-repair-2026-10-05-w1"


def d(value: str, reason: str, error_type: str) -> dict:
    return {"value": value, "value_latex": value, "error_type": error_type,
            "error_logic": reason, "explanation": reason,
            "error_logic_latex": reason, "explanation_latex": reason}


def choices(question: str | None, key: str, distractors: list[dict], **extra) -> dict:
    fields = {"correct_answer": key, "correct_answer_latex": key,
              "answer_options": [key] + [x["value"] for x in distractors],
              "answer_options_latex": [key] + [x["value_latex"] for x in distractors],
              "distractor_meta": distractors, "sympy_solution": None,
              "answer_type": "multiple_choice", "verification_status": "verified", **extra}
    if question is not None:
        fields.update(question_text=question, question_latex=question)
    return fields


REPAIRS = {
    "G10_TB_3_9_9": {
        "reason": "Неверный ключ и объяснения; скидка производителя ошибочно принята за добавленную стоимость оптовика. Mapping показательного роста не соответствует задаче.",
        "evidence": "IDUM, Алгебра 10 (2022), с.130–131, §3.9 №9: НДС равен разности выходного и входного налога. Цены 8 400 000 → 9 600 000 → 12 000 000; 10% разностей = 120 000 и 240 000. Привязка: скидки/наценки, не показательный рост.",
        "changes": choices(
            r"Объявленная цена товара — $12\,000\,000$ сумов без налога. Производитель продаёт его оптовику со скидкой $30\%$, оптовик — розничному продавцу со скидкой $20\%$ от объявленной цены. Розничный продавец продаёт товар по объявленной цене. Налог на каждом этапе равен $10\%$ цены продажи без налога; к уплате идёт разность выходного и входного налога. Найдите суммы к уплате оптовиком и розничным продавцом, в этом порядке.",
            r"$120\,000;\ 240\,000$",
            [d(r"$360\,000;\ 240\,000$", r"Для оптовика взят налог от скидки производителя: $12\,000\,000\cdot0{,}3\cdot0{,}1=360\,000$. Нужна разность его цен продажи и покупки: $(9\,600\,000-8\,400\,000)\cdot0{,}1=120\,000$.", "discount_instead_of_margin"),
             d(r"$960\,000;\ 1\,200\,000$", r"Взяты налоги от полной выручки продавцов, без вычета входного налога: $9\,600\,000\cdot0{,}1$ и $12\,000\,000\cdot0{,}1$.", "input_tax_omitted"),
             d(r"$240\,000;\ 120\,000$", "Правильно вычисленные суммы переставлены: первая относится к оптовику, вторая — к розничному продавцу.", "order_reversed")],
            skill_id="G5_S46_02"),
    },
    "G10_TB_6_2_16": {
        "reason": "Сам учебник говорит только о квадрате внутри круга. Для однозначного ключа добавлены вписанность и равномерный выбор точки; исправлены неверные цепочки дистракторов.",
        "evidence": "IDUM, Алгебра 10 (2022), с.177, §6.2 №16: у задания нет рисунка квадрата и не указан его размер. Явное уточнение редактора: квадрат вписан в круг. Диагональ 2R, площадь 2R², вероятность 2R²/(πR²)=2/π. Изображения не активируются.",
        "changes": choices(
            "В круг вписан квадрат: все четыре его вершины лежат на окружности. Точку выбирают случайно и равномерно по площади круга. Найдите вероятность того, что она окажется внутри квадрата.",
            r"$\dfrac{2}{\pi}$",
            [d(r"$\dfrac{1}{\pi}$", r"Сторона квадрата ошибочно принята равной радиусу $R$, поэтому получено $R^{2}/(\pi R^{2})$. У вписанного квадрата сторона $R\sqrt{2}$.", "radius_as_square_side"),
             d(r"$\dfrac{4}{\pi}$", r"Сторона квадрата ошибочно принята равной диаметру $2R$. Получено $4R^{2}/(\pi R^{2})>1$, что также противоречит границам вероятности.", "diameter_as_square_side"),
             d(r"$\dfrac{\pi}{4}$", r"Вычислена вероятность для обратной геометрической постановки: круг внутри квадрата со стороной $2R$, то есть $\pi R^{2}/(4R^{2})$.", "inscribed_shapes_reversed")]),
    },
    "G10_TB_§42_42_7_3": {
        "reason": "Первоисточник действительно требует открытый интервал (1;2). В ключе не была указана область определения, исключающая x=0.",
        "evidence": "Мерзляк, Алгебра 10, базовый уровень, с.317 (PDF311), №42.7(3): интервал (1;2), без дополнительных условий. Для f=1+1/(1+x²), x≠0, 0<1/(1+x²)<1; любое y∈(1;2) достигается при x=±sqrt(1/(y−1)−1). Остальные варианты имеют (0;1], (1;+∞), [1;2).",
        "changes": choices(
            r"Выберите функцию, область значений которой — интервал $(1;2)$. Для каждого варианта используйте указанную рядом область определения.",
            r"$f(x)=1+\dfrac{1}{1+x^{2}},\quad x\in\mathbb{R}\setminus\{0\}$",
            [d(r"$f(x)=\dfrac{1}{1+x^{2}},\quad x\in\mathbb{R}$", r"Не выполнен сдвиг значений на $1$: область значений равна $(0;1]$, а не $(1;2)$.", "range_shift_omitted"),
             d(r"$f(x)=1+\dfrac{1}{x^{2}},\quad x\in\mathbb{R}\setminus\{0\}$", r"При приближении $x$ к нулю значения не ограничены сверху; область значений $(1;+\infty)$.", "unbounded_range"),
             d(r"$f(x)=2-\dfrac{1}{1+x^{2}},\quad x\in\mathbb{R}$", r"При $x=0$ значение равно $1$, поэтому область значений $[1;2)$ включает недопустимую нижнюю границу.", "closed_range_endpoint")]),
    },
    "G10_TB_6_1_1": {
        "reason": "Импортирован разобранный пример из теории вместо вопроса. Уточнены исчерпывающие исходы; варианты теперь короткие и взаимно различимые.",
        "evidence": "IDUM, Алгебра 10 (2022), с.166, §6.1, Пример1. Каждая деталь либо качественная, либо некачественная: A∩B=∅, A∪B=Ω, B=Ω\\A. В коробке есть детали обоих видов, поэтому 0<P(A)<1 и события не независимы.",
        "changes": choices(
            "В коробке есть качественные и некачественные детали. Каждая деталь относится ровно к одному из этих двух видов. Случайно выбирают одну деталь. Как называются события «выбрана качественная деталь» и «выбрана некачественная деталь»?",
            "Противоположные",
            [d("Независимые", "При наступлении одного из событий другое невозможно. При наличии деталей обоих видов вероятность их совместного наступления равна нулю, а произведение вероятностей положительно.", "independence_confused_with_complement"),
             d("Совместные", "Одна выбранная деталь не может одновременно быть качественной и некачественной: события несовместны.", "mutually_exclusive_events_confused"),
             d("Совпадающие", "События описывают разные, взаимно исключающие исходы; они не совпадают.", "events_identified")],
            skill_id="G10_S27_02"),
    },
    "G10_TB_1_6_7_g": {
        "reason": "Верный ключ сохранён. Объяснения ошибочно называли замену аргумента вертикальным сдвигом; проверены все три дистрактора.",
        "evidence": "IDUM, Алгебра 10 (2022), §1.6 №7(g). Отражение Oy даёт f(−x); перенос вверх — f(−x)+1, x≤0. sqrt[4](x+1) — перенос исходного графика влево; sqrt[4](1−x) — перенос отражённого графика вправо, не вверх.",
        "changes": choices(
            r"График функции $f(x)=\sqrt[4]{x}$ сначала отражают относительно оси $Oy$, затем перемещают вверх на $1$ единицу. Выберите формулу полученной функции.",
            r"$\sqrt[4]{-x} + 1$",
            [d(r"$\sqrt[4]{x+1}$", r"Замена $x$ на $x+1$ сдвигает исходный график влево на $1$. В этом варианте нет ни отражения относительно $Oy$, ни переноса вверх.", "horizontal_shift_instead_of_required_transforms"),
             d(r"$-\sqrt[4]{x}+1$", r"Минус перед значением функции отражает график относительно $Ox$. Для отражения относительно $Oy$ минус должен появиться у аргумента под корнем.", "reflection_axis_confused"),
             d(r"$\sqrt[4]{1-x}$", r"После отражения получено $g(x)=\sqrt[4]{-x}$. Вариант $g(x-1)=\sqrt[4]{1-x}$ сдвигает его вправо на $1$; перенос вверх должен давать $g(x)+1$.", "horizontal_instead_of_vertical_shift")],
            skill_id="G10_S06_08"),
    },
    "G11_TB_6_6_6_43_c": {
        "reason": "Потерян контекст метода трапеций; mapping указывал метод прямоугольников. Ключ 0 сохранён; варианты теперь проверяют конкретные различия методов.",
        "evidence": "Никольский, Алгебра11, §6.6, с.182–184 (PDF183–185), №6.43(в): метод трапеций. На 20 равных подотрезках симметричные слагаемые sin взаимно сокращаются. Трапеции=0, левые прямоугольники=−π/20, правые=π/20; интеграл |sin|=2.",
        "changes": choices(
            r"Вычислите приближённое значение интеграла методом трапеций на равномерном разбиении с шагом $\Delta x=\dfrac{\pi}{20}$: $$\displaystyle\int_{-\pi/2}^{\pi/2}\sin x\,dx.$$",
            r"$0$",
            [d(r"$2$", r"Вместо интеграла знакопеременной функции взята суммарная площадь: $\int_{-\pi/2}^{\pi/2}|\sin x|\,dx=2$. У исходной нечётной функции вклады слева и справа от нуля имеют разные знаки.", "absolute_area_instead_of_signed_integral"),
             d(r"$\dfrac{\pi}{20}$", r"Использованы правые прямоугольники вместо трапеций. Их сумма больше суммы трапеций на $\dfrac{\Delta x}{2}(\sin(\pi/2)-\sin(-\pi/2))=\dfrac{\pi}{20}$.", "right_rectangles_instead_of_trapezoids"),
             d(r"$-\dfrac{\pi}{20}$", r"Использованы левые прямоугольники вместо трапеций. Их сумма меньше суммы трапеций на $\dfrac{\Delta x}{2}(\sin(\pi/2)-\sin(-\pi/2))=\dfrac{\pi}{20}$.", "left_rectangles_instead_of_trapezoids")],
            skill_id="G11_S39_02"),
    },
}


def build(source: dict, repairs: dict = REPAIRS, batch: str = BATCH) -> dict:
    tasks = {row["id"]: row for row in source["content"]["tasks"]}
    result = {"batch": batch, "mode": "in_place_owner_requested",
              "source_checked_at": source["checked_at"], "student_data_included": False,
              "repairs": []}
    for task_id, spec in repairs.items():
        row = tasks[task_id]
        changes = {k: v for k, v in spec["changes"].items() if row.get(k) != v}
        # Parallel columns travel together even if one already has its final value.
        for raw, display in (("question_text", "question_latex"),
                             ("correct_answer", "correct_answer_latex"),
                             ("answer_options", "answer_options_latex")):
            if raw in changes or display in changes:
                changes[raw], changes[display] = spec["changes"][raw], spec["changes"][display]
        entry = {"id": task_id, "before_sha256": fingerprint(row),
                 "reason": spec["reason"], "evidence": spec["evidence"], "changes": changes}
        after = candidate(row, entry, batch)
        entry["after_sha256"] = fingerprint(after)
        validate_entry(entry)
        validate_choices(after)
        result["repairs"].append(entry)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build(json.loads(args.source.read_text())),
                                     ensure_ascii=False, indent=2) + "\n")
