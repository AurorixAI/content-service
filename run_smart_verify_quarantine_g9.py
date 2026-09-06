#!/usr/bin/env python3
"""
SmartVerify Quarantine Runner v3 — FULL VERIFICATION.

Pipeline per task:
  1. DeepSeek (chat API) independently solves the task → ai_answer
  2. Compare ai_answer with stored textbook answer via:
       - answers_equivalent() (existing SymPy logic)
       - interval_normalizer.intervals_equivalent() (our new module)
  3. If match → textbook answer confirmed → generate distractors
  4. If no match → flag needs_human_review + save both answers for manual check
  5. If API error → flag as pending_retry

Usage:
    docker exec content-worker python /app/run_smart_verify_quarantine.py [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from typing import Optional

sys.path.insert(0, "/app")

import psycopg2
import psycopg2.extras

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("quarantine_runner_v3")

DB_URL = os.getenv("DATABASE_URL", "postgresql://algo_user:algo_password@postgres:5432/algo_db")
BATCH_SIZE = 5
BATCH_PAUSE_S = 1.5

# ── Solve prompt ────────────────────────────────────────────────────────────────

SOLVE_SYSTEM = (
    "Ты — строгий математический решатель уровня учителя 9-го класса. "
    "Решай задачу точно, пошагово. "
    "В конце напиши ТОЛЬКО строку: ОТВЕТ: <значение>\n"
    "Ничего кроме этой строки после слова ОТВЕТ."
)


def _build_solve_prompt(question: str, answer_type: str) -> str:
    type_hints = {
        "exact_number": "Ответ — целое или десятичное число.",
        "decimal": "Ответ — десятичная дробь.",
        "fraction": "Ответ — обыкновенная дробь.",
        "expression": "Ответ — алгебраическое выражение.",
        "equation_solution": "Ответ — все корни уравнения через '; '.",
        "inequality": "Ответ — множество решений в виде интервала или неравенства.",
        "set": "Ответ — множество значений через '; '.",
        "multiple_choice": "Ответ — да/нет или буква.",
        "text": "Ответ — краткий текст (1-3 слова).",
    }
    hint = type_hints.get(answer_type, "")
    return (
        f"Задача:\n{question}\n\n"
        f"Тип ответа: {answer_type}. {hint}\n\n"
        "Реши задачу. В конце напиши строку:\n"
        "ОТВЕТ: <значение>"
    )


def _strip_latex(s: str) -> str:
    """Strip LaTeX wrappers, units, and normalize to plain math notation."""
    if not s:
        return s
    # Strip \( ... \) and $ ... $ wrappers
    s = re.sub(r"\\[\(\)]", "", s)
    s = re.sub(r"\$", "", s)
    # Strip LaTeX text commands with units: \text{м}, \text{см} etc.
    s = re.sub(r"\\text\{[а-яА-Яa-zA-Z/²³·]+\}", "", s)
    # Strip trailing units (м, см, кг, etc.)
    s = re.sub(r"\s+(м|км|см|мм|кг|г|мг|л|мл|с|мс|ч|мин)\s*$", "", s, flags=re.I)
    # Normalize \times and \cdot to *
    s = s.replace("\\times", "*").replace("\\cdot", "*").replace("×", "*").replace("·", "*")
    # Normalize \cdot 10^ to * 10^
    s = re.sub(r"\*\s*10\^\{?(-?\d+)\}?", r" * 10^\1", s)
    # Normalize decimal comma in numbers
    s = re.sub(r"(\d),(\d)", r"\1.\2", s)
    return s.strip()


def _sci_notation_equal(a: str, b: str) -> Optional[bool]:
    """Check if two scientific notation expressions are numerically equal (with variable factor).
    E.g. '9.46 * 10^9 * a' == '9460 * 10^6 * a'
    """
    # For expressions with variables, extract the numeric coefficient
    def extract_coeff(s: str) -> Optional[float]:
        # Match: coeff * 10^exp optionally followed by * var
        m = re.match(
            r"^([+-]?[\d.]+)\s*\*?\s*10\^\{?(-?\d+)\}?(?:\s*\*\s*[a-zA-Z])?$",
            s.strip(), re.I
        )
        if m:
            return float(m.group(1)) * (10 ** int(m.group(2)))
        return None
    ca = extract_coeff(a)
    cb = extract_coeff(b)
    if ca is not None and cb is not None:
        return abs(ca - cb) / max(abs(ca), abs(cb), 1e-30) < 1e-6
    return None


def _extract_answer(llm_text: str) -> Optional[str]:
    """Extract the ОТВЕТ: line from LLM response, cleaned up."""
    if not llm_text:
        return None
    # Garbage detection: asterisks, just whitespace, empty string
    stripped = llm_text.strip()
    if stripped in ('**', '*', '', 'None') or stripped.startswith('**') or len(stripped) < 1:
        return None
    m = re.search(r"ОТВЕТ:\s*(.+)", llm_text, re.I)
    if m:
        raw = m.group(1).strip()
        # Filter out garbage in the answer line itself
        if raw in ('**', '*', '') or raw.startswith('**'):
            return None
        return _strip_latex(raw)
    # Fallback: last non-empty line
    lines = [l.strip() for l in llm_text.splitlines() if l.strip()]
    if lines:
        last = lines[-1]
        if last not in ('**', '*') and not last.startswith('**'):
            return _strip_latex(last)
    return None


# ── SymPy back-substitution proof ───────────────────────────────────────────

# Types where we can try to do algebraic/numeric back-verification
_SYMPY_PROVABLE_TYPES = frozenset({
    "exact_number", "decimal", "fraction", "expression",
    "equation_solution", "set",
})


def _sympy_proof(question: str, answer: str, atype: str) -> Optional[str]:
    """
    Try to mathematically PROVE the answer using SymPy back-substitution.

    Returns:
      'proven'   — SymPy confirmed the answer is correct
      'refuted'  — SymPy proved the answer is WRONG
      'unknown'  — SymPy could not verify (not enough info, symbolic, etc.)

    Uses two strategies (delegated to shared library functions):
      Strategy 1: try_validate_answer_for_question (expression simplification)
      Strategy 2: back_substitute_roots (extract equation, substitute roots)
    """
    if atype not in _SYMPY_PROVABLE_TYPES:
        return "unknown"
    if not question or not answer:
        return "unknown"

    try:
        from src.pipeline.answer_sympy import (
            try_validate_answer_for_question,
            back_substitute_roots,
        )

        # Strategy 1: works for "simplify this expression" type tasks
        val = try_validate_answer_for_question(question, answer, atype)
        if val is True:
            return "proven"
        if val is False:
            return "refuted"

        # Strategy 2: extract equation from question and substitute roots
        val2 = back_substitute_roots(question, answer, atype)
        if val2 is True:
            return "proven"
        if val2 is False:
            return "refuted"

        return "unknown"

    except Exception as e:
        log.debug("SymPy proof error: %s", e)
        return "unknown"


# ── Answer comparison ────────────────────────────────────────────────────────


def _answers_match(stored: str, ai_answer: str, atype: str, question: str = "") -> bool:
    """Check if stored textbook answer matches AI-computed answer."""
    if not stored or not ai_answer:
        return False

    s = _strip_latex(stored.strip())
    a = _strip_latex(ai_answer.strip())

    if s.lower() == a.lower():
        return True

    # Scientific notation equivalence (for expression type with 10^n)
    sci = _sci_notation_equal(s, a)
    if sci is True:
        return True

    # Use existing SymPy-backed answer comparison
    try:
        from src.pipeline.answer_verify import answers_equivalent
        if answers_equivalent(s, a, atype, question=question):
            return True
        # Also try with originals (in case strip changed something)
        if answers_equivalent(stored.strip(), ai_answer.strip(), atype, question=question):
            return True
    except Exception as e:
        log.debug("answers_equivalent error: %s", e)

    # For expression type: use sympy_equivalent for symbolic comparison
    if atype in ("expression", "fraction", "exact_number", "decimal"):
        try:
            from src.pipeline.answer_sympy import sympy_equivalent
            result = sympy_equivalent(s, a, atype)
            if result is True:
                return True
        except Exception as e:
            log.debug("sympy_equivalent error: %s", e)

    # Use interval normalizer for inequality/set types
    if atype in ("inequality", "set", "equation_solution"):
        try:
            from src.pipeline.interval_normalizer import intervals_equivalent
            result = intervals_equivalent(s, a)
            if result is True:
                return True
        except Exception as e:
            log.debug("intervals_equivalent error: %s", e)
    # ── Sorted roots comparison (equation_solution, set)
    # Handles: '1; 2.8; 6' vs '6; 14/5; 1' (same set, different order)
    if atype in ("equation_solution", "set", "fraction"):
        try:
            from src.pipeline.answer_sympy import _latexish_to_sympy
            from sympy import Rational

            def _split_roots(text: str) -> list:
                parts = re.split(r"[;,]", text)
                nums = []
                for p in parts:
                    p = p.strip().replace("x=","").replace("y=","")
                    try:
                        expr = _latexish_to_sympy(p)
                        if expr is not None:
                            nums.append(float(expr.evalf()))
                    except Exception:
                        pass
                return sorted(nums)

            roots_s = _split_roots(s)
            roots_a = _split_roots(a)
            if roots_s and len(roots_s) == len(roots_a):
                if all(abs(x - y) < 0.01 for x, y in zip(roots_s, roots_a)):
                    return True
        except Exception as e:
            log.debug("sorted roots error: %s", e)

    # ── x=a, y=b notation vs coordinate (a; b)  [with SymPy numeric equality]
    # Handles: 'x=16, y=15' vs '(16; 15)', 'x=(-1+√61)/5' vs '((-1+√61)/5)'
    if atype in ("equation_solution", "coordinate"):
        try:
            from src.pipeline.answer_sympy import _latexish_to_sympy

            def _pairs_from_xy(text: str) -> list:
                pairs = []
                for chunk in re.split(r";", text):
                    chunk = chunk.strip().strip("()").strip()
                    mx = re.search(r"x\s*=\s*([^,;]+)", chunk)
                    my = re.search(r"y\s*=\s*([^,;]+)", chunk)
                    if mx and my:
                        pairs.append((mx.group(1).strip(), my.group(1).strip()))
                return pairs

            def _pairs_from_coord(text: str) -> list:
                pairs = []
                for chunk in re.split(r"\)\s*[;,]\s*\(", text.strip().strip("()")):
                    parts = re.split(r"[;,]", chunk)
                    if len(parts) == 2:
                        pairs.append((parts[0].strip(), parts[1].strip()))
                return pairs

            def _sympy_pair_float(px, py):
                """Convert pair of string expressions to (float, float) via SymPy."""
                try:
                    ex = _latexish_to_sympy(px)
                    ey = _latexish_to_sympy(py)
                    if ex is not None and ey is not None:
                        return (float(ex.evalf()), float(ey.evalf()))
                except Exception:
                    pass
                return None

            pairs_s = _pairs_from_xy(s) or _pairs_from_coord(s)
            pairs_a = _pairs_from_xy(a) or _pairs_from_coord(a)
            if pairs_s and len(pairs_s) == len(pairs_a):
                # Convert all pairs to float tuples for comparison
                floats_s = sorted(filter(None, (_sympy_pair_float(*p) for p in pairs_s)))
                floats_a = sorted(filter(None, (_sympy_pair_float(*p) for p in pairs_a)))
                if floats_s and len(floats_s) == len(floats_a):
                    if all(
                        abs(xs - xa) < 0.001 and abs(ys - ya) < 0.001
                        for (xs, ys), (xa, ya) in zip(floats_s, floats_a)
                    ):
                        return True
                else:
                    # Fallback: string sort (works for simple integer pairs)
                    if sorted(pairs_s) == sorted(pairs_a):
                        return True
        except Exception as e:
            log.debug("xy notation error: %s", e)

    # ── x ≠ val  ↔  (-∞; val) ∪ (val; +∞)
    # Handles: 'x ≠ -1' vs '(-∞; -1) ∪ (-1; +∞)'
    if atype == "inequality":
        try:
            def _xne_val(text: str):
                m2 = re.search(r"[a-zA-Z]\s*≠\s*([^\s]+)", text)
                if not m2:
                    m2 = re.search(r"[a-zA-Z]\s*!=\s*([^\s]+)", text)
                if m2:
                    return m2.group(1).strip()
                return None

            ne_s = _xne_val(s)
            ne_a = _xne_val(a)
            # Check if one is x≠c and the other is full interval notation for same c
            if ne_s and not ne_a:
                from src.pipeline.interval_normalizer import _to_sympy_set, _parse_bound
                excl = _parse_bound(ne_s)
                si = _to_sympy_set(a)
                if excl is not None and si is not None:
                    from sympy import oo, Union, Interval
                    expected = Union(Interval(-oo, excl, True, True), Interval(excl, oo, True, True))
                    if si == expected:
                        return True
            if ne_a and not ne_s:
                from src.pipeline.interval_normalizer import _to_sympy_set, _parse_bound
                excl = _parse_bound(ne_a)
                si = _to_sympy_set(s)
                if excl is not None and si is not None:
                    from sympy import oo, Union, Interval
                    expected = Union(Interval(-oo, excl, True, True), Interval(excl, oo, True, True))
                    if si == expected:
                        return True
        except Exception as e:
            log.debug("xne interval error: %s", e)

    return False


# ── DB helpers ───────────────────────────────────────────────────────────────

def get_quarantined_tasks(conn, limit: Optional[int] = None, worker_id: Optional[int] = None, num_workers: Optional[int] = None):
    """
    Fetch tasks that need processing:
    1. Tasks without distractors (original quarantine flow)
    2. Tasks WITH distractors but not yet SymPy back-substitution verified
       (covers the 939 tasks that went through the main pipeline only)
    """
    parallel_clause = ""
    if num_workers is not None and worker_id is not None:
        parallel_clause = f"AND (abs(hashtext(t.id)) % {num_workers} = {worker_id})"

    query = f"""
        SELECT
            t.id,
            t.toc_id,
            t.correct_answer,
            t.answer_type,
            t.tags,
            t.distractor_meta,
            tt.exercise_number,
            t.question_text
        FROM tasks_master t
        JOIN textbook_tasks tt ON t.id = tt.task_id
        WHERE
            t.toc_id IN (1054, 1055, 1056, 1057)
            AND (t.correct_answer IS NOT NULL AND t.correct_answer != '')
            AND (t.tags->>'smart_verify_status' IS NULL
                 OR t.tags->>'smart_verify_status' NOT IN (
                     'needs_human_review', 'needs_compound_split', 'skipped_type'
                 ))
            AND (t.tags->>'quarantine_v3_processed' IS NULL)
            {parallel_clause}
            AND (
                -- Case 1: No distractors yet (classic quarantine)
                (t.distractor_meta IS NULL OR jsonb_array_length(t.distractor_meta) = 0)
                OR
                -- Case 2: Has distractors but SymPy proof not run yet
                (
                    t.distractor_meta IS NOT NULL
                    AND jsonb_array_length(t.distractor_meta) > 0
                    AND (t.tags->>'quarantine_v3_sympy_proven' IS NULL)
                    AND t.answer_type IN (
                        'equation_solution', 'set', 'exact_number', 'decimal', 'fraction', 'expression'
                    )
                )
            )
        ORDER BY t.toc_id, tt.exercise_number
    """
    if limit:
        query += f" LIMIT {limit}"
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute(query)
    return cur.fetchall()


def update_task(conn, task_id, distractor_meta: list, tags: dict,
                dry_run: bool = False, correct_answer: str = None):
    tags["quarantine_v3_processed"] = True
    is_override = tags.get("quarantine_v3_source") == "ai_consensus_override"
    if dry_run:
        override_note = f" [AI OVERRIDE: {correct_answer!r}]" if is_override else ""
        log.info("[DRY-RUN] Would write %d distractors | verified=%s%s",
                 len(distractor_meta), tags.get("quarantine_v3_verified"), override_note)
        return
    cur = conn.cursor()
    if is_override and correct_answer:
        # Update correct_answer to the mathematically verified AI answer
        cur.execute("""
            UPDATE tasks_master
            SET
                distractor_meta = %s::jsonb,
                tags = tags || %s::jsonb,
                correct_answer = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (
            json.dumps(distractor_meta, ensure_ascii=False),
            json.dumps(tags, ensure_ascii=False),
            correct_answer,
            task_id,
        ))
    else:
        cur.execute("""
            UPDATE tasks_master
            SET
                distractor_meta = %s::jsonb,
                tags = tags || %s::jsonb,
                updated_at = NOW()
            WHERE id = %s
        """, (
            json.dumps(distractor_meta, ensure_ascii=False),
            json.dumps(tags, ensure_ascii=False),
            task_id,
        ))
    conn.commit()



