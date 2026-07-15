"""Content Service — Database Writer

Batch upsert of digitized tasks into the shared PostgreSQL database.
Tables: textbooks, textbook_toc, tasks_master, textbook_tasks.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.models import ExtractedTask, Figure

log = logging.getLogger(__name__)

# Module-level engine — one connection pool shared across all DBWriter calls
_ENGINE = None


def _engine():
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = create_engine(
            get_settings().database_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
    return _ENGINE


class DBWriter:
    """Writes digitized tasks to PostgreSQL (tasks_master + textbook_tasks)."""

    # ── Textbook registration ─────────────────────────────────────────────

    def upsert_textbook(
        self,
        textbook_id: str,
        title: str,
        class_level: int,
        authors: Optional[List[str]] = None,
        subtitle: Optional[str] = None,
        publisher: Optional[str] = None,
        isbn: Optional[str] = None,
        edition: Optional[str] = None,
        total_pages: Optional[int] = None,
        cover_image_url: Optional[str] = None,
        subject: str = "math",
        country: str = "UZ",
        language: str = "ru",
    ) -> str:
        """Insert or update a textbook record. Returns textbook_id."""
        engine = _engine()
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO textbooks (
                        textbook_id, title, authors, class_level,
                        subtitle, publisher, isbn, edition, total_pages,
                        cover_image_url, subject, country, language,
                        digitization_status, digitization_progress, tasks_extracted,
                        is_active
                    ) VALUES (
                        CAST(:tb_id AS UUID), :title, :authors, :class_level,
                        :subtitle, :publisher, :isbn, :edition, :total_pages,
                        :cover_image_url, :subject, :country, :language,
                        'pending', 0, 0, TRUE
                    )
                    ON CONFLICT (textbook_id) DO UPDATE SET
                        title           = EXCLUDED.title,
                        authors         = EXCLUDED.authors,
                        subtitle        = EXCLUDED.subtitle,
                        publisher       = EXCLUDED.publisher,
                        isbn            = EXCLUDED.isbn,
                        edition         = EXCLUDED.edition,
                        total_pages     = EXCLUDED.total_pages,
                        cover_image_url = EXCLUDED.cover_image_url,
                        updated_at      = NOW()
                """),
                {
                    "tb_id": textbook_id,
                    "title": title,
                    "authors": authors or [],
                    "class_level": class_level,
                    "subtitle": subtitle,
                    "publisher": publisher,
                    "isbn": isbn,
                    "edition": edition,
                    "total_pages": total_pages,
                    "cover_image_url": cover_image_url,
                    "subject": subject,
                    "country": country,
                    "language": language,
                },
            )
        log.info("DBWriter: upserted textbook %s (%s)", textbook_id, title)
        return textbook_id

    def write_toc(
        self,
        textbook_id: str,
        toc_entries: List[Dict[str, Any]],
    ) -> int:
        """
        Insert TOC entries for a textbook. Clears existing TOC first.

        Each entry dict:
          {
            "number":     "3.1",          # section number (str)
            "title":      "Дроби",        # display title
            "level":      2,              # 1=chapter, 2=paragraph, 3=topic
            "parent_id":  None,           # DB id of parent row (filled after insert)
            "page_start": 48,             # first page (optional)
            "page_end":   55,             # last page (optional)
            "sort_order": 5,              # ordering within book
          }

        Supports parent-child hierarchy: use "parent_number" (str) to reference
        parent by its number field, OR "parent_id" (int) for already-inserted rows.
        Returns count of rows inserted.
        """
        if not toc_entries:
            return 0

        engine = _engine()
        with engine.begin() as conn:
            # Clear existing TOC for this textbook
            conn.execute(
                text("DELETE FROM textbook_toc WHERE textbook_id = CAST(:tb_id AS UUID)"),
                {"tb_id": textbook_id},
            )

            # Two-pass insert: first pass without parent_id, second pass resolves them
            number_to_id: Dict[str, int] = {}

            for sort_idx, entry in enumerate(toc_entries):
                row = conn.execute(
                    text("""
                        INSERT INTO textbook_toc (
                            textbook_id, level, number, title,
                            page_start, page_end, sort_order
                        ) VALUES (
                            CAST(:tb_id AS UUID), :level, :number, :title,
                            :page_start, :page_end, :sort_order
                        )
                        RETURNING id
                    """),
                    {
                        "tb_id": textbook_id,
                        "level": int(entry.get("level", 2)),
                        "number": str(entry.get("number", "")),
                        "title": str(entry.get("title", "")),
                        "page_start": entry.get("page_start"),
                        "page_end": entry.get("page_end"),
                        "sort_order": entry.get("sort_order", sort_idx),
                    },
                ).fetchone()
                inserted_id = row[0]
                number_to_id[str(entry.get("number", ""))] = inserted_id

            # Second pass: set parent_id by number reference
            for entry in toc_entries:
                parent_num = str(entry.get("parent_number", "")).strip()
                if parent_num and parent_num in number_to_id:
                    parent_db_id = number_to_id[parent_num]
                    child_db_id = number_to_id.get(str(entry.get("number", "")))
                    if child_db_id:
                        conn.execute(
                            text("UPDATE textbook_toc SET parent_id = :pid WHERE id = :cid"),
                            {"pid": parent_db_id, "cid": child_db_id},
                        )

        log.info("DBWriter: wrote %d TOC entries for textbook %s", len(toc_entries), textbook_id)
        return len(toc_entries)

    def update_digitization_status(
        self,
        textbook_id: str,
        status: str,
        progress: float = 0.0,
        tasks_extracted: int = 0,
    ) -> None:
        """Update textbook digitization_status and progress."""
        engine = _engine()
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE textbooks
                    SET digitization_status   = :status,
                        digitization_progress = :progress,
                        tasks_extracted       = :tasks_extracted,
                        updated_at            = NOW()
                    WHERE textbook_id = CAST(:tb_id AS UUID)
                """),
                {
                    "tb_id": textbook_id,
                    "status": status,
                    "progress": progress,
                    "tasks_extracted": tasks_extracted,
                },
            )

    def increment_tasks_skipped(self, textbook_id: str, count: int) -> None:
        """Атомарно увеличивает счётчик offline-задач, отброшенных фильтром."""
        if count <= 0:
            return
        engine = _engine()
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE textbooks
                    SET tasks_skipped = COALESCE(tasks_skipped, 0) + :c,
                        updated_at    = NOW()
                    WHERE textbook_id = CAST(:tb_id AS UUID)
                """),
                {"tb_id": textbook_id, "c": int(count)},
            )

    def increment_figures_skipped(self, textbook_id: str, count: int) -> None:
        """Атомарно увеличивает счётчик бесполезных рисунков (фото, портреты, орнаменты)."""
        if count <= 0:
            return
        engine = _engine()
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE textbooks
                    SET figures_skipped = COALESCE(figures_skipped, 0) + :c,
                        updated_at      = NOW()
                    WHERE textbook_id = CAST(:tb_id AS UUID)
                """),
                {"tb_id": textbook_id, "c": int(count)},
            )

    def save_ocr_text(self, textbook_id: str, text: str) -> None:
        """Persist raw OCR text so the pipeline can be resumed without re-OCR."""
        engine = _engine()
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE textbooks
                    SET ocr_text = :ocr_text,
                        ocr_completed_at = NOW(),
                        updated_at = NOW()
                    WHERE textbook_id = CAST(:tb_id AS UUID)
                """),
                {"tb_id": textbook_id, "ocr_text": text},
            )
        log.info("OCR text saved for textbook %s (%d chars)", textbook_id, len(text))

    def load_ocr_text(self, textbook_id: str) -> Optional[str]:
        """Return previously saved OCR text, or None if not yet stored."""
        engine = _engine()
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT ocr_text FROM textbooks WHERE textbook_id = CAST(:tb_id AS UUID)"),
                {"tb_id": textbook_id},
            ).fetchone()
        return row[0] if row and row[0] else None

    def write_batch(
        self,
        tasks: List[ExtractedTask],
        textbook_id: str,
        class_level: int,
        prefix: str = "G_TB",
    ) -> int:
        """Upsert a batch of tasks. Returns the count of rows written."""
        if not tasks:
            return 0

        engine = _engine()
        written = 0
        # Preload valid figure_ids for this textbook so we can drop broken refs
        # BEFORE the INSERT (FK violation would abort the whole batch otherwise).
        try:
            valid_fig_ids = self.load_figure_ids(textbook_id)
        except Exception:
            valid_fig_ids = set()

        # Valid enum values enforced by DB CHECK constraints
        _VALID_DIFFICULTY = {"A", "B", "C"}
        _VALID_COGLOAD = {"recall", "apply", "analyze"}
        _VALID_ANSWER_TYPE = {
            "exact_number", "expression", "multiple_choice", "text",
            "fraction", "equation_solution", "set", "coordinate",
            "inequality", "decimal", "open_text", "multiple_values",
        }
        _VALID_TASK_CATEGORY = {
            "standard", "advanced", "olympiad",
            "oral", "research", "project", "with_drawing",
        }

        # Per-task transaction so one bad row (trigger raise, FK violation,
        # CHECK constraint) does NOT kill the whole paragraph batch.
        skipped_no_skill = 0
        skipped_no_question = 0
        skipped_exists = 0
        failed_db = 0
        for task in tasks:
            if not task.question_text:
                log.warning("Skip %s: no question_text", task.temp_id)
                skipped_no_question += 1
                continue
            if not task.skill_id:
                log.info(
                    "Task %s: no skill_id — saving as exam-only task (toc_id=%s)",
                    task.temp_id, task.toc_id,
                )
                skipped_no_skill += 1  # still count for stats
            try:
                with engine.begin() as conn:
                    inserted = self._insert_one_task(
                        conn, task, textbook_id, class_level, prefix,
                        valid_fig_ids,
                        _VALID_DIFFICULTY, _VALID_COGLOAD,
                        _VALID_ANSWER_TYPE, _VALID_TASK_CATEGORY,
                    )
                if inserted:
                    written += 1
                else:
                    skipped_exists += 1
            except Exception as exc:
                failed_db += 1
                log.error(
                    "DBWriter: task %s INSERT failed: %s",
                    task.temp_id, str(exc)[:300],
                )

        log.info(
            "DBWriter: wrote %d/%d tasks (skipped: exists=%d no_skill=%d no_question=%d db_fail=%d)",
            written, len(tasks), skipped_exists, skipped_no_skill, skipped_no_question, failed_db,
        )
        return written

    def _insert_one_task(
        self,
        conn,
        task,
        textbook_id: str,
        class_level: int,
        prefix: str,
        valid_fig_ids: set,
        _VALID_DIFFICULTY,
        _VALID_COGLOAD,
        _VALID_ANSWER_TYPE,
        _VALID_TASK_CATEGORY,
    ) -> bool:
        # ── Sanitize fields against DB CHECK constraints ──────────
        difficulty = task.difficulty if task.difficulty in _VALID_DIFFICULTY else "B"
        cognitive_load = task.cognitive_load if task.cognitive_load in _VALID_COGLOAD else "apply"
        answer_type = task.answer_type if task.answer_type in _VALID_ANSWER_TYPE else "exact_number"
        correct_answer = task.answer_raw.strip() if task.answer_raw else "—"
        skill_id = task.skill_id.strip() or None if task.skill_id else None

        # Hard safety net: ensure every varchar(20) value really fits, even if
        # enrichment/mapper mutated the dataclass after our enum clamp. This
        # protects against `value too long for type character varying(20)`.
        if len(cognitive_load) > 20:
            cognitive_load = "apply"
        if len(answer_type) > 20:
            answer_type = "exact_number"

        if task.difficulty not in _VALID_DIFFICULTY:
            log.warning("Fix difficulty '%s'→'B' for %s", task.difficulty, task.temp_id)
        if task.cognitive_load not in _VALID_COGLOAD:
            log.warning("Fix cognitive_load '%s'→'apply' for %s", task.cognitive_load, task.temp_id)

        # ── Категория (только оффлайн-типы; advanced/olympiad → standard) ──
        task_category = task.task_category if task.task_category in _VALID_TASK_CATEGORY else "standard"
        if task_category in ("advanced", "olympiad"):
            task_category = "standard"
        if len(task_category) > 20:
            task_category = "standard"
        is_star = False
        # ─────────────────────────────────────────────────────────

        task_id = (
            f"{prefix}_{task.paragraph_number}_{task.exercise_number}"
            .replace(".", "_").replace(" ", "")
        )[:60]  # VARCHAR(60) в БД

        # IRT b — только из difficulty (A/B/C), без надбавок за маркеры
        irt_b = {"A": -1.0, "B": 0.5, "C": 1.5}.get(difficulty, 0.0)
        irt_a = 1.0
        irt_c = 0.2 if answer_type == "multiple_choice" else 0.0

        # Enrich tags with quality signals before writing
        tags = dict(task.tags or {})
        tags["sympy_verified"] = task.sympy_verified
        if task.sympy_verified:
            tags["sympy_confidence"] = round(task.sympy_confidence, 3)
        if task.mapping_confidence:
            tags.setdefault("mapping_confidence", round(task.mapping_confidence, 3))

        from src.pipeline.answer_sympy_gate import to_answer_latex
        correct_answer_latex = to_answer_latex(correct_answer, answer_type)

        result = conn.execute(
            text("""
                INSERT INTO tasks_master (
                    id, skill_id, question_text, question_latex, correct_answer,
                    correct_answer_latex,
                    answer_type, difficulty, cognitive_load,
                    irt_discrimination, irt_difficulty, irt_guessing,
                    distractor_meta, answer_options,
                    toc_id, tags,
                    is_star, task_category,
                    verification_status, source_type, source_reference,
                    is_active, created_at
                ) VALUES (
                    :id, :skill_id, :question_text, :question_latex, :correct_answer,
                    :correct_answer_latex,
                    :answer_type, :difficulty, :cognitive_load,
                    :irt_a, :irt_b, :irt_c,
                    :distractor_meta, :answer_options,
                    :toc_id, :tags,
                    :is_star, :task_category,
                    :verification_status, 'textbook', :source_ref,
                    TRUE, NOW()
                )
                ON CONFLICT (id) DO NOTHING
                RETURNING id
            """),
            {
                "id": task_id,
                "skill_id": skill_id,
                "question_text": task.question_text,
                "question_latex": task.question_latex or "",
                "correct_answer": correct_answer,
                "correct_answer_latex": correct_answer_latex,
                "answer_type": answer_type,
                "difficulty": difficulty,
                "cognitive_load": cognitive_load,
                "irt_a": irt_a,
                "irt_b": irt_b,
                "irt_c": irt_c,
                "distractor_meta": json.dumps(task.distractor_meta or [], ensure_ascii=False),
                "answer_options": json.dumps(task.answer_options or [], ensure_ascii=False),
                "toc_id": task.toc_id,
                "tags": json.dumps(tags, ensure_ascii=False),
                "is_star": is_star,
                "task_category": task_category,
                "verification_status": "verified" if task.sympy_verified else "pending",
                "source_ref": f"{textbook_id}::{task.paragraph_number}:{task.exercise_number}",
            },
        )
        if result.fetchone() is None:
            return False

        # Bridge table: textbook ↔ task
        conn.execute(
            text("""
                INSERT INTO textbook_tasks (textbook_id, task_id, paragraph_number, exercise_number)
                VALUES (CAST(:tb_id AS UUID), :task_id, :para, :ex)
                ON CONFLICT (textbook_id, task_id) DO NOTHING
            """),
            {
                "tb_id": textbook_id,
                "task_id": task_id,
                "para": str(task.paragraph_number)[:30],
                "ex": str(task.exercise_number)[:20],
            },
        )

        # Figures ↔ task (m2m). Drop refs that point to non-existent figures
        # to prevent FK violations from rolling back the task INSERT.
        valid_refs = [
            fid for fid in (task.figure_refs or [])
            if not valid_fig_ids or fid in valid_fig_ids
        ]
        dropped_refs = len(task.figure_refs or []) - len(valid_refs)
        if dropped_refs:
            log.warning(
                "Task %s: dropped %d figure_refs not in task_figures",
                task.temp_id, dropped_refs,
            )
        if valid_refs:
            conn.execute(
                text("DELETE FROM task_figure_refs WHERE task_id = :tid"),
                {"tid": task_id},
            )
            for order_idx, fig_id in enumerate(valid_refs):
                conn.execute(
                    text("""
                        INSERT INTO task_figure_refs (task_id, figure_id, order_idx)
                        VALUES (:tid, :fid, :oi)
                        ON CONFLICT (task_id, figure_id) DO UPDATE
                          SET order_idx = EXCLUDED.order_idx
                    """),
                    {"tid": task_id, "fid": fig_id, "oi": order_idx},
                )
        return True

    # ── Figures ───────────────────────────────────────────────────────────

    def write_figures(self, figures: List[Figure], textbook_id: str) -> int:
        """Upsert figures для учебника. Возвращает число записанных."""
        if not figures:
            return 0
        engine = _engine()
        with engine.begin() as conn:
            for fig in figures:
                conn.execute(
                    text("""
                        INSERT INTO task_figures (
                            figure_id, textbook_id, page, bbox, image_url,
                            alt_text, semantic_json
                        ) VALUES (
                            :fid, CAST(:tb AS UUID), :page, CAST(:bbox AS JSONB), :url,
                            :alt, CAST(:sem AS JSONB)
                        )
                        ON CONFLICT (figure_id) DO UPDATE SET
                            bbox          = EXCLUDED.bbox,
                            image_url     = EXCLUDED.image_url,
                            alt_text      = EXCLUDED.alt_text,
                            semantic_json = EXCLUDED.semantic_json
                    """),
                    {
                        "fid": fig.figure_id,
                        "tb": textbook_id,
                        "page": fig.page,
                        "bbox": json.dumps(fig.bbox),
                        "url": fig.image_url,
                        "alt": fig.alt_text or None,
                        "sem": json.dumps(fig.semantic_json or {}, ensure_ascii=False),
                    },
                )
        log.info("DBWriter: wrote %d figures for textbook %s", len(figures), textbook_id)
        return len(figures)

    def load_figure_ids(self, textbook_id: str) -> set[str]:
        """Возвращает множество figure_id для учебника (для валидации ссылок)."""
        engine = _engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT figure_id FROM task_figures WHERE textbook_id = CAST(:tb AS UUID)"),
                {"tb": textbook_id},
            ).fetchall()
        return {r[0] for r in rows}

    def load_toc(self, textbook_id: str) -> list:
        """Load TOC entries for a textbook from the database."""
        engine = _engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT tt.id, tt.number, tt.title, tt.page_start, tt.page_end,
                           tt.level, tt.sort_order, p.number AS parent_number
                    FROM textbook_toc tt
                    LEFT JOIN textbook_toc p ON p.id = tt.parent_id
                    WHERE tt.textbook_id = CAST(:tb_id AS UUID)
                    ORDER BY tt.sort_order, tt.page_start
                """),
                {"tb_id": textbook_id},
            ).fetchall()
        return [
            {
                "id": r[0], "number": r[1], "title": r[2],
                "page_start": r[3], "page_end": r[4], "level": r[5],
                "sort_order": r[6], "parent_number": r[7] or "",
            }
            for r in rows
        ]

    def load_paragraph_exercise_numbers(
        self,
        textbook_id: str,
        paragraph_number: str,
    ) -> set[int]:
        """Exercise numbers already stored for this § (from textbook_tasks)."""
        engine = _engine()
        key = paragraph_number.strip()
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT tt.exercise_number
                    FROM textbook_tasks tt
                    WHERE tt.textbook_id = CAST(:tb AS UUID)
                      AND tt.paragraph_number = :para
                """),
                {"tb": textbook_id, "para": key},
            ).fetchall()
        nums: set[int] = set()
        for (raw,) in rows:
            try:
                nums.add(int(str(raw).split(".")[0]))
            except ValueError:
                pass
        return nums

    def load_paragraph_question_fingerprints(
        self,
        textbook_id: str,
        paragraph_number: str,
    ) -> set[str]:
        """Normalized question text snippets for dedup within a §."""
        from src.pipeline.dedup import question_fingerprint

        key = paragraph_number.strip()
        engine = _engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT tm.question_text
                    FROM tasks_master tm
                    JOIN textbook_tasks tt ON tt.task_id = tm.id
                    WHERE tt.textbook_id = CAST(:tb AS UUID)
                      AND tt.paragraph_number = :para
                """),
                {"tb": textbook_id, "para": key},
            ).fetchall()
        out: set[str] = set()
        for (q,) in rows:
            fp = question_fingerprint(q or "")
            if fp:
                out.add(fp)
        return out

    def missing_exercises(
        self,
        textbook_id: str,
        paragraph_number: str,
    ) -> list[int] | None:
        """Return missing ex numbers for §, or None if no range table."""
        from src.pipeline.exercise_ranges import exercise_range

        lo_hi = exercise_range(textbook_id, paragraph_number)
        if not lo_hi:
            return None
        lo, hi = lo_hi
        in_db = self.load_paragraph_exercise_numbers(textbook_id, paragraph_number)
        return [n for n in range(lo, hi + 1) if n not in in_db]

    def paragraph_has_tasks(self, toc_id) -> bool:
        """True if tasks_master already contains rows for this TOC entry — used for resume."""
        if toc_id is None:
            return False
        engine = _engine()
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT 1 FROM tasks_master WHERE toc_id = :tid LIMIT 1"),
                {"tid": toc_id},
            ).fetchone()
        return row is not None

    def load_skills(self, class_level: int) -> list:
        """Load skill hierarchy for classifier."""
        engine = _engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT id, level, parent_id, name_ru, description,
                           class_level_start, class_level_end
                    FROM knowledge_hierarchy
                    WHERE class_level_start <= :cl AND class_level_end >= :cl
                      AND is_active = TRUE
                    ORDER BY level, sequence_order
                """),
                {"cl": class_level},
            ).fetchall()
        return [
            {
                "id": r[0], "level": r[1], "parent_id": r[2],
                "name_ru": r[3], "description": r[4],
                "origin": None,
            }
            for r in rows
        ]
