#!/usr/bin/env python3
"""Раздел «Ответы» книги → `tasks_staging` (инвариант И2).

Почему отдельным шагом, а не внутри `orchestrator`:

Раздел «Ответы» — это отдельный диапазон страниц в конце книги, а не часть
параграфа. Конвейер идёт по листовым параграфам оглавления и до этих страниц
не доходит вовсе (они помечены служебными и пропускаются — и правильно, задач
там нет). Поэтому join ответов делается **производной операцией** поверх уже
записанного staging: разобрали раздел → пришили по номеру → пересчитали
вердикт. Так же он идемпотентен — повторный запуск переприменяет join, а не
затирает данные (это и был баг B2 в прототипе).

    docker exec content-worker python /app/scripts/apply_answer_key.py \\
        --textbook-id <uuid> --pdf /textbooks/book.pdf [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

# Работает и в контейнере (/app), и из корня репозитория на хосте.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from src.pipeline import answer_key as AK  # noqa: E402
from src.pipeline import gates as G  # noqa: E402
from src.pipeline import provenance as prov  # noqa: E402
from src.pipeline import scoring as SC  # noqa: E402
from src.pipeline.db_writer import _engine  # noqa: E402
from src.pipeline.models import ExtractedTask  # noqa: E402
from src.pipeline.ocr import GeminiVisionOCR  # noqa: E402
from src.pipeline.ocr_utils import is_usable_ocr_text  # noqa: E402

#: Заголовки, по которым раздел ответов опознаётся в оглавлении.
_ANSWER_TITLES = ("ответ", "javob")

_LOAD_SQL = """
SELECT staging_id, task_id, paragraph_number, exercise_number, page,
       question_text, question_latex, shared_context, correct_answer,
       answer_type, answer_options, answer_source, text_source,
       answer_source_page, confidence
FROM tasks_staging
WHERE textbook_id = CAST(:tb AS UUID)
ORDER BY staging_id
"""

_UPDATE_SQL = """
UPDATE tasks_staging SET
    correct_answer     = :correct_answer,
    answer_source      = :answer_source,
    answer_source_page = :answer_source_page,
    confidence         = CAST(:confidence AS JSONB),
    gate_status        = :gate_status,
    gate_reasons       = CAST(:gate_reasons AS JSONB),
    updated_at         = NOW()