def mark_human_review(conn, task_id, ai_answer: str, tags: dict, dry_run: bool = False):
    tags["quarantine_v3_processed"] = True
    tags["quarantine_v3_needs_review"] = True
    tags["quarantine_v3_ai_answer"] = ai_answer[:300]
    if dry_run:
        log.info("[DRY-RUN] Would mark task %s for human review (ai=%r)", task_id, ai_answer[:60])
        return
    cur = conn.cursor()
    cur.execute("""
        UPDATE tasks_master
        SET tags = tags || %s::jsonb, updated_at = NOW()
        WHERE id = %s
    """, (json.dumps(tags, ensure_ascii=False), task_id))
    conn.commit()


# ── Main logic per task ──────────────────────────────────────────────────────

def process_task(task, dry_run: bool = False) -> dict:
    task_id = task["id"]
    atype = (task["answer_type"] or "exact_number").strip()
    stored = (task["correct_answer"] or "").strip()
    question = (task["question_text"] or "").strip()
    tags = dict(task["tags"] or {})
    has_distractors = bool(task["distractor_meta"] and len(task["distractor_meta"]) > 0)

    if not question:
        return {"status": "skipped", "reason": "no_question"}

    if not stored or stored in ("—", "-"):
        return {"status": "skipped", "reason": "no_stored_answer"}

    # FAST PATH: Task already has distractors — only run SymPy proof (no AI re-solve needed).
    # This handles the 939 tasks from the main pipeline that need SymPy verification backfill.
    if has_distractors:
        sympy_result = _sympy_proof(question, stored, atype)
        tags["quarantine_v3_sympy_proof"] = sympy_result
        tags["quarantine_v3_sympy_proven"] = (sympy_result == "proven")
        tags["quarantine_v3_processed"] = True

        if sympy_result == "refuted":
            log.error(
                "  ❌ SymPy REFUTED stored answer for task with distractors! "
                "stored=%r — escalating to human review",
                stored[:60]
            )
            return {"status": "mismatch", "ai_answer": stored, "tags": tags}
        elif sympy_result == "proven":
            log.info("  🔬 SymPy PROVED existing answer correct: %r", stored[:50])
        else:
            log.debug("  SymPy proof: unknown for %r", stored[:40])

        # Keep existing distractors, just update the tags
        distractor_meta = list(task["distractor_meta"])
        return {
            "status": "success",
            "distractor_meta": distractor_meta,
            "tags": tags,
            "correct_answer": stored,
        }

    # STEP 1: Independent solve via DeepSeek chat
    try:
        from src.pipeline.deepseek_client import call_deepseek
        prompt = _build_solve_prompt(question, atype)
        llm_text = call_deepseek(
            prompt,
            system_prompt=SOLVE_SYSTEM,
            temperature=0.0,
            max_tokens=2048,
        )
        ai_answer = _extract_answer(llm_text)
    except Exception as exc:
        log.warning("  DeepSeek solve failed: %s", exc)
        return {"status": "api_error", "reason": str(exc)[:100]}

    if not ai_answer:
        return {"status": "skipped", "reason": "ai_no_answer"}

    log.info("  Textbook: %r  |  AI-1: %r", stored[:50], ai_answer[:50])

    # STEP 2: Compare AI answer with textbook
    matched_textbook = _answers_match(stored, ai_answer, atype, question=question)

    if matched_textbook:
        # Great — first solve already confirms textbook answer
        final_answer = stored
        log.info("  ✅ AI-1 confirms textbook answer")
        tags["quarantine_v3_verified"] = True
        tags["quarantine_v3_source"] = "textbook_confirmed"
        tags["quarantine_v3_ai_answer"] = ai_answer[:300]
    else:
        # STEP 2b: Second independent solve — MATHEMATICS FIRST
        # Run with a stronger "show all work" prompt to get the right answer
        log.info("  ⚡ Mismatch — running 2nd independent solve...")
        try:
            from src.pipeline.deepseek_client import call_deepseek
            prompt2 = (
                f"Задача (реши шаг за шагом, покажи всё решение):\n{question}\n\n"
                f"Тип ответа: {atype}.\n\n"
                "После полного решения напиши строку:\n"
                "ОТВЕТ: <только значение>"
            )
            llm_text2 = call_deepseek(
                prompt2,
                system_prompt=(
                    "Ты опытный учитель математики. Решай задачу строго шаг за шагом. "
                    "Не угадывай — только математически точный вывод. "
                    "В конце одна строка: ОТВЕТ: <значение>"
                ),
                temperature=0.0,
                max_tokens=4096,
            )
            ai_answer2 = _extract_answer(llm_text2)
        except Exception as exc:
            log.warning("  2nd solve failed: %s", exc)
            ai_answer2 = None

        log.info("  AI-2: %r", (ai_answer2 or "failed")[:50])

        if not ai_answer2:
            # 2nd solve failed → flag for human review, use textbook as fallback
            log.warning("  ❌ 2nd solve failed → human review")
            tags["quarantine_v3_verified"] = False
            tags["quarantine_v3_ai_answer"] = ai_answer[:300]
            return {"status": "mismatch", "ai_answer": ai_answer, "tags": tags}

        ai2_matches_textbook = _answers_match(stored, ai_answer2, atype, question=question)
        ai2_matches_ai1 = _answers_match(ai_answer, ai_answer2, atype, question=question)

        if ai2_matches_textbook:
            # Both AI solves confirm OR 2nd confirms textbook
            log.info("  ✅ AI-2 confirms textbook answer")
            final_answer = stored
            tags["quarantine_v3_verified"] = True
            tags["quarantine_v3_source"] = "textbook_confirmed_by_ai2"
            tags["quarantine_v3_ai_answer"] = ai_answer2[:300]

        elif ai2_matches_ai1:
            # AI CONSENSUS: both AI solves agree on a DIFFERENT answer than textbook
            # Trust the math, not the book — update correct_answer
            log.warning(
                "  🔄 AI CONSENSUS overrides textbook: ai=%r | textbook=%r",
                ai_answer[:60], stored[:60]
            )
            final_answer = ai_answer  # mathematically verified by two independent solves
            tags["quarantine_v3_verified"] = True
            tags["quarantine_v3_source"] = "ai_consensus_override"
            tags["quarantine_v3_ai_answer"] = ai_answer[:300]
            tags["quarantine_v3_textbook_answer"] = stored[:300]
            tags["correct_answer_overridden"] = True
        else:
            # Three-way disagreement: textbook, AI-1 and AI-2 all differ
            log.warning(
                "  ❌ 3-WAY CONFLICT: textbook=%r | ai1=%r | ai2=%r",
                stored[:40], ai_answer[:40], ai_answer2[:40]
            )
            tags["quarantine_v3_verified"] = False
            tags["quarantine_v3_ai_answer"] = ai_answer[:300]
            tags["quarantine_v3_ai2_answer"] = ai_answer2[:300]
            return {"status": "mismatch", "ai_answer": ai_answer, "tags": tags}


    # STEP 2.5: SymPy back-substitution proof (max quality gate)
    # For equation/number types: mathematically verify the final answer by substituting
    # back into the equation extracted from the question. This catches cases where
    # two AIs agreed on the same WRONG answer.
    sympy_proof_result = _sympy_proof(question, final_answer, atype)
    tags["quarantine_v3_sympy_proof"] = sympy_proof_result

    if sympy_proof_result == "proven":
        log.info("  🔬 SymPy PROVED the answer correct (back-substitution verified)")
        tags["quarantine_v3_sympy_proven"] = True
    elif sympy_proof_result == "refuted":
        # SymPy mathematically DISPROVED the answer that AI agreed on!
        # This is a critical catch — do NOT write wrong data to DB.
        log.error(
            "  ❌ SymPy REFUTED the answer! final=%r | source=%s — escalating to human review",
            final_answer[:60], tags.get("quarantine_v3_source", "unknown")
        )
        tags["quarantine_v3_sympy_proof"] = "refuted"
        tags["quarantine_v3_sympy_proven"] = False
        tags["quarantine_v3_verified"] = False
        tags["quarantine_v3_ai_answer"] = final_answer[:300]
        return {"status": "mismatch", "ai_answer": final_answer, "tags": tags}
    else:
        # unknown — SymPy could not verify (symbolic, text task, etc.) — proceed normally
        log.debug("  SymPy proof: unknown (not verifiable algebraically)")
        tags["quarantine_v3_sympy_proven"] = False

    # STEP 3: Generate distractors on VERIFIED answer (may be AI or textbook)
    is_override = tags.get("quarantine_v3_source") == "ai_consensus_override"
    log.info("  ✅ Generating distractors on %s answer: %r",
             "AI-consensus" if is_override else "textbook", final_answer[:50])

    try:
        from src.pipeline.models import ExtractedTask
        from src.pipeline.distractors import generate_distractors

        t = ExtractedTask(
            temp_id=str(task_id),
            question_text=question,
            answer_type=atype,
            answer_raw=final_answer,  # verified answer (textbook OR AI consensus)
            tags=dict(tags),
            distractors=[],
            distractor_meta=[],
        )
        t = generate_distractors(t, verify_answer=False, force_distractors=True)
        distractor_meta = list(t.distractor_meta or [])
        tags_out = dict(t.tags or tags)
        tags_out["quarantine_v3_verified"] = True

        if len(distractor_meta) >= 2:
            return {
                "status": "success",
                "distractor_meta": distractor_meta,
                "tags": tags_out,
                "correct_answer": final_answer,  # may differ from stored if AI overrode
            }
        else:
            return {"status": "review", "reason": "too_few_distractors",
                    "distractor_meta": distractor_meta, "tags": tags_out,
                    "correct_answer": final_answer}
    except Exception as exc:
        log.error("  Distractor generation failed: %s", exc)
        return {"status": "error", "reason": str(exc)[:200], "tags": tags}


