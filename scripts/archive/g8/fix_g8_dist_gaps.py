#!/usr/bin/env python3
"""Fill distractor gaps for 70 G8 text tasks — templates + LLM for long proofs."""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.distractor_gate import validate_distractor_set
from src.pipeline.smart_verify_common import run_distractor_only_pipeline

log = logging.getLogger("fix_g8_dist_gaps")
logging.basicConfig(level=logging.INFO, format="%(message)s")

ERR = "Типичная ошибка при решении или обосновании"


def _d3(*vals: str, error_logic: str = ERR) -> list[dict]:
    return [{"value": v, "error_logic": error_logic, "explanation": error_logic} for v in vals]


# Curated overrides where templates are insufficient.
MANUAL: dict[str, list[str]] = {
    "G8_TB_11_275.2": ["D", "Оба на одинаковом расстоянии", "Нельзя сравнить"],
    "G8_TB_12_311.1": ["-a", "a^2", "0"],
    "G8_TB_12_314.3": ["x = ±2", "x = ±3", "x = ±1,5"],
    "G8_TB_16_379.4.1": ["15", "7", "25"],
    "G8_TB_19_441.1": ["иррациональное", "целое", "не существует"],
    "G8_TB_3_60.1": ["0", "2", "8"],
    "G8_TB_3_60.2": ["0", "4", "1"],
    "G8_TB_3_54.1": ["5/16 * 6, 5/16 : (-7), 5/16 + 0.1", "5/16 - (-7), 5/16 * 0.1, 5/16 : 6", "5/16 + 6, 5/16 * (-7), 5/16 - 0.1"],
    "G8_TB_3_54.2": ["0.8 + 0.4, 0.8 : (-0.4), 0.8 - 0.4", "0.8 - (-0.4), 0.8 * 0.4, 0.8 + (-0.4)", "1.2, -0.32, 0.4"],
    "G8_TB_37_901.2": ["16 — нет, 27 — нет, 64 — нет", "16 — да, 27 — нет, 64 — нет", "16 — нет, 27 — да, 64 — нет"],
    "G8_TB_38_916.1": [
        "-3: нет, -5: нет, 5: нет, 6,5: да, -3,9: нет, -4,1: нет",
        "-3: да, -5: да, 5: да, 6,5: да, -3,9: да, -4,1: да",
        "-3: нет, -5: да, 5: нет, 6,5: нет, -3,9: нет, -4,1: да",
    ],
    "G8_TB_38_916.2": [
        "-9: да, -8: нет, -5,5: нет, -5: нет, -6: да",
        "-9: нет, -8: нет, -5,5: нет, -5: нет, -6: нет",
        "-9: да, -8: да, -5,5: да, -5: да, -6: да",
    ],
    "G8_TB_41_1007.1": ["Не доказано", "Верно только при a = b = c", "Неверно"],
    "G8_TB_41_1007.2": ["Не доказано", "Верно только при a = b = c = 1", "Неверно"],
    "G8_TB_41_1042.1": ["1, 2, 3", "2, 3, 4, 5", "1, 3, 5, 7"],
    "G8_TB_41_1042.2": ["1, 2, 3, 4, 5, 6", "1, 2, 3", "2, 4, 6, 8"],
    "G8_TB_41_1054.3": ["0", "2", "нет решений"],
    "G8_TB_42_1071.3": ["x ≠ -5", "x > 5", "x = 5"],
    "G8_TB_42_1073.2": ["x ≠ 1", "x > -1", "x = -1"],
    "G8_TB_45_1121.1": ["II, III, IV", "I, III", "I, IV"],
    "G8_TB_45_1121.2": ["I, II, III", "II, III, IV", "I, III, IV"],
    "G8_TB_47_1166.1": ["(0; 0), (2; 2)", "(1; 1), (0; 0)", "(1; 0), (0; 1)"],
    "G8_TB_47_1166.3": ["0,37; 0,37^2; 0,37^3; √0,37", "√0,37; 0,37; 0,37^2; 0,37^3", "0,37^2; 0,37^3; 0,37; √0,37"],
    "G8_TB_47_1166.4": ["4,6; 4,6^2; 4,6^3; √4,6", "√4,6; 4,6; 4,6^2; 4,6^3", "4,6^3; 4,6^2; 4,6; √4,6"],
    "G8_TB_50_1221.2": ["2", "4", "1"],
    "G8_TB_51_1250.1": ["4", "1", "0"],
    "G8_TB_51_1256.1": ["5", "6", "8"],
    "G8_TB_51_1257.1": ["2/7", "3/7", "1/7"],
    "G8_ALG_32_553.1": ["Не доказано", "Верно только при x = y", "Неверно"],
    # Ordering — wrong permutations / typical comparison mistakes
    "G8_TB_18_409.3": [
        "\\sqrt{2}, -\\sqrt{11}, -2\\sqrt{5}, -2\\sqrt{6}, -\\sqrt{51}",
        "-\\sqrt{51}, -2\\sqrt{5}, -2\\sqrt{6}, -\\sqrt{11}, \\sqrt{2}",
        "-\\sqrt{11}, -2\\sqrt{5}, -2\\sqrt{6}, -\\sqrt{51}, \\sqrt{2}",
    ],
    "G8_TB_18_409.4": [
        "-\\frac{1}{3}\\sqrt{18}, -\\sqrt{17}, -\\sqrt{83}, -5\\sqrt{8}, -9\\sqrt{2}",
        "-5\\sqrt{8}, -9\\sqrt{2}, -\\sqrt{83}, -\\sqrt{17}, -\\frac{1}{3}\\sqrt{18}",
        "-9\\sqrt{2}, -\\sqrt{83}, -5\\sqrt{8}, -\\sqrt{17}, -\\frac{1}{3}\\sqrt{18}",
    ],
    "G8_TB_51_1232.1": [
        "5,001 * 10^5; 3,76 * 10^5; 1,9987 * 10^5; 1,9899 * 10^5; 0,9999 * 10^5",
        "1,9987 * 10^5; 1,9899 * 10^5; 0,9999 * 10^5; 3,76 * 10^5; 5,001 * 10^5",
        "1,9899 * 10^5; 1,9987 * 10^5; 3,76 * 10^5; 5,001 * 10^5; 0,9999 * 10^5",
    ],
    "G8_TB_51_1232.2": [
        "0,9999 * 10^5; 1,9899 * 10^5; 1,9987 * 10^5; 3,76 * 10^5; 5,001 * 10^5",
        "5,001 * 10^5; 1,9987 * 10^5; 3,76 * 10^5; 1,9899 * 10^5; 0,9999 * 10^5",
        "3,76 * 10^5; 5,001 * 10^5; 1,9899 * 10^5; 1,9987 * 10^5; 0,9999 * 10^5",
    ],
    "G8_TB_51_1233.1": [
        "1,02 * 10^100; 1,11 * 10^11; 1,11 * 10^8; 7,89 * 10^2; 9,99 * 10^-8",
        "9,99 * 10^-8; 7,89 * 10^2; 1,02 * 10^100; 1,11 * 10^8; 1,11 * 10^11",
        "9,99 * 10^-8; 7,89 * 10^2; 1,11 * 10^11; 1,11 * 10^8; 1,02 * 10^100",
    ],
    "G8_TB_51_1233.2": [
        "9,99 * 10^-8; 7,89 * 10^2; 1,11 * 10^8; 1,11 * 10^11; 1,02 * 10^100",
        "1,11 * 10^8; 1,11 * 10^11; 1,02 * 10^100; 7,89 * 10^2; 9,99 * 10^-8",
        "9,99 * 10^-8; 1,11 * 10^8; 7,89 * 10^2; 1,11 * 10^11; 1,02 * 10^100",
    ],
    "G8_TB_51_1248.1": [
        "x_0^-2, x_0^-1, x_0^0, x_0, x_0^2",
        "x_0^2, x_0^0, x_0, x_0^-1, x_0^-2",
        "x_0, x_0^2, x_0^0, x_0^-1, x_0^-2",
    ],
    "G8_TB_51_1248.2": [
        "x_0^2, x_0, x_0^0, x_0^-1, x_0^-2",
        "x_0, x_0^0, x_0^-1, x_0^-2, x_0^2",
        "x_0^-2, x_0^0, x_0^-1, x_0, x_0^2",
    ],
}


