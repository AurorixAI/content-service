"""tasks_staging + провенанс + B10 (correct_answer_latex)

Три вещи, которые нужно делать одной миграцией, потому что они об одном:
где заканчивается конвейер и начинаются данные, на которых учатся ученики.

1. **B10.** `correct_answer_latex` читают 9 модулей, включая
   `src/api/content_router.py`, но ни одна миграция её не создавала: в проде
   колонка заведена вручную, вне Alembic. На чистой БД `alembic upgrade head`
   давал схему, на которой API падает — проверено 2026-08-28 на пустом
   PostgreSQL. Здесь схема приводится в соответствие с продом. `IF NOT EXISTS`
   делает шаг безопасным и для прода, где колонка уже есть.

2. **Провенанс (И1).** Источник и уверенность становятся колонками, а не
   договорённостью. Значения по умолчанию выбраны так, чтобы уже накопленные
   3 796 задач G8 не соврали о себе: `answer_source='unknown'` честно говорит
   «эти данные записаны до введения провенанса», а не приписывает им книжный
   источник задним числом.

3. **`tasks_staging` (И3).** Конвейер пишет сюда, а не в `tasks_master`.
   В `tasks_master` переносит отдельный шаг промоушена (`scripts/promote.py`),
   и только то, что прошло гейты. Не прошло — остаётся здесь с флагами и ждёт
   человека. Правило §0.7 («не трогай прод-данные вслепую») перестаёт быть
   дисциплиной и становится свойством схемы.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
"""
from alembic import op

revision = "c5d6e7f8a9b0"
down_revision = "h9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. B10 — привести схему в соответствие с продом ────────────────────
    op.execute("ALTER TABLE tasks_master ADD COLUMN IF NOT EXISTS correct_answer_latex TEXT")

    # ── 2. Провенанс на tasks_master ──────────────────────────────────────
    # 'unknown' — не источник, а признание: записано до введения провенанса.
    # Отличать его от 'absent' важно: absent = «искали, не нашли».
    #
    # То же и для text_source. Сначала здесь стояло DEFAULT 'book_ocr', и на
    # выгрузке прода (2026-09-01) это проставило «текст из распознавания книги»
    # всем 35 202 задачам — включая 2 023 с source_type='ai_generated', текст
    # которых книгой не подтверждён вовсе. Дефолт, приписывающий происхождение,
    # которого не проверяли, — ровно та ложь, против которой заведён инвариант.
    op.execute("""
        ALTER TABLE tasks_master
            ADD COLUMN IF NOT EXISTS answer_source      TEXT NOT NULL DEFAULT 'unknown',
            ADD COLUMN IF NOT EXISTS text_source        TEXT NOT NULL DEFAULT 'unknown',
            ADD COLUMN IF NOT EXISTS answer_source_page INTEGER,
            ADD COLUMN IF NOT EXISTS confidence         JSONB DEFAULT '{}'::jsonb
    """)
    op.execute("""
        ALTER TABLE tasks_master
            DROP CONSTRAINT IF EXISTS tasks_master_answer_source_check
    """)
    op.execute("""
        ALTER TABLE tasks_master
            ADD CONSTRAINT tasks_master_answer_source_check
            CHECK (answer_source IN (
                'book_key', 'book_solution', 'sympy_derived',
                'ai_solved', 'absent', 'unknown'
            ))
    """)
    op.execute("""
        ALTER TABLE tasks_master
            DROP CONSTRAINT IF EXISTS tasks_master_text_source_check
    """)
    op.execute("""
        ALTER TABLE tasks_master
            ADD CONSTRAINT tasks_master_text_source_check
            CHECK (text_source IN ('book_ocr', 'ai_repaired', 'unknown'))
    """)
    # Частичный индекс: «покажи всё, что придумала модель» — самый частый
    # вопрос к банку после введения провенанса.
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tasks_answer_source
            ON tasks_master (answer_source) WHERE is_active = TRUE
    """)

    # ── 3. tasks_staging ──────────────────────────────────────────────────
    # Схема намеренно ПЕРМИССИВНЕЕ tasks_master: staging обязан принять и то,
    # что не прошло проверку, — иначе брак некуда положить и он либо потеряется,
    # либо просочится. Ограничения (skill_id NOT NULL, L4-инвариант, CHECK по
    # answer_type) остаются на tasks_master и проверяются при промоушене.
    op.execute("""
        CREATE TABLE IF NOT EXISTS tasks_staging (
            staging_id          BIGSERIAL PRIMARY KEY,
            task_id             VARCHAR(60) NOT NULL,
            textbook_id         UUID REFERENCES textbooks(textbook_id) ON DELETE CASCADE,
            class_level         INTEGER,

            skill_id            TEXT,
            toc_id              INTEGER,
            paragraph_number    TEXT,
            exercise_number     TEXT,
            page                INTEGER,

            question_text       TEXT,
            question_latex      TEXT DEFAULT '',
            correct_answer      TEXT,
            correct_answer_latex TEXT,
            answer_type         TEXT,
            answer_options      JSONB DEFAULT '[]',
            distractor_meta     JSONB DEFAULT '[]',
            difficulty          TEXT,
            cognitive_load      TEXT,
            is_star             BOOLEAN DEFAULT FALSE,
            task_category       TEXT DEFAULT 'standard',
            tags                JSONB DEFAULT '{}',

            -- Провенанс (И1)
            answer_source       TEXT NOT NULL DEFAULT 'absent',
            text_source         TEXT NOT NULL DEFAULT 'book_ocr',
            answer_source_page  INTEGER,
            confidence          JSONB DEFAULT '{}',

            -- Вердикт гейтов (И3): почему задача здесь и куда ей дальше
            gate_status         TEXT NOT NULL DEFAULT 'review'
                                    CHECK (gate_status IN ('pass', 'review', 'reject')),
            gate_reasons        JSONB DEFAULT '[]',
            formulas_checked    INTEGER DEFAULT 0,
            formulas_broken     INTEGER DEFAULT 0,
            compile_measured    BOOLEAN DEFAULT FALSE,

            -- Бухгалтерия промоушена
            promoted_at         TIMESTAMPTZ,
            promoted_to         VARCHAR(60),
            run_id              TEXT,
            stage_hash          TEXT,

            created_at          TIMESTAMPTZ DEFAULT NOW(),
            updated_at          TIMESTAMPTZ DEFAULT NOW(),

            UNIQUE (textbook_id, task_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_staging_gate
            ON tasks_staging (gate_status) WHERE promoted_at IS NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_staging_run
            ON tasks_staging (run_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_staging_textbook
            ON tasks_staging (textbook_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tasks_staging")
    op.execute("DROP INDEX IF EXISTS idx_tasks_answer_source")
    op.execute("ALTER TABLE tasks_master DROP CONSTRAINT IF EXISTS tasks_master_answer_source_check")
    op.execute("""
        ALTER TABLE tasks_master
            DROP COLUMN IF EXISTS answer_source,
            DROP COLUMN IF EXISTS text_source,
            DROP COLUMN IF EXISTS answer_source_page,
            DROP COLUMN IF EXISTS confidence
    """)
    # correct_answer_latex НЕ удаляется: в проде она заведена вне миграций и
    # содержит данные. Откат схемы не должен уносить прод-содержимое.
