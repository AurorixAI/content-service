#!/usr/bin/env python3
"""Re-verify G5 trust_textbook LLM mismatches with fresh Gemini + deep math."""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from collections import Counter
from fractions import Fraction

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.answer_sympy import try_validate_expression_answer
from src.pipeline.answer_verify import answers_equivalent
from src.pipeline.smart_verify_text import _run_text_llm

log = logging.getLogger("audit_g5_llm_mismatch")
logging.basicConfig(level=logging.INFO, format="%(message)s")

MANUAL_DONE = {
    "G5_TB_13_245", "G5_TB_21_844", "G5_TB_25_987", "G5_TB_4_66",
    "G5_TB_10_386.2", "G5_TB_41_726", "G5_TB_44_1718.4", "G5_TB_55_1292",
}


def _nums(s: str) -> list[float]:
    out = []
    for m in re.finditer(r"\d+(?:[.,]\d+)?", (s or "").replace(" ", "")):
        out.append(float(m.group().replace(",", ".")))
    return out


def _letters(s: str) -> list[str]:
    return re.findall(r"\b([абвгдежз])\)", (s or "").lower())


def _eval_expr(expr: str) -> float | None:
    s = (expr or "").strip().replace(" ", "").replace(",", ".")
    s = re.sub(r"(\d)\.(\d)", r"\1.\2", s)
    s = s.replace(":", "/")
    if not re.fullmatch(r"[\d+\-*/().]+", s):
        return None
    try:
        return float(eval(s, {"__builtins__": {}}))
    except Exception:
        return None


def _extract_compute_answer(q: str) -> float | None:
    m = re.search(
        r"Найдите значение выражения\s*\n?(.+)",
        q or "",
        re.S | re.I,
    )
    if not m:
        return None
    return _eval_expr(m.group(1).strip())


def judge(stored: str, llm: str, q: str, tid: str) -> dict:
    stored = (stored or "").strip()
    llm = (llm or "").strip()
    if tid in MANUAL_DONE:
        return {"verdict": "keep_manual", "reason": "уже исправлено вручную", "winner": stored}

    if not llm:
        return {"verdict": "keep_tb", "reason": "LLM пустой", "winner": stored}

    if answers_equivalent(stored, llm, "text", question=q):
        return {"verdict": "equivalent", "reason": "answers_equivalent", "winner": stored}

    ns, nl = _nums(stored), _nums(llm)
    if ns and nl and ns == nl:
        return {"verdict": "equivalent", "reason": "те же числа", "winner": stored}

    # single numeric from expression task
    calc = _extract_compute_answer(q)
    if calc is not None and len(ns) == 1 and len(nl) == 1:
        if abs(ns[0] - calc) < 0.51 and abs(nl[0] - calc) > 0.51:
            return {"verdict": "fix_llm", "reason": f"calc={calc}, LLM верен", "winner": llm}
        if abs(nl[0] - calc) < 0.51 and abs(ns[0] - calc) > 0.51:
            return {"verdict": "fix_tb", "reason": f"calc={calc}, TB неверен", "winner": llm}
        if abs(ns[0] - calc) < 0.51:
            return {"verdict": "keep_tb", "reason": f"calc={calc}≈TB", "winner": stored}
        if abs(nl[0] - calc) < 0.51:
            return {"verdict": "fix_llm", "reason": f"calc={calc}≈LLM", "winner": llm}

    if ns and nl and ns != nl:
        # multi-value: check each via sympy on sub-parts if possible
        if len(ns) == len(nl):
            diffs = sum(1 for a, b in zip(ns, nl) if abs(a - b) > 0.51)
            if diffs == 0:
                return {"verdict": "equivalent", "reason": "multi numeric match", "winner": stored}
        return {"verdict": "review_numeric", "reason": f"TB nums {ns[:5]} vs LLM {nl[:5]}", "winner": None}

    # MCQ letter
    ls, ll = _letters(stored), _letters(llm)
    if ls or ll or re.fullmatch(r"[АБВГ]", stored.strip(), re.I):
        ts = stored.strip().upper()
        tl = llm.strip().upper()
        if ts != tl and re.fullmatch(r"[АБВГ]", ts) and re.fullmatch(r"[АБВГ]", tl):
            return {"verdict": "review_mcq", "reason": f"TB={ts} LLM={tl}", "winner": None}

    # LLM refuses figure
    if re.search(r"недостаточно|отсутствует|невозможно определить", llm, re.I):
        if re.search(r"рис\.|рисун|шкал|термометр", q, re.I):
            if len(stored) > 15 and "недостаточно" not in stored.lower():
                return {"verdict": "keep_tb", "reason": "TB условный ответ при отсутствии рис.", "winner": stored}
            return {"verdict": "review_figure", "reason": "оба про отсутствие данных", "winner": None}

    # units strip
    def strip_units(x: str) -> str:
        x = re.sub(
            r"\s*(км/ч|м/с|км|мм|см|м²|м³|м\^2|м\^3|кг|г|т|ц|га|а|°|мин|ч|дм\^3|дм³|сум|л|%|дет\./ч)\b",
            "",
            x,
            flags=re.I,
        )
        return re.sub(r"\s+", " ", x).strip().lower()

    su, lu = strip_units(stored), strip_units(llm)
    if su and lu and (su == lu or su in lu or lu in su):
        return {"verdict": "equivalent", "reason": "units/format only", "winner": stored}

    # mixed fractions in kg
    if "кг" in stored.lower() and "/" in stored and "/" in llm:
        def improper_parts(s: str) -> list[Fraction]:
            out = []
            for a, b in re.findall(r"(\d+)\s*/\s*(\d+)", s):
                out.append(Fraction(int(a), int(b)))
            for w, a, b in re.findall(r"(\d+)\s+(\d+)\s*/\s*(\d+)", s):
                out.append(Fraction(int(w)) + Fraction(int(a), int(b)))
            return out

        ps, pl = improper_parts(stored), improper_parts(llm)
        if ps and pl and sorted(ps) == sorted(pl):
            return {"verdict": "equivalent", "reason": "дроби эквивалентны", "winner": stored}

    sw = set(re.findall(r"\w{4,}", stored.lower()))
    lw = set(re.findall(r"\w{4,}", llm.lower()))
    overlap = len(sw & lw) / max(len(sw | lw), 1)
    if overlap >= 0.72:
        return {"verdict": "equivalent", "reason": f"paraphrase {overlap:.0%}", "winner": stored}
    if overlap >= 0.5:
        return {"verdict": "review_paraphrase", "reason": f"overlap {overlap:.0%}", "winner": None}

    return {"verdict": "review_other", "reason": "существенное расхождение", "winner": None}