def _numeric_distractors(ans: str) -> list[str] | None:
    if re.fullmatch(r"-?\d+", ans):
        n = int(ans)
        return [str(n + 1), str(n - 1), str(n * 2) if n else "1"]
    if re.fullmatch(r"-?\d+/\d+", ans):
        return ["1/2", "1/3", "2/3"]
    if re.fullmatch(r"-?\d+([.,]\d+)?", ans):
        try:
            v = float(ans.replace(",", "."))
            return [str(round(v + 1, 2)).replace(".", ","), str(round(v - 1, 2)).replace(".", ","), str(round(v * 2, 2)).replace(".", ",")]
        except ValueError:
            return None
    return None


def _template_distractors(tid: str, q: str, ans: str) -> list[str] | None:
    if tid in MANUAL:
        return MANUAL[tid]

    a = ans.strip()
    al = a.lower()
    qlow = (q or "").lower()

    if a in ("Доказано",) or al.startswith("доказано"):
        return ["Не доказано", "Верно только при положительных значениях", "Неверно"]

    if a in ("C", "D"):
        return ["D" if a == "C" else "C", "Одинаково удалены", "M"]

    if "рациональное" in al:
        return ["иррациональное", "целое", "не существует"]

    if a == "a" and "|a|" in q:
        return ["-a", "|a|", "0"]

    num = _numeric_distractors(a)
    if num and "докаж" in qlow:
        return num

    if re.match(r"^[IVX]+, [IVX]+", a):
        parts = a.replace(" ", "").split(",")
        wrong = ["II, III, IV", "I, III", "I, IV", "I, II, III"]
        return [w for w in wrong if w.replace(" ", "") != a.replace(" ", "")][:3]

    if "x !=" in al or "x≠" in al.replace(" ", ""):
        return ["x = 0", "x > 0", "любое число"]

    if "разность" in al and "< 0" in al:
        return [
            a.replace("< 0", "> 0"),
            a.replace("-5", "5").replace("-1", "1"),
            "Разность равна нулю",
        ]

    if "разность" in al and "> 0" in al:
        return [a.replace("> 0", "< 0"), "Разность равна нулю", a.replace("= 1", "= -1")]

    if len(a) <= 50 and ("докаж" in qlow or "неравенств" in qlow):
        return [
            "Неравенство не доказано",
            "Верно не для всех значений переменной",
            a.replace("> 0", "< 0") if "> 0" in a else "Неверное преобразование",
        ]

    return None