WHERE staging_id = :staging_id
"""


def answer_pages_from_toc(tb_id: str) -> tuple[int, int] | None:
    """Диапазон страниц раздела «Ответы» по оглавлению."""
    with _engine().connect() as conn:
        rows = conn.execute(
            text("""SELECT title, page_start, page_end FROM textbook_toc
                    WHERE textbook_id = CAST(:tb AS UUID) ORDER BY sort_order"""),
            {"tb": tb_id},
        ).fetchall()
    for title, start, end in rows:
        low = str(title or "").lower()
        if any(m in low for m in _ANSWER_TITLES) and start:
            return int(start), int(end or start)
    return None


def load_staged(tb_id: str):
    with _engine().connect() as conn:
        rows = conn.execute(text(_LOAD_SQL), {"tb": tb_id}).mappings().all()
    tasks, ids = [], []
    for r in rows:
        t = ExtractedTask(
            temp_id=r["task_id"],
            paragraph_number=r["paragraph_number"] or "",
            exercise_number=r["exercise_number"] or "",
            page=r["page"] or 0,
            question_text=r["question_text"] or "",
            question_latex=r["question_latex"] or "",
            shared_context=r["shared_context"] or "",
            answer_raw=r["correct_answer"] or "",
            answer_type=r["answer_type"] or "exact_number",
            answer_source=r["answer_source"] or prov.ABSENT,
            text_source=r["text_source"] or prov.BOOK_OCR,
            answer_source_page=r["answer_source_page"],
        )
        opts = r["answer_options"]
        t.answer_options = opts if isinstance(opts, list) and opts else None
        t.confidence = r["confidence"] if isinstance(r["confidence"], dict) else {}
        tasks.append(t)
        ids.append(r["staging_id"])
    return tasks, ids


def read_answer_pages(
    pdf_path: str, start: int, end: int, *, verbose: bool = False
) -> tuple[list[dict], int, int]:
    """Текст страниц раздела «Ответы»: сначала текстовый слой, потом OCR.

    Раздел ответов — плотный печатный список без формул и картинок. Там, где у
    PDF есть текстовый слой (а у сканов с распознаванием он есть), он даёт
    точный текст **бесплатно и мгновенно**. Гонять такие страницы через Vision
    значит платить за то, что уже лежит в файле, и добавлять шанс на ошибку
    распознавания там, где её могло не быть.

    OCR остаётся фолбэком для книг без слоя — тот же принцип, что в
    `ocr._text_layer_fallback`, только приоритет обратный: здесь текст
    заведомо надёжнее модели.
    """
    import pymupdf

    doc = pymupdf.open(pdf_path)
    ocr: GeminiVisionOCR | None = None
    answers: list[dict] = []
    n_layer = n_ocr = 0

    for pg in range(start, end + 1):
        page_text = ""
        try:
            page_text = doc[pg - 1].get_text() or ""
        except Exception:  # noqa: BLE001
            page_text = ""

        source = "текстовый слой"
        if not is_usable_ocr_text(page_text):
            if ocr is None:
                ocr = GeminiVisionOCR()
            page_text = ocr.process_pages(pdf_path, pg, pg)
            source = "OCR"
            n_ocr += 1
        else:
            n_layer += 1

        found = AK.parse_answer_section(page_text, source_page=pg)
        answers.extend(found)
        if verbose:
            print(f"  стр. {pg}: ответов {len(found):>3}  ({source})")

    doc.close()
    return answers, n_layer, n_ocr


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--textbook-id", required=True)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--pages", help="диапазон вручную, напр. 92-102")
    ap.add_argument("--dry-run", action="store_true", help="ничего не писать")
    args = ap.parse_args()

    if args.pages:
        a, _, b = args.pages.partition("-")
        rng = (int(a), int(b or a))
    else:
        rng = answer_pages_from_toc(args.textbook_id)
    if not rng:
        print("раздел «Ответы» не найден в оглавлении; задайте --pages", file=sys.stderr)
        return 1
    start, end = rng
    print(f"раздел «Ответы»: стр. {start}–{end}")

    answers, n_layer, n_ocr = read_answer_pages(args.pdf, start, end, verbose=True)
    print(f"извлечено ответов: {len(answers)} "
          f"(страниц из текстового слоя: {n_layer}, через OCR: {n_ocr})")

    tasks, ids = load_staged(args.textbook_id)
    if not tasks:
        print("в tasks_staging нет задач по этому учебнику", file=sys.stderr)
        return 1

    # То же, что делает `orchestrator._mark_extraction_provenance` (И1):
    # ответ, произведённый извлечением, не должен лежать с источником
    # `absent` — «ответа нет» при наличии ответа. Здесь это применяется
    # ретроактивно, к уже записанному staging.
    marked = 0
    for t in tasks:
        if t.answer_source == prov.ABSENT and not AK.is_empty_answer(t.answer_raw):
            t.answer_source = prov.AI_SOLVED
            marked += 1
    if marked:
        print(f"провенанс: {marked} ответов помечены ai_solved (источник — извлечение)")

    report = AK.join_answers(tasks, answers)
    print(f"\nJOIN: ключ={report.strategy} пришито={report.matched}/{report.n_tasks} "
          f"coverage={report.coverage} неоднозначных={report.ambiguous} "
          f"без пары={len(report.unmatched_answers)}")

    verdicts = G.evaluate_batch(tasks)
    G.apply_verdicts(tasks, verdicts)
    summary = SC.score_tasks(tasks, verdicts)
    print(f"вердикты: pass={sum(1 for v in verdicts if v.status == G.PASS)} "
          f"review={sum(1 for v in verdicts if v.status == G.REVIEW)} "
          f"reject={sum(1 for v in verdicts if v.status == G.REJECT)}")
    print(f"на ручную проверку (брак): {summary['n_needs_review']}, "
          f"ждут ответа: {summary['n_awaiting_answer']}")

    if args.dry_run:
        print("\n--dry-run: в БД ничего не записано")
        return 0

    with _engine().begin() as conn:
        for sid, t, v in zip(ids, tasks, verdicts):
            conn.execute(text(_UPDATE_SQL), {
                "staging_id": sid,
                "correct_answer": t.answer_raw or None,
                "answer_source": t.answer_source,
                "answer_source_page": t.answer_source_page,
                "confidence": json.dumps(t.confidence or {}, ensure_ascii=False),
                "gate_status": v.status,
                "gate_reasons": json.dumps(v.reasons, ensure_ascii=False),
            })
    print(f"\nобновлено строк staging: {len(ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
