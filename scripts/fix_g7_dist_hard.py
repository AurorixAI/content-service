#!/usr/bin/env python3
"""Hand-finish stubborn G7 distractor gaps — validated + atomic persist."""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.answer_sympy_gate import enrich_distractor_latex, to_answer_latex
from src.pipeline.distractor_gate import validate_distractor_set

# task_id -> list of (value, error_logic)
MANUAL: dict[str, list[tuple[str, str]]] = {
    "G7_TB_4_88.1": [
        ("-1 < -2 < 0", "Перепутан порядок чисел на координатной прямой слева направо"),
        ("-2 < 0 < -1", "Ноль поставлен между -2 и -1, хотя он правее -1"),
        ("0 < -2 < -1", "Все три числа записаны в обратном порядке"),
    ],
    "G7_TB_4_88.2": [
        ("-0,1 < -0,5 < 0,1", "Перепутаны местами -0,5 и -0,1 на прямой"),
        ("-0,5 < 0,1 < -0,1", "Положительное 0,1 оказалось левее отрицательного -0,1"),
        ("0,1 < -0,5 < -0,1", "Числа расположены не по возрастанию слева направо"),
    ],
    "G7_TB_4_88.3": [
        ("-1,25 < -1,5 < -1", "Меньшее число -1,5 поставлено правее -1,25"),
        ("-1,5 < -1 < -1,25", "Число -1 стоит между -1,5 и -1,25 ошибочно"),
        ("-1 < -1,5 < -1,25", "Нарушен порядок отрицательных чисел на прямой"),
    ],
    "G7_TB_4_76.3": [
        ("-3,65 < -3,7 < -3,6", "Перепутан порядок -3,7 и -3,65"),
        ("-3,7 < -3,6 < -3,65", "Число -3,6 поставлено между -3,7 и -3,65"),
        ("-3,6 < -3,65 < -3,7", "Все три числа записаны в неверном порядке"),
    ],
    "G7_TB_3_43.4": [
        ("2 + 2 / 2 = 3", "Сначала выполнено деление, а не сложение в скобках"),
        ("(2 + 2) * 2 = 8", "Вместо деления на 2 ошибочно умножили на 2"),
        ("2 / 2 + 2 = 3", "Скобки не учтены: сначала деление, потом сложение"),
    ],
    "G7_TB_32_836.2": [
        (
            "(x + y)^2 - (x - y)^2 = (x^2 + 2xy + y^2) - (x^2 - 2xy + y^2) = 2y^2",
            "При раскрытии скобок потерян член 4xy, получили только 2y^2",
        ),
        (
            "(x + y)^2 - (x - y)^2 = x^2 + y^2 - x^2 + y^2 = 2y^2",
            "Неверно раскрыты квадраты суммы и разности",
        ),
        (
            "(x + y)^2 - (x - y)^2 = 4x",
            "Оставили только слагаемые с x, потеряв члены с y",
        ),
    ],
    "G7_TB_32_836.3": [
        (
            "((x+y)-(x-y))^2 = (2x)^2 = 4x^2",
            "Ошибочно получили 2x вместо 2y при вычитании скобок",
        ),
        (
            "((x+y)-(x-y))^2 = (x+y-x-y)^2 = 0",
            "Неверно упростили разность перед возведением в квадрат",
        ),
        (
            "((x+y)-(x-y))^2 = 2y^2",
            "Забыли возвести множитель 2y в квадрат",
        ),
    ],
    "G7_TB_32_836.4": [
        (
            "((x+y)^2 - (x-y)^2)((x+y)^2 + (x-y)^2) = 4xy * (x^2+y^2) = 4xy^3 + 4x^3y",
            "Ошибочно не удвоили второй множитель (x^2+y^2)",
        ),
        (
            "((x+y)^2 - (x-y)^2)((x+y)^2 + (x-y)^2) = 2xy * 2(x^2+y^2) = 4xy(x^2+y^2)",
            "Неверно вычислен первый множитель 4xy как 2xy",
        ),
        (
            "((x+y)^2 - (x-y)^2)((x+y)^2 + (x-y)^2) = 8x^2y^2",
            "Перемножили множители без приведения к виду 8xy(x^2+y^2)",
        ),
    ],
    "G7_TB_32_837.1": [
        (
            "(n+1)^2 - n^2 = n^2 + 2n + 1 - n^2 = 2n",
            "После раскрытия квадрата забыли единицу, получили 2n",
        ),
        (
            "(n+1)^2 - n^2 = n^2 + 1 - n^2 = 1",
            "Потеряли слагаемое 2n при раскрытии (n+1)^2",
        ),
        (
            "(n+1)^2 - n^2 = 2n - 1",
            "Неверный знак при вычитании n^2",
        ),
    ],
    "G7_TB_37_968.2": [
        (
            "(x + y)^2 - (x - y)^2 = (x^2 + 2xy + y^2) - (x^2 - 2xy + y^2) = 2y^2",
            "При раскрытии скобок потерян член 4xy",
        ),
        (
            "(x + y)^2 - (x - y)^2 = x^2 - y^2",
            "Смешаны формулы квадрата суммы и разности квадратов",
        ),
        (
            "(x + y)^2 - (x - y)^2 = 4x",
            "Оставили только слагаемые с переменной x",
        ),
    ],
    "G7_TB_28_689.2": [
        (
            "16^4 - 2^{13} = 2^{16} - 2^{13} = 2^{13} \\cdot 8",
            "Ошибочно приняли 2^3 - 1 за 8 вместо 7",
        ),
        (
            "16^4 - 2^{13} = 2^{16} - 2^{13} = 2^{12} \\cdot 15",
            "Неверно вынесли множитель при разложении степеней двойки",
        ),
        (
            "16^4 - 2^{13} = 2^{14}",
            "Сложили показатели вместо приведения к общему основанию",
        ),
    ],
    "G7_TB_6_129.2": [
        (
            "4a - (3a - (2a - 1)) = 4a - (3a - 2a - 1) = 4a - a + 1 = 3a + 1",
            "Ошибка знака при раскрытии внутренних скобок",
        ),
        (
            "4a - (3a - (2a - 1)) = 4a - 3a - 2a + 1 = -a + 1",
            "Неверно сняли все скобки одновременно",
        ),
        (
            "4a - (3a - (2a - 1)) = 4a - (3a - 2a + 1) = 4a - a + 1 = 3a + 1",
            "Плюс перед 1 превратили в минус при раскрытии",
        ),
    ],
    "G7_ALG_39_4": [
        (
            "Для a = -10: a^2 = -100, -a^2 = 100, (-a)^2 = 100, (-a)^3 = -1000",
            "Перепутаны знаки при возведении -10 в квадрат и куб",
        ),
        (
            "Для a = -10: a^2 = 100, -a^2 = 100, (-a)^2 = -100, (-a)^3 = 1000",
            "Ошибка со знаком у (-a)^2 и (-a)^3",
        ),
        (
            "Для a = 5: a^2 = 10, -a^2 = -25, (-a)^2 = 25, (-a)^3 = 125",
            "Неверно вычислен квадрат числа 5",
        ),
    ],
}