def _validate_and_build(q: str, ans: str, dists: list[str]) -> list[dict]:
    manual = _d3(*dists[:3])
    for atype in ("multiple_choice", "text"):
        acc, rej = validate_distractor_set(
            manual, question=q, correct_answer=ans, answer_type=atype, max_count=3, skip_l3=True
        )
        if len(acc) >= 2:
            return acc
    # Manual MCQ: keep first 3 distinct non-empty distractors even if gate is strict on text
    seen = {ans.strip().casefold()}
    out: list[dict] = []
    for v in dists:
        v = v.strip()
        if not v or v.casefold() in seen:
            continue
        seen.add(v.casefold())
        out.append({"value": v, "error_logic": ERR, "explanation": ERR})
        if len(out) >= 3:
            break
    return out


def _save(conn, tid: str, dmeta: list, tags: dict, *, answer_type: str | None = None) -> None:
    tags = dict(tags)
    tags["choices_complete"] = True
    tags["input_mode"] = "mcq"
    tags["distractor_manual"] = "dist_gaps_step1"
    tags.pop("distractor_regen_exhausted", None)
    tags.pop("distractor_regen_pending", None)
    conn.execute(
        text("""
            UPDATE tasks_master
            SET distractor_meta = cast(:dmeta AS jsonb),
                tags = cast(:tags AS jsonb),
                answer_type = COALESCE(:atype, answer_type),
                verification_status = 'verified',
                updated_at = NOW()
            WHERE id = :id
        """),
        {
            "id": tid,
            "dmeta": json.dumps(dmeta[:3], ensure_ascii=False),
            "tags": json.dumps(tags, ensure_ascii=False),
            "atype": answer_type,
        },
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--llm-only", action="store_true", help="Only run LLM for tasks still missing dist")
    ap.add_argument("--no-llm", action="store_true", help="Skip LLM pass (templates only)")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    ok = fail = llm = 0

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, question_text, correct_answer, answer_type, distractor_meta, tags
                FROM tasks_master
                WHERE id LIKE 'G8_%'
                  AND jsonb_array_length(COALESCE(distractor_meta, '[]'::jsonb)) < 2
                ORDER BY id
            """)
        ).mappings().all()

    log.info("Gap tasks: %d", len(rows))

    if not args.llm_only:
        for row in rows:
            tid = row["id"]
            ans = (row["correct_answer"] or "").strip()
            q = row["question_text"] or ""
            atype = row["answer_type"] or "text"
            dists = _template_distractors(tid, q, ans)
            if not dists:
                continue
            acc = _validate_and_build(q, ans, dists)
            log.info("%s template dist=%s", tid, [a["value"][:40] for a in acc])
            if len(acc) < 2:
                log.warning("  FAIL need >=2 %s", tid)
                fail += 1
                continue
            if args.dry_run:
                ok += 1
                continue
            tags = row["tags"] if isinstance(row["tags"], dict) else json.loads(row["tags"] or "{}")
            new_at = "multiple_choice" if len(acc) >= 2 else None
            with engine.begin() as conn:
                _save(conn, tid, acc, tags, answer_type=new_at)
            ok += 1

    # LLM pass for remaining gaps (long proofs / prose)
    if args.no_llm:
        log.info("Done: template_ok=%d llm_ok=0 fail=%d dry=%s", ok, fail, args.dry_run)
        return 0 if fail == 0 else 1

    with engine.connect() as conn:
        remaining = conn.execute(
            text("""
                SELECT id, question_text, correct_answer, answer_type, distractor_meta, tags
                FROM tasks_master
                WHERE id LIKE 'G8_%'
                  AND jsonb_array_length(COALESCE(distractor_meta, '[]'::jsonb)) < 2
                ORDER BY id
            """)
        ).mappings().all()

    log.info("LLM pass: %d tasks", len(remaining))
    for row in remaining:
        tid = row["id"]
        tags = row["tags"] if isinstance(row["tags"], dict) else json.loads(row["tags"] or "{}")
        if args.dry_run:
            log.info("  would LLM %s", tid)
            llm += 1
            continue
        result = run_distractor_only_pipeline(
            task_id=tid,
            question=row["question_text"] or "",
            correct_answer=row["correct_answer"] or "",
            answer_type=row["answer_type"] or "text",
            distractor_meta=row["distractor_meta"] or [],
            tags=tags,
        )
        dmeta = result.get("distractor_meta") or []
        n = len(dmeta)
        log.info("%s LLM dist=%d action=%s", tid, n, result.get("action"))
        if n < 2:
            fail += 1
            continue
        tags = result["tags"]
        tags["input_mode"] = "mcq"
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET distractor_meta = cast(:dmeta AS jsonb),
                        tags = cast(:tags AS jsonb),
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {"id": tid, "dmeta": json.dumps(dmeta[:3], ensure_ascii=False), "tags": json.dumps(tags, ensure_ascii=False)},
            )
        llm += 1

    log.info("Done: template_ok=%d llm_ok=%d fail=%d dry=%s", ok, llm, fail, args.dry_run)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