def fetch_tasks(engine) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type, tm.tags
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 5
                  AND tm.tags->>'fix_g5_human_review' = 'trust_textbook'
                ORDER BY tm.id
            """)
        ).mappings().all()
    return [dict(r) for r in rows]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=float, default=0.5)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--report", default="/tmp/g5_llm_mismatch_audit.json")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    rows = fetch_tasks(engine)
    if args.limit:
        rows = rows[: args.limit]
    log.info("Re-verify trust_textbook: %d tasks", len(rows))

    results = []
    verdicts = Counter()
    fixes: dict[str, str] = {}

    for i, row in enumerate(rows, 1):
        tid = row["id"]
        stored = (row["correct_answer"] or "").strip()
        q = row["question_text"] or ""
        llm_resp = _run_text_llm(tid, q, stored, alt_method=False, temperature=0.1)
        llm = (llm_resp.absolute_correct_answer if llm_resp else "") or ""
        conf = llm_resp.confidence if llm_resp else ""
        j = judge(stored, llm, q, tid)
        j["id"] = tid
        j["stored"] = stored
        j["llm"] = llm
        j["confidence"] = conf
        j["question"] = q[:200]
        results.append(j)
        verdicts[j["verdict"]] += 1
        if j["verdict"] in ("fix_llm", "fix_tb") and j.get("winner"):
            fixes[tid] = j["winner"]
        log.info(
            "[%d/%d] %s %s | TB=%s | LLM=%s",
            i,
            len(rows),
            tid,
            j["verdict"],
            stored[:45],
            llm[:45],
        )
        if args.sleep:
            time.sleep(args.sleep)

    print("\nVERDICTS:", dict(verdicts))
    review = [r for r in results if r["verdict"].startswith("review_")]
    print(f"\nNEEDS HUMAN DECISION ({len(review)}):")
    for r in review:
        print(f"  {r['id']} [{r['verdict']}] {r['reason']}")
        print(f"    TB:  {r['stored'][:90]}")
        print(f"    LLM: {r['llm'][:90]}")

    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    log.info("Report: %s", args.report)

    if args.apply and fixes:
        from src.pipeline.smart_verify_common import clear_stale_verify_flags, sync_verify_tags

        with engine.begin() as conn:
            for tid, ans in fixes.items():
                row = next(r for r in rows if r["id"] == tid)
                tags = dict(row["tags"] or {})
                clear_stale_verify_flags(tags)
                sync_verify_tags(tags, "verified_corrected")
                tags["answer_corrected_reaudit"] = "true"
                tags["answer_locked"] = True
                conn.execute(
                    text("""
                        UPDATE tasks_master
                        SET correct_answer = :a, tags = cast(:t AS jsonb)
                        WHERE id = :id
                    """),
                    {"id": tid, "a": ans, "t": json.dumps(tags, ensure_ascii=False)},
                )
        log.info("Applied %d fixes", len(fixes))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