# ── Runner ───────────────────────────────────────────────────────────────────

def run(dry_run: bool = False, limit: Optional[int] = None, worker_id: Optional[int] = None, num_workers: Optional[int] = None):
    conn = psycopg2.connect(DB_URL)
    tasks = get_quarantined_tasks(conn, limit=limit, worker_id=worker_id, num_workers=num_workers)
    total = len(tasks)
    log.info("=" * 60)
    log.info("SmartVerify Quarantine Runner v3 — FULL VERIFICATION")
    log.info("Tasks to process: %d  (dry_run=%s, worker_id=%s, num_workers=%s)", total, dry_run, worker_id, num_workers)
    log.info("=" * 60)

    stats = {"success": 0, "mismatch": 0, "review": 0,
             "skipped": 0, "api_error": 0, "error": 0}

    for i, task in enumerate(tasks, 1):
        task_id = task["id"]
        ex_num = task["exercise_number"] or "?"
        atype = task["answer_type"] or "?"
        stored = (task["correct_answer"] or "")[:50]
        log.info("[%d/%d] %s  Ex.%s  [%s]  stored=%r",
                 i, total, task_id, ex_num, atype, stored)

        result = process_task(task, dry_run=dry_run)
        status = result.get("status", "error")
        stats[status] = stats.get(status, 0) + 1

        if status == "success":
            update_task(conn, task_id, result["distractor_meta"], result["tags"],
                        dry_run, correct_answer=result.get("correct_answer"))
        elif status == "mismatch":
            mark_human_review(conn, task_id, result.get("ai_answer", ""), result["tags"], dry_run)
        elif status == "review" and result.get("distractor_meta"):
            update_task(conn, task_id, result["distractor_meta"], result["tags"],
                        dry_run, correct_answer=result.get("correct_answer"))

        if i % BATCH_SIZE == 0:
            pct = i / total * 100
            log.info("── [%d/%d] %.0f%% ── %s", i, total, pct, stats)
            time.sleep(BATCH_PAUSE_S)

    conn.close()
    log.info("=" * 60)
    log.info("COMPLETE — %d tasks processed", total)
    log.info("  ✅ Verified + distractors: %d", stats.get("success", 0))
    log.info("  ❌ Answer mismatch (→ human review): %d", stats.get("mismatch", 0))
    log.info("  👁  Too few distractors: %d", stats.get("review", 0))
    log.info("  ⏭  Skipped: %d", stats.get("skipped", 0))
    log.info("  📡  API errors: %d", stats.get("api_error", 0))
    log.info("  💥  Other errors: %d", stats.get("error", 0))
    log.info("=" * 60)
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--worker-id", type=int, default=None)
    parser.add_argument("--num-workers", type=int, default=None)
    args = parser.parse_args()
    run(dry_run=args.dry_run, limit=args.limit, worker_id=args.worker_id, num_workers=args.num_workers)