STABLE_LOCK_IDS = frozenset({
    "G7_TB_32_836.2",
    "G7_TB_32_837.1",
    "G7_TB_6_129.2",
})


def _build_meta(items: list[dict]) -> list[dict]:
    return [
        {
            "value": d["value"],
            "error_type": "ai_generated",
            "explanation": d["error_logic"],
            "error_logic": d["error_logic"],
            "plausibility": 0.75,
        }
        for d in items
    ]


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--lock-stable",
        action="store_true",
        help="Re-apply + lock STABLE_LOCK_IDS (proof dist that must not regress)",
    )
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    ok = fail = 0

    with engine.connect() as conn:
        if args.lock_stable:
            gap_ids = list(STABLE_LOCK_IDS)
        else:
            gap_ids = [
                r[0]
                for r in conn.execute(
                    text("""
                        SELECT tm.id FROM tasks_master tm
                        JOIN textbook_toc toc ON toc.id = tm.toc_id
                        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                        WHERE tb.class_level = 7
                          AND jsonb_array_length(COALESCE(tm.distractor_meta, '[]'::jsonb)) < 2
                    """),
                ).fetchall()
            ]

    for tid in gap_ids:
        manual = MANUAL.get(tid)
        if not manual:
            print(f"SKIP {tid} — no manual distractors")
            fail += 1
            continue

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT question_text, correct_answer, answer_type, tags "
                    "FROM tasks_master WHERE id = :id"
                ),
                {"id": tid},
            ).fetchone()
        question, answer, atype, tags_raw = row
        tags = dict(tags_raw or {})
        raw = [{"value": v, "error_logic": el} for v, el in manual]
        accepted, rejected = validate_distractor_set(
            raw,
            question=question or "",
            correct_answer=answer or "",
            answer_type=atype or "text",
            max_count=3,
            skip_l3=atype in ("text", "open_text", "coordinate", "inequality", "set"),
        )
        if len(accepted) < 2:
            print(f"FAIL {tid}: only {len(accepted)} passed gate")
            for r in rejected[:4]:
                print(f"  {r.get('value', '')[:60]} -> {r.get('gate_reason')}")
            fail += 1
            continue

        dmeta = enrich_distractor_latex(_build_meta(accepted), atype or "text")
        cal = to_answer_latex(answer or "", atype or "text")
        tags["choices_complete"] = True
        tags.pop("distractor_regen_pending", None)
        tags.pop("distractor_regen_exhausted", None)
        tags.pop("distractor_regen_attempts", None)
        tags["distractor_gate_passed"] = len(dmeta)
        if tid in STABLE_LOCK_IDS:
            tags["distractor_locked"] = True
            tags["answer_locked"] = True
            tags["dist_stable_lock"] = True

        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET distractor_meta = cast(:dmeta as jsonb),
                        correct_answer_latex = :cal,
                        tags = cast(:tags as jsonb),
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {
                    "id": tid,
                    "dmeta": json.dumps(dmeta, ensure_ascii=False),
                    "cal": cal,
                    "tags": json.dumps(tags, ensure_ascii=False),
                },
            )
        print(f"OK {tid} +{len(dmeta)}")
        ok += 1

    with engine.connect() as conn:
        gaps = conn.execute(
            text("""
                SELECT COUNT(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 7
                  AND jsonb_array_length(COALESCE(distractor_meta,'[]'::jsonb)) < 2
            """),
        ).scalar()
    print(f"Done: ok={ok} fail={fail} remaining_gaps={gaps}")
    return 0 if gaps == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
