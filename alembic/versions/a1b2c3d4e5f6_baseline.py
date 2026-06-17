"""Baseline schema — all 6 content-service tables

This migration captures the full schema as it existed before Alembic was
introduced.  On a fresh database, ``alembic upgrade head`` creates all
tables.  On an existing production database run::

    alembic stamp head

to mark this revision as already applied without executing the SQL.

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-05-27 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. knowledge_hierarchy ─────────────────────────────────────────────
    # Must be created before tasks_master (tasks reference skills via skill_id)
    # and before skill_prerequisites.
    op.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_hierarchy (
            id                   TEXT PRIMARY KEY,
            level                TEXT NOT NULL CHECK (level IN ('L1', 'L2', 'L3', 'L4')),
            parent_id            TEXT REFERENCES knowledge_hierarchy(id),
            name_ru              TEXT NOT NULL,
            description          TEXT,
            class_level_start    INTEGER NOT NULL DEFAULT 5,
            class_level_end      INTEGER NOT NULL DEFAULT 11,
            sequence_order       INTEGER DEFAULT 0,
            importance           INTEGER DEFAULT 5 CHECK (importance BETWEEN 1 AND 10),
            cognitive_type       TEXT,
            example_task         TEXT,
            assessed_ability     TEXT,
            difficulty_level     TEXT,
            formula              TEXT,
            origin               TEXT DEFAULT 'manual',
            is_advanced          BOOLEAN DEFAULT FALSE,
            is_active            BOOLEAN DEFAULT TRUE,
            created_at           TIMESTAMPTZ DEFAULT NOW(),
            updated_at           TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_kh_level_active
            ON knowledge_hierarchy (level, is_active)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_kh_class_range
            ON knowledge_hierarchy (class_level_start, class_level_end)
    """)

    # ── 2. skill_prerequisites ─────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS skill_prerequisites (
            skill_id                  TEXT NOT NULL REFERENCES knowledge_hierarchy(id),
            prerequisite_id           TEXT NOT NULL REFERENCES knowledge_hierarchy(id),
            dependency_type           TEXT DEFAULT 'required',
            criticality               INTEGER DEFAULT 3 CHECK (criticality BETWEEN 1 AND 5),
            weight                    FLOAT DEFAULT 1.0,
            relationship_description  TEXT,
            confidence                FLOAT DEFAULT 0.85,
            discovery_source          TEXT DEFAULT 'manual',
            created_at                TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (skill_id, prerequisite_id)
        )
    """)

    # ── 3. textbooks ──────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS textbooks (
            textbook_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title                   TEXT NOT NULL,
            authors                 JSONB DEFAULT '[]',
            class_level             INTEGER NOT NULL,
            subtitle                TEXT,
            publisher               TEXT,
            isbn                    TEXT,
            edition                 TEXT,
            total_pages             INTEGER,
            cover_image_url         TEXT,
            subject                 TEXT DEFAULT 'math',
            country                 TEXT DEFAULT 'KZ',
            language                TEXT DEFAULT 'ru',
            digitization_status     TEXT DEFAULT 'pending'
                                        CHECK (digitization_status IN
                                            ('pending', 'ocr_done', 'extracting',
                                             'extracted', 'failed', 'complete')),
            digitization_progress   FLOAT DEFAULT 0.0,
            tasks_extracted         INTEGER DEFAULT 0,
            is_active               BOOLEAN DEFAULT TRUE,
            ocr_text                TEXT,
            ocr_completed_at        TIMESTAMPTZ,
            created_at              TIMESTAMPTZ DEFAULT NOW(),
            updated_at              TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_textbooks_subject_level
            ON textbooks (subject, class_level) WHERE is_active = TRUE
    """)

    # ── 4. textbook_toc ────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS textbook_toc (
            id           SERIAL PRIMARY KEY,
            textbook_id  UUID NOT NULL REFERENCES textbooks(textbook_id) ON DELETE CASCADE,
            level        INTEGER NOT NULL DEFAULT 2,
            number       TEXT,
            title        TEXT NOT NULL,
            page_start   INTEGER,
            page_end     INTEGER,
            sort_order   INTEGER DEFAULT 0,
            parent_id    INTEGER REFERENCES textbook_toc(id)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_toc_textbook
            ON textbook_toc (textbook_id, sort_order)
    """)

    # ── 5. tasks_master ────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS tasks_master (
            id                   VARCHAR(60) PRIMARY KEY,
            skill_id             TEXT REFERENCES knowledge_hierarchy(id),
            question_text        TEXT NOT NULL,
            question_latex       TEXT DEFAULT '',
            correct_answer       TEXT NOT NULL,
            answer_type          TEXT NOT NULL
                                     CHECK (answer_type IN (
                                         'exact_number', 'expression', 'multiple_choice',
                                         'text', 'fraction', 'equation_solution', 'set',
                                         'coordinate', 'inequality', 'decimal',
                                         'open_text', 'multiple_values'
                                     )),
            difficulty           TEXT NOT NULL CHECK (difficulty IN ('A', 'B', 'C')),
            cognitive_load       TEXT NOT NULL
                                     CHECK (cognitive_load IN ('recall', 'apply', 'analyze')),
            irt_discrimination   FLOAT DEFAULT 1.0,
            irt_difficulty       FLOAT DEFAULT 0.5,
            irt_guessing         FLOAT DEFAULT 0.2,
            solution_steps       JSONB DEFAULT '[]',
            hints                JSONB DEFAULT '[]',
            common_mistakes      JSONB DEFAULT '[]',
            distractor_meta      JSONB DEFAULT '[]',
            answer_options       JSONB DEFAULT '[]',
            toc_id               INTEGER REFERENCES textbook_toc(id),
            tags                 JSONB DEFAULT '{}',
            verification_status  TEXT DEFAULT 'pending'
                                     CHECK (verification_status IN
                                         ('pending', 'verified', 'rejected')),
            source_type          TEXT DEFAULT 'textbook',
            source_reference     TEXT,
            is_active            BOOLEAN DEFAULT TRUE,
            created_at           TIMESTAMPTZ DEFAULT NOW(),
            updated_at           TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tasks_skill
            ON tasks_master (skill_id) WHERE is_active = TRUE
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tasks_difficulty
            ON tasks_master (difficulty, answer_type) WHERE is_active = TRUE
    """)

    # ── 6. textbook_tasks (bridge) ─────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS textbook_tasks (
            textbook_id        UUID NOT NULL REFERENCES textbooks(textbook_id) ON DELETE CASCADE,
            task_id            VARCHAR(60) NOT NULL REFERENCES tasks_master(id),
            paragraph_number   TEXT,
            exercise_number    TEXT,
            PRIMARY KEY (textbook_id, task_id)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tt_textbook
            ON textbook_tasks (textbook_id)
    """)

    # ── 7. textbook_skill_map ──────────────────────────────────────────────
    # Maps TOC sections to skills — used by pipeline to link chapters to
    # the knowledge graph. Exists in live DB but was missing from baseline.
    op.execute("""
        CREATE TABLE IF NOT EXISTS textbook_skill_map (
            id          SERIAL PRIMARY KEY,
            toc_id      INTEGER NOT NULL REFERENCES textbook_toc(id) ON DELETE CASCADE,
            skill_id    VARCHAR(60) NOT NULL REFERENCES knowledge_hierarchy(id),
            role        VARCHAR(30) DEFAULT 'primary',
            confidence  NUMERIC(5, 4) DEFAULT 1.0,
            is_main     BOOLEAN DEFAULT TRUE
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tsm_toc
            ON textbook_skill_map (toc_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tsm_skill
            ON textbook_skill_map (skill_id)
    """)


def downgrade() -> None:
    # Drop in reverse dependency order
    op.execute("DROP TABLE IF EXISTS textbook_skill_map")
    op.execute("DROP TABLE IF EXISTS textbook_tasks")
    op.execute("DROP TABLE IF EXISTS tasks_master")
    op.execute("DROP TABLE IF EXISTS textbook_toc")
    op.execute("DROP TABLE IF EXISTS textbooks")
    op.execute("DROP TABLE IF EXISTS skill_prerequisites")
    op.execute("DROP TABLE IF EXISTS knowledge_hierarchy")
