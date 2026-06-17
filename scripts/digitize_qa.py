#!/usr/bin/env python3
"""
Post-digitization QA pipeline.

Runs a sequence of idempotent checks and fixes on a digitized textbook:

  Step 1  [audit]       — Full health report (read-only)
  Step 2  [dedup]       — Delete question_text duplicates (keep correct paragraph)
  Step 3  [gap_fill]    — Re-extract paragraphs with 0 tasks from OCR/PDF
  Step 4  [reclassify]  — Map tasks without skill_id via ADC (Gemini Pro)
  Step 5  [enrich]      — Fill missing solution_steps, hints, distractors
  Step 6  [abc_fill]    — Generate AI tasks for missing A/B/C difficulty levels

All steps are idempotent — safe to re-run. Each can be skipped via --skip-*.

Usage inside container:
  python /app/scripts/digitize_qa.py --textbook-id <uuid> --class-level 6
  python /app/scripts/digitize_qa.py --textbook-id <uuid> --class-level 6 --audit-only
  python /app/scripts/digitize_qa.py --textbook-id <uuid> --class-level 6 --skip-gap-fill --skip-abc-fill
  python /app/scripts/digitize_qa.py --textbook-id <uuid> --class-level 6 --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.core.config import get_settings
from src.pipeline.exercise_ranges import exercise_range, parse_exercise_num, has_ranges

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

SEP = "─" * 60


# ─────────────────────────────────────────────────────────────
# AUDIT
# ─────────────────────────────────────────────────────────────

def audit(engine: Engine, textbook_id: str, class_level: int) -> dict:
    """Return a health snapshot of a digitized textbook."""
    with engine.connect() as c:
        meta = c.execute(text("""
            SELECT title FROM textbooks WHERE textbook_id = :tid
        """), {"tid": textbook_id}).fetchone()

        total = c.execute(text("""
            SELECT COUNT(*) FROM tasks_master tm
            JOIN textbook_toc t ON t.id = tm.toc_id
            WHERE t.textbook_id = :tid
        """), {"tid": textbook_id}).scalar() or 0

        no_skill = c.execute(text("""
            SELECT COUNT(*) FROM tasks_master tm
            JOIN textbook_toc t ON t.id = tm.toc_id
            WHERE t.textbook_id = :tid AND tm.skill_id IS NULL
        """), {"tid": textbook_id}).scalar() or 0

        no_steps = c.execute(text("""
            SELECT COUNT(*) FROM tasks_master tm
            JOIN textbook_toc t ON t.id = tm.toc_id
            WHERE t.textbook_id = :tid
              AND (solution_steps IS NULL OR solution_steps::text IN ('null','[]'))
        """), {"tid": textbook_id}).scalar() or 0

        no_hints = c.execute(text("""
            SELECT COUNT(*) FROM tasks_master tm
            JOIN textbook_toc t ON t.id = tm.toc_id
            WHERE t.textbook_id = :tid
              AND (hints IS NULL OR hints::text IN ('null','[]'))
        """), {"tid": textbook_id}).scalar() or 0

        no_distr = c.execute(text("""
            SELECT COUNT(*) FROM tasks_master tm
            JOIN textbook_toc t ON t.id = tm.toc_id
            WHERE t.textbook_id = :tid
              AND (distractor_meta IS NULL OR distractor_meta::text IN ('null','[]'))
        """), {"tid": textbook_id}).scalar() or 0

        no_answer = c.execute(text("""
            SELECT COUNT(*) FROM tasks_master tm
            JOIN textbook_toc t ON t.id = tm.toc_id
            WHERE t.textbook_id = :tid
              AND (correct_answer IS NULL OR correct_answer = '')
        """), {"tid": textbook_id}).scalar() or 0

        dups = c.execute(text("""
            SELECT COUNT(*) FROM (
                SELECT question_text FROM tasks_master tm
                JOIN textbook_toc t ON t.id = tm.toc_id
                WHERE t.textbook_id = :tid
                GROUP BY question_text HAVING COUNT(*) > 1
            ) x
        """), {"tid": textbook_id}).scalar() or 0

        empty_paras = c.execute(text("""
            SELECT COUNT(*) FROM textbook_toc t
            WHERE t.textbook_id = :tid AND t.level = 2
              AND NOT EXISTS (
                  SELECT 1 FROM tasks_master tm WHERE tm.toc_id = t.id
              )
        """), {"tid": textbook_id}).scalar() or 0

        out_of_range = 0
        if has_ranges(textbook_id):
            for _id, para, ex_raw in c.execute(text("""
                SELECT tm.id, tt.paragraph_number, tt.exercise_number
                FROM tasks_master tm
                JOIN textbook_toc t ON t.id = tm.toc_id
                JOIN textbook_tasks tt ON tt.task_id = tm.id
                WHERE t.textbook_id = :tid
            """), {"tid": textbook_id}).fetchall():
                lo_hi = exercise_range(textbook_id, para)
                if not lo_hi:
                    continue
                n = parse_exercise_num(str(ex_raw or ""))
                if n is not None and (n < lo_hi[0] or n > lo_hi[1]):
                    out_of_range += 1

        para_counts = c.execute(text("""
            SELECT t.number, t.title, COUNT(tm.id) AS n
            FROM textbook_toc t
            LEFT JOIN tasks_master tm ON tm.toc_id = t.id
            WHERE t.textbook_id = :tid AND t.level = 2
            GROUP BY t.id, t.number, t.title, t.sort_order
            ORDER BY t.sort_order
        """), {"tid": textbook_id}).fetchall()

        # A/B/C coverage for this class
        gp = f"G{class_level}_"
        abc = c.execute(text("""
            WITH sd AS (
                SELECT skill_id,
                       bool_or(difficulty='A') has_a,
                       bool_or(difficulty='B') has_b,
                       bool_or(difficulty='C') has_c
                FROM tasks_master
                WHERE skill_id LIKE :gp
                GROUP BY skill_id
            )
            SELECT
              COUNT(*) FILTER (WHERE has_a AND has_b AND has_c) full_abc,
              COUNT(*) FILTER (WHERE NOT (has_a AND has_b AND has_c)) partial_abc,
              COUNT(*) total_with_tasks
            FROM sd
        """), {"gp": f"{gp}%"}).fetchone()

    title = (meta[0] if meta else None) or textbook_id

    return {
        "title": title,
        "total": total,
        "no_skill": no_skill,
        "no_steps": no_steps,
        "no_hints": no_hints,
        "no_distr": no_distr,
        "no_answer": no_answer,
        "dups": dups,
        "out_of_range": out_of_range,
        "empty_paras": empty_paras,
        "para_counts": para_counts,
        "abc_full": abc[0] if abc else 0,
        "abc_partial": abc[1] if abc else 0,
        "abc_total": abc[2] if abc else 0,
    }


def print_audit(snap: dict, label: str = "AUDIT") -> None:
    log.info(SEP)
    log.info("=== %s: %s ===", label, snap["title"])
    log.info(SEP)
    ok = lambda v: "✅" if v == 0 else "⚠️ "
    total = snap["total"]
    pct = lambda n: f"{n}/{total} ({100*n//total if total else 0}%)"
    log.info("  Tasks total:        %d", total)
    log.info("  %s Duplicates:      %s", ok(snap["dups"]), snap["dups"])
    if snap.get("out_of_range") is not None:
        log.info("  %s Out-of-range ex: %s", ok(snap["out_of_range"]), snap["out_of_range"])
    log.info("  %s Empty paragraphs:%s", ok(snap["empty_paras"]), snap["empty_paras"])
    log.info("  %s No skill_id:     %s", ok(snap["no_skill"]), pct(snap["no_skill"]))
    log.info("  %s No answer:       %s", ok(snap["no_answer"]), pct(snap["no_answer"]))
    log.info("  %s No steps:        %s", ok(snap["no_steps"]), pct(snap["no_steps"]))
    log.info("  %s No hints:        %s", ok(snap["no_hints"]), pct(snap["no_hints"]))
    log.info("  %s No distractors:  %s", ok(snap["no_distr"]), pct(snap["no_distr"]))
    log.info("  A/B/C full cover:   %d / %d skills", snap["abc_full"], snap["abc_total"])
    if snap["abc_partial"]:
        log.info("  ⚠️  Partial A/B/C:  %d skills", snap["abc_partial"])
    log.info("")
    log.info("  Paragraphs:")
    for number, title, n in snap["para_counts"]:
        flag = "  <── 0" if n == 0 else ("  <── few" if n < 5 else "")
        log.info("    §%-18s %3d  %s%s", number, n, (title or "")[:35], flag)
    log.info(SEP)


# ─────────────────────────────────────────────────────────────
# STEP 2 — Deduplicate
# ─────────────────────────────────────────────────────────────

def step_dedup(engine: Engine, textbook_id: str, *, dry_run: bool = False) -> int:
    """
    Delete duplicate tasks (identical question_text) keeping the one in the
    paragraph with the highest sort_order (latest = most correct toc binding).
    """
    log.info(SEP)
    log.info("STEP 2 — Deduplication")
    with engine.connect() as c:
        dups = c.execute(text("""
            SELECT
                tm.question_text,
                array_agg(tm.id ORDER BY t.sort_order DESC) AS ids,
                array_agg(t.number ORDER BY t.sort_order DESC) AS paras
            FROM tasks_master tm
            JOIN textbook_toc t ON t.id = tm.toc_id
            WHERE t.textbook_id = :tid
            GROUP BY tm.question_text
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC
        """), {"tid": textbook_id}).fetchall()

    if not dups:
        log.info("  No duplicates — skipping")
        return 0

    to_delete: list[str] = []
    for row in dups:
        ids = row[1]
        paras = row[2]
        keep, *rest = ids
        log.info("  keep §%s id=%s — delete %s (§%s)", paras[0], keep, rest, paras[1:])
        to_delete.extend(rest)

    log.info("  Total to delete: %d", len(to_delete))
    if dry_run:
        log.info("  [DRY RUN] skipped")
        return 0

    with engine.begin() as c:
        c.execute(text("DELETE FROM task_figure_refs WHERE task_id = ANY(:ids)"), {"ids": to_delete})
        c.execute(text("DELETE FROM textbook_tasks WHERE task_id = ANY(:ids)"), {"ids": to_delete})
        n = c.execute(text("DELETE FROM tasks_master WHERE id = ANY(:ids) RETURNING id"), {"ids": to_delete}).rowcount

    log.info("  Deleted %d duplicates", n)
    return n


# ─────────────────────────────────────────────────────────────
# STEP 2b — Remove out-of-range exercise contamination
# ─────────────────────────────────────────────────────────────

def step_validate_ranges(
    engine: Engine,
    textbook_id: str,
    *,
    dry_run: bool = False,
) -> int:
    """Delete tasks whose exercise_number falls outside the paragraph's range table."""
    log.info(SEP)
    log.info("STEP 2b — Exercise range validation")

    if not has_ranges(textbook_id):
        log.info("  No exercise range table — skipping")
        return 0

    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT tm.id, tt.paragraph_number, tt.exercise_number, tm.question_text
            FROM tasks_master tm
            JOIN textbook_toc t ON t.id = tm.toc_id
            JOIN textbook_tasks tt ON tt.task_id = tm.id
            WHERE t.textbook_id = :tid
            ORDER BY tt.paragraph_number, tt.exercise_number
        """), {"tid": textbook_id}).fetchall()

    to_delete: list[str] = []
    for task_id, para, ex_raw, q in rows:
        lo_hi = exercise_range(textbook_id, para)
        if not lo_hi:
            continue
        n = parse_exercise_num(str(ex_raw or ""))
        if n is None:
            continue
        lo, hi = lo_hi
        if n < lo or n > hi:
            # Find correct paragraph if possible
            correct_para = None
            from src.pipeline.exercise_ranges import get_ranges
            for pkey, (plo, phi) in get_ranges(textbook_id).items():
                if plo <= n <= phi:
                    correct_para = pkey
                    break
            log.info(
                "  OUT OF RANGE: %s ex=%s in §%s (expected %d–%d)%s | %s",
                task_id, ex_raw, para, lo, hi,
                f" → belongs to §{correct_para}" if correct_para else "",
                (q or "")[:50],
            )
            to_delete.append(task_id)

    if not to_delete:
        log.info("  All tasks within exercise ranges — OK")
        return 0

    log.info("  Total out-of-range: %d", len(to_delete))
    if dry_run:
        log.info("  [DRY RUN] skipped deletion")
        return 0

    with engine.begin() as c:
        c.execute(text("DELETE FROM task_figure_refs WHERE task_id = ANY(:ids)"), {"ids": to_delete})
        c.execute(text("DELETE FROM textbook_tasks WHERE task_id = ANY(:ids)"), {"ids": to_delete})
        n = c.execute(
            text("DELETE FROM tasks_master WHERE id = ANY(:ids) RETURNING id"),
            {"ids": to_delete},
        ).rowcount

    log.info("  Deleted %d out-of-range tasks", n)
    return n


# ─────────────────────────────────────────────────────────────
# STEP 3 — Gap-fill (re-extract empty paragraphs)
# ─────────────────────────────────────────────────────────────

def step_gap_fill(
    engine: Engine,
    textbook_id: str,
    class_level: int,
    pdf_path: str,
    *,
    threshold: int = 0,
    dry_run: bool = False,
) -> int:
    """Re-extract paragraphs with <= threshold tasks from OCR/PDF."""
    log.info(SEP)
    log.info("STEP 3 — Gap-fill (threshold ≤ %d tasks)", threshold)

    with engine.connect() as c:
        all_paras = c.execute(text("""
            SELECT t.id, t.number, t.title, t.page_start, t.sort_order
            FROM textbook_toc t
            WHERE t.textbook_id = :tid AND t.level = 2
            ORDER BY t.sort_order
        """), {"tid": textbook_id}).fetchall()

        counts = {
            str(r[0]): r[1]
            for r in c.execute(text("""
                SELECT tm.toc_id::text, COUNT(*) FROM tasks_master tm
                JOIN textbook_toc t ON t.id = tm.toc_id
                WHERE t.textbook_id = :tid
                GROUP BY tm.toc_id::text
            """), {"tid": textbook_id}).fetchall()
        }

    # Build page_end for each paragraph
    all_starts = [(r[0], r[3]) for r in all_paras]
    targets = []
    for i, para in enumerate(all_paras):
        toc_id, number, title, page_start, sort_order = para
        cnt = counts.get(str(toc_id), 0)
        if cnt > threshold or page_start is None:
            continue
        # page_end = next paragraph's start - 1
        page_end = page_start
        for j in range(i + 1, len(all_paras)):
            ns = all_paras[j][3]
            if ns is not None and ns > page_start:
                page_end = ns - 1
                break
        else:
            page_end = page_start + 5  # fallback

        targets.append({
            "id": str(toc_id),
            "number": number,
            "title": title,
            "page_start": page_start,
            "page_end": page_end,
        })

    if not targets:
        log.info("  No paragraphs need gap-filling — skipping")
        return 0

    log.info("  %d paragraphs to re-extract:", len(targets))
    for t in targets:
        log.info("    §%s  p%s–%s  «%s»", t["number"], t["page_start"], t["page_end"], (t["title"] or "")[:40])

    if dry_run:
        log.info("  [DRY RUN] skipped")
        return 0

    import uuid
    from src.pipeline.orchestrator import DigitizationOrchestrator as Orchestrator
    from src.pipeline.ocr import GeminiVisionOCR
    from src.pipeline.extraction import LegendExtractor, TaskExtractor
    from src.pipeline.figures import FigureExtractor
    from src.pipeline.classification import SkeletonTextbookMapper

    ocr = GeminiVisionOCR()
    legend = {}
    try:
        head = ocr.process_pages(pdf_path, 1, 10, figures_by_page={})
        legend = LegendExtractor().extract_legend(head)
        log.info("  Legend: %d markers", len(legend))
    except Exception as exc:
        log.warning("  Legend extraction failed: %s", exc)

    settings = get_settings()
    extractor = TaskExtractor(legend=legend)
    mapper = SkeletonTextbookMapper()
    mapper.load_skills_from_db(settings.database_url, class_level=class_level)
    fig_extractor = FigureExtractor(textbook_id)
    job_id = f"qa_gapfill_{uuid.uuid4().hex[:6]}"
    orch = Orchestrator(job_id=job_id, textbook_id=textbook_id, class_level=class_level)

    total_added = 0
    for entry in targets:
        log.info("  Processing §%s …", entry["number"])
        try:
            n = orch._process_paragraph_pages(
                entry=entry,
                pdf_path=pdf_path,
                fig_extractor=fig_extractor,
                ocr_worker=ocr,
                extractor=extractor,
                mapper=mapper,
                theme_stream=True,
            )
            log.info("  §%s: +%d tasks", entry["number"], n)
            total_added += n
        except Exception as exc:
            log.error("  §%s FAILED: %s", entry["number"], exc)

    log.info("  Gap-fill complete: +%d tasks total", total_added)
    return total_added


# ─────────────────────────────────────────────────────────────
# STEP 4 — Skill classification (ADC)
# ─────────────────────────────────────────────────────────────

def step_reclassify(
    engine: Engine,
    textbook_id: str,
    class_level: int,
    *,
    dry_run: bool = False,
    sleep_s: float = 0.5,
    max_retries: int = 2,
) -> int:
    """Map tasks without skill_id using two-step Gemini Pro ADC."""
    log.info(SEP)
    log.info("STEP 4 — Skill classification (ADC)")

    from src.pipeline.classification import SkeletonTextbookMapper
    from src.pipeline.models import ExtractedTask

    settings = get_settings()
    mapper = SkeletonTextbookMapper()
    mapper.load_skills_from_db(settings.database_url, class_level=class_level)

    with engine.connect() as c:
        para_titles = {
            str(r[0]): r[1] or ""
            for r in c.execute(text("""
                SELECT number, title FROM textbook_toc
                WHERE textbook_id = :tid AND level = 2
            """), {"tid": textbook_id}).fetchall()
        }
        rows = c.execute(text("""
            SELECT tm.id, t.number, t.title, tm.toc_id,
                   tm.question_text, tm.question_latex,
                   tm.correct_answer, tm.answer_type, tm.difficulty, tm.tags
            FROM tasks_master tm
            JOIN textbook_toc t ON t.id = tm.toc_id
            JOIN textbook_tasks tt ON tt.task_id = tm.id
            WHERE t.textbook_id = :tid AND tm.skill_id IS NULL
            ORDER BY t.sort_order, tm.id
        """), {"tid": textbook_id}).fetchall()

    if not rows:
        log.info("  All tasks have skill_id — skipping")
        return 0

    log.info("  %d tasks without skill_id", len(rows))
    if dry_run:
        log.info("  [DRY RUN] skipped")
        return 0

    updated = 0
    failed = 0

    for attempt in range(1, max_retries + 1):
        if not rows:
            break
        log.info("  Attempt %d/%d: %d tasks", attempt, max_retries, len(rows))
        still_failed = []

        for i, row in enumerate(rows, 1):
            task_id, toc_num, toc_title, toc_id, question, latex, answer, atype, difficulty, tags_raw = row
            tags = tags_raw if isinstance(tags_raw, dict) else {}
            para_title = para_titles.get(str(toc_num), toc_title or "")

            et = ExtractedTask(
                temp_id=task_id,
                exercise_number=str(tags.get("exercise", "")),
                paragraph_number=str(toc_num or ""),
                paragraph_title=para_title,
                question_text=question or "",
                question_latex=latex or "",
                answer_raw=answer or "",
                answer_type=atype or "exact_number",
                difficulty=difficulty or "B",
                toc_id=toc_id,
                tags=dict(tags),
            )

            try:
                mapped = mapper.map_task(et)
            except Exception as exc:
                log.warning("  ADC error %s: %s", task_id, exc)
                still_failed.append(row)
                time.sleep(sleep_s)
                continue

            if not mapped.skill_id:
                still_failed.append(row)
                time.sleep(sleep_s)
                continue

            merged_tags = {**tags,
                "mapping_l3": mapped.tags.get("mapping_l3"),
                "mapping_confidence": mapped.tags.get("mapping_confidence"),
                "mapping_reasoning": mapped.tags.get("mapping_reasoning"),
            }
            with engine.begin() as c:
                c.execute(text("""
                    UPDATE tasks_master
                    SET skill_id = :skill_id, tags = CAST(:tags AS jsonb), updated_at = NOW()
                    WHERE id = :id
                """), {
                    "id": task_id,
                    "skill_id": mapped.skill_id,
                    "tags": json.dumps(merged_tags, ensure_ascii=False),
                })
            updated += 1

            if i % 20 == 0:
                log.info("  Progress: %d/%d mapped=%d failed=%d", i, len(rows), updated, failed + len(still_failed))
            time.sleep(sleep_s)

        rows = still_failed  # retry only those that failed

    failed = len(rows)
    log.info("  ADC done: mapped=%d  still_no_skill=%d", updated, failed)
    if rows:
        log.info("  Remaining without skill:")
        for r in rows:
            log.info("    %s §%s", r[0], r[1])
    return updated


# ─────────────────────────────────────────────────────────────
# STEP 5 — Enrich (steps, hints, distractors)
# ─────────────────────────────────────────────────────────────

def step_enrich(engine: Engine, textbook_id: str, *, dry_run: bool = False) -> dict:
    """Fill missing solution_steps, hints and distractor_meta for textbook tasks."""
    log.info(SEP)
    log.info("STEP 5 — Enrich (steps / hints / distractors)")

    from src.pipeline.distractors import generate_distractors, _ai_text
    from src.pipeline.gemini_client import call_gemini, get_pro_model, parse_json_response
    from src.pipeline.models import ExtractedTask

    with engine.connect() as c:
        no_steps = c.execute(text("""
            SELECT tm.id, tm.question_text, tm.correct_answer,
                   tm.hints, tm.solution_steps
            FROM tasks_master tm
            JOIN textbook_toc t ON t.id = tm.toc_id
            WHERE t.textbook_id = :tid
              AND (solution_steps IS NULL OR solution_steps::text IN ('null','[]'))
            ORDER BY tm.id
        """), {"tid": textbook_id}).fetchall()

        no_distr = c.execute(text("""
            SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type
            FROM tasks_master tm
            JOIN textbook_toc t ON t.id = tm.toc_id
            WHERE t.textbook_id = :tid
              AND (distractor_meta IS NULL OR distractor_meta::text IN ('null','[]'))
            ORDER BY tm.id
        """), {"tid": textbook_id}).fetchall()

    log.info("  Need steps/hints: %d | Need distractors: %d", len(no_steps), len(no_distr))
    if not no_steps and not no_distr:
        log.info("  All enrichment complete — skipping")
        return {"steps": 0, "distractors": 0}

    if dry_run:
        log.info("  [DRY RUN] skipped")
        return {"steps": 0, "distractors": 0}

    steps_done = 0
    for task_id, question, answer, hints_raw, steps_raw in no_steps:
        if not question or not answer:
            continue
        need_hints = not hints_raw or str(hints_raw) in ("null", "[]")
        prompt = (
            "Ты — методист по математике. Для задачи:\n"
            f"Вопрос: {question}\n"
            f"Ответ: {answer}\n\n"
            "Сгенерируй:\n"
            "1. solution_steps: 3–5 шагов решения\n"
            "2. hints: 2 подсказки для ученика\n"
            'Верни JSON: {"solution_steps":["..."],"hints":["..."]}'
        )
        try:
            raw = call_gemini(prompt, model=get_pro_model(), temperature=0.1, max_tokens=1024)
            data = parse_json_response(raw)
            if not isinstance(data, dict):
                continue
            steps = data.get("solution_steps") or []
            hints = data.get("hints") or []
            if not steps:
                continue
            params: dict = {
                "id": task_id,
                "steps": json.dumps(steps, ensure_ascii=False),
            }
            sql_hints = ""
            if need_hints and hints:
                params["hints"] = json.dumps(hints, ensure_ascii=False)
                sql_hints = ", hints = CAST(:hints AS jsonb)"
            with engine.begin() as c:
                c.execute(text(f"""
                    UPDATE tasks_master
                    SET solution_steps = CAST(:steps AS jsonb){sql_hints}, updated_at = NOW()
                    WHERE id = :id
                """), params)
            steps_done += 1
        except Exception as exc:
            log.warning("  Steps enrich failed %s: %s", task_id, exc)
        time.sleep(0.3)

    distr_done = 0
    for task_id, question, answer, atype in no_distr:
        if not question or not answer or str(answer).strip() in ("—", "-", ""):
            continue
        et = ExtractedTask(temp_id=task_id, question_text=question,
                           answer_raw=answer, answer_type=atype or "exact_number")
        try:
            float(answer.replace(",", ".").replace(" ", "").split()[0])
            generate_distractors(et)
        except (ValueError, IndexError):
            _ai_text(et)

        if not et.distractor_meta:
            continue
        with engine.begin() as c:
            c.execute(text("""
                UPDATE tasks_master
                SET distractor_meta = CAST(:dmeta AS jsonb), updated_at = NOW()
                WHERE id = :id
            """), {"id": task_id, "dmeta": json.dumps(et.distractor_meta, ensure_ascii=False)})
        distr_done += 1
        time.sleep(0.2)

    log.info("  Enriched: steps=%d  distractors=%d", steps_done, distr_done)
    return {"steps": steps_done, "distractors": distr_done}


# ─────────────────────────────────────────────────────────────
# STEP 6 — Fill missing A/B/C
# ─────────────────────────────────────────────────────────────

def step_abc_fill(engine: Engine, class_level: int, *, dry_run: bool = False) -> int:
    """Generate AI tasks for skills missing any A/B/C difficulty level."""
    log.info(SEP)
    log.info("STEP 6 — A/B/C gap fill (AI tasks)")

    from src.pipeline.post_processing import generate_missing_difficulties

    if dry_run:
        gp = f"G{class_level}_"
        with engine.connect() as c:
            rows = c.execute(text("""
                SELECT kh.id, kh.name_ru,
                       COUNT(CASE WHEN tm.difficulty='A' THEN 1 END) AS ca,
                       COUNT(CASE WHEN tm.difficulty='B' THEN 1 END) AS cb,
                       COUNT(CASE WHEN tm.difficulty='C' THEN 1 END) AS cc
                FROM knowledge_hierarchy kh
                LEFT JOIN tasks_master tm ON tm.skill_id = kh.id
                WHERE kh.level='L4' AND kh.id LIKE :gp
                GROUP BY kh.id, kh.name_ru
                HAVING COUNT(CASE WHEN tm.difficulty='A' THEN 1 END)=0
                    OR COUNT(CASE WHEN tm.difficulty='B' THEN 1 END)=0
                    OR COUNT(CASE WHEN tm.difficulty='C' THEN 1 END)=0
                ORDER BY kh.id
            """), {"gp": f"{gp}%"}).fetchall()
        log.info("  [DRY RUN] %d skills need A/B/C fill:", len(rows))
        for sid, name, ca, cb, cc in rows:
            missing = [d for d, n in [("A", ca), ("B", cb), ("C", cc)] if n == 0]
            log.info("    %s «%s» — missing: %s", sid, name[:40], missing)
        return 0

    n = generate_missing_difficulties(engine, class_level)
    log.info("  A/B/C fill: +%d AI tasks", n)
    return n


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Post-digitization QA pipeline")
    parser.add_argument("--textbook-id", required=True, help="UUID of the textbook")
    parser.add_argument("--class-level", type=int, required=True, help="Grade level (e.g. 6)")
    parser.add_argument("--pdf-path", default="", help="Path to PDF (needed for gap-fill)")

    parser.add_argument("--audit-only",    action="store_true", help="Print report only, no changes")
    parser.add_argument("--dry-run",       action="store_true", help="All steps: plan only, no DB writes")

    parser.add_argument("--skip-dedup",      action="store_true")
    parser.add_argument("--skip-validate",   action="store_true",
                        help="Skip exercise range validation")
    parser.add_argument("--skip-gap-fill",   action="store_true")
    parser.add_argument("--skip-reclassify", action="store_true")
    parser.add_argument("--skip-enrich",     action="store_true")
    parser.add_argument("--skip-abc-fill",   action="store_true")

    parser.add_argument("--gap-fill-threshold", type=int, default=0,
                        help="Re-extract paragraphs with <= N tasks (default: 0 = only empty)")
    parser.add_argument("--adc-sleep",   type=float, default=0.5)
    parser.add_argument("--adc-retries", type=int,   default=2)

    args = parser.parse_args()

    dry = args.dry_run or args.audit_only
    settings = get_settings()
    engine = create_engine(settings.database_url)
    tid = args.textbook_id
    cl = args.class_level

    # ── BEFORE ────────────────────────────────────────────────
    before = audit(engine, tid, cl)
    print_audit(before, "BEFORE")

    if args.audit_only:
        log.info("--audit-only: exiting without changes")
        return 0

    results: dict = {}

    # ── Step 2: dedup ─────────────────────────────────────────
    if not args.skip_dedup:
        results["dedup"] = step_dedup(engine, tid, dry_run=dry)

    if not args.skip_validate:
        results["validate_ranges"] = step_validate_ranges(engine, tid, dry_run=dry)

    # ── Step 3: gap-fill ──────────────────────────────────────
    if not args.skip_gap_fill:
        pdf = args.pdf_path
        if not pdf:
            log.warning("--pdf-path not provided — skipping gap-fill")
            results["gap_fill"] = 0
        else:
            results["gap_fill"] = step_gap_fill(
                engine, tid, cl, pdf,
                threshold=args.gap_fill_threshold,
                dry_run=dry,
            )

    # ── Step 4: reclassify ────────────────────────────────────
    if not args.skip_reclassify:
        results["reclassify"] = step_reclassify(
            engine, tid, cl,
            dry_run=dry,
            sleep_s=args.adc_sleep,
            max_retries=args.adc_retries,
        )

    # ── Step 5: enrich ────────────────────────────────────────
    if not args.skip_enrich:
        results["enrich"] = step_enrich(engine, tid, dry_run=dry)

    # ── Step 6: A/B/C fill ────────────────────────────────────
    if not args.skip_abc_fill:
        results["abc_fill"] = step_abc_fill(engine, cl, dry_run=dry)

    # ── AFTER ─────────────────────────────────────────────────
    after = audit(engine, tid, cl)
    print_audit(after, "AFTER")

    log.info(SEP)
    log.info("=== SUMMARY ===")
    log.info("  Dedup removed:        %s", results.get("dedup", "—"))
    log.info("  Out-of-range removed: %s", results.get("validate_ranges", "—"))
    log.info("  Gap-fill added:       %s", results.get("gap_fill", "—"))
    log.info("  Skills mapped:        %s", results.get("reclassify", "—"))
    log.info("  Steps enriched:       %s", results.get("enrich", {}).get("steps", "—") if isinstance(results.get("enrich"), dict) else "—")
    log.info("  Distractors enriched: %s", results.get("enrich", {}).get("distractors", "—") if isinstance(results.get("enrich"), dict) else "—")
    log.info("  A/B/C AI tasks added: %s", results.get("abc_fill", "—"))
    delta = after["total"] - before["total"]
    log.info("  Tasks: %d → %d (%+d)", before["total"], after["total"], delta)
    log.info(SEP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
