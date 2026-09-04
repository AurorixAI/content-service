"""prod schema catch-up: догнать схему, до которой прод дошёл мимо репозитория

Revision ID: f8a9b0c1d2e3
Revises: b4c5d6e7f8a9
Create Date: 2026-09-02

Зачем эта миграция существует.

Выгрузка прода (2026-09-01) показала `alembic_version = 'h9b0c1d2e3f4'` —
ревизии, которой нет ни в одной ветке репозитория (`main`, `develop`, `CEO`,
`temur`: у всех голова `b4c5d6e7f8a9`). По датам в самих данных работа шла
5–14 августа 2026, через три недели после последнего коммита: 13 августа за
один день изменено 22 994 задачи, добавлены `latex_status`,
`latex_normalized_at`, `answer_options_latex`, и 32 893 задачи помечены
`verified`. Файлы миграций при этом в git не попали.

Следствие проверено фактом: `alembic current` на копии прода падает с
«Can't locate revision identified by 'h9b0c1d2e3f4'», то есть и
`alembic upgrade head` упадёт — а он стоит в автодеплое на push в `main`.

Расхождение оказалось шире августовских колонок. Сверка чистой базы (цепочка
репозитория до `b4c5d6e7f8a9`) с продом: **18 колонок отсутствуют, у 51 из 102
общих колонок расходится тип, nullability или значение по умолчанию**. То есть
базовая миграция в репозитории никогда не была реальной прод-схемой. Из
семантически значимого: `tasks_master.irt_difficulty` по умолчанию `0.5` в
репозитории против `0.0` в проде — это параметр сложности, по которому работает
CAT; `skill_prerequisites.criticality` ограничен 1–5 против 1–10, и все 588
настоящих связей имеют 6–10, то есть в схему репозитория они не грузятся вовсе.

Спецификация ниже **выведена из дампа**, а не написана по памяти: снимок
`information_schema` прода сравнён со снимком чистой базы, разница выписана
машинно.

Каждое изменение применяется только если фактическое состояние отличается.
На проде это делает миграцию набором no-op (там уже всё так) и не вызывает
переписывания таблиц на 35 202 строках; на чистой базе — выравнивает схему.

Что миграция намеренно НЕ делает:
* не удаляет `knowledge_hierarchy.is_advanced`/`origin` и
  `skill_prerequisites.confidence` — они есть в репозитории и нет в проде.
  Удаление колонки необратимо уносит данные, а вреда от лишней колонки нет;
* не трогает данные — только схему.

**Разовое действие на проде.** Эта миграция не может быть применена, пока
`alembic_version` называет неизвестную ревизию. Перед деплоем нужно один раз
выполнить (это решение человека, а не автоматики):

    UPDATE alembic_version SET version_num = 'f8a9b0c1d2e3';

Это допустимо ровно потому, что схема прода уже соответствует целевой: миграция
на нём — no-op, и штамп лишь возвращает журнал в согласие с фактом.
"""
from alembic import op
import sqlalchemy as sa

revision = "f8a9b0c1d2e3"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


#: (таблица, колонка, тип, nullable, default) — снято с прода машинно.
_SPEC: list[tuple[str, str, str, bool, str | None]] = [
    ('knowledge_hierarchy', 'class_level_end', 'INTEGER', True, None),  # align
    ('knowledge_hierarchy', 'class_level_start', 'INTEGER', True, None),  # align
    ('knowledge_hierarchy', 'cognitive_type', 'VARCHAR(20)', True, None),  # align
    ('knowledge_hierarchy', 'created_at', 'TIMESTAMP', True, 'now()'),  # align
    ('knowledge_hierarchy', 'difficulty_level', 'VARCHAR(50)', True, None),  # align
    ('knowledge_hierarchy', 'id', 'VARCHAR(30)', False, None),  # align
    ('knowledge_hierarchy', 'level', 'VARCHAR(2)', False, None),  # align
    ('knowledge_hierarchy', 'name', 'VARCHAR(200)', False, "''::character varying"),  # add
    ('knowledge_hierarchy', 'name_ru', 'VARCHAR(200)', False, None),  # align
    ('knowledge_hierarchy', 'parent_id', 'VARCHAR(30)', True, None),  # align
    ('knowledge_hierarchy', 'updated_at', 'TIMESTAMP', True, 'now()'),  # align
    ('skill_prerequisites', 'created_at', 'TIMESTAMP', True, 'now()'),  # align
    ('skill_prerequisites', 'criticality', 'INTEGER', True, '5'),  # align
    ('skill_prerequisites', 'dependency_type', 'VARCHAR(10)', False, "'hard'::character varying"),  # align
    ('skill_prerequisites', 'discovery_source', 'VARCHAR(20)', True, "'expert'::character varying"),  # align
    ('skill_prerequisites', 'id', 'INTEGER', False, None),  # add
    ('skill_prerequisites', 'is_cross_grade', 'BOOLEAN', True, 'false'),  # add
    ('skill_prerequisites', 'last_validated_at', 'TIMESTAMP', True, 'now()'),  # add
    ('skill_prerequisites', 'prerequisite_id', 'VARCHAR(30)', False, None),  # align
    ('skill_prerequisites', 'skill_id', 'VARCHAR(30)', False, None),  # align
    ('skill_prerequisites', 'weight', 'NUMERIC(4,2)', True, '1.0'),  # align
    ('tasks_master', 'answer_options', 'JSONB', True, None),  # align
    ('tasks_master', 'answer_options_latex', 'JSONB', True, None),  # add
    ('tasks_master', 'answer_type', 'VARCHAR(20)', False, "'exact_number'::character varying"),  # align
    ('tasks_master', 'cognitive_load', 'VARCHAR(20)', True, "'apply'::character varying"),  # align
    ('tasks_master', 'correct_answer_latex', 'TEXT', True, None),  # add
    ('tasks_master', 'created_at', 'TIMESTAMP', True, 'now()'),  # align
    ('tasks_master', 'difficulty', 'VARCHAR(1)', False, "'B'::character varying"),  # align
    ('tasks_master', 'distractor_meta', 'JSONB', True, None),  # align
    ('tasks_master', 'irt_difficulty', 'NUMERIC(6,4)', True, '0.0'),  # align
    ('tasks_master', 'irt_discrimination', 'NUMERIC(6,4)', True, '1.0'),  # align
    ('tasks_master', 'irt_guessing', 'NUMERIC(6,4)', True, '0.0'),  # align
    ('tasks_master', 'latex_normalized_at', 'TIMESTAMPTZ', True, None),  # add
    ('tasks_master', 'latex_status', 'VARCHAR(32)', True, None),  # add
    ('tasks_master', 'question_image_url', 'TEXT', True, None),  # add
    ('tasks_master', 'question_latex', 'TEXT', True, None),  # align
    ('tasks_master', 'skill_id', 'VARCHAR(30)', True, None),  # align
    ('tasks_master', 'source_type', 'VARCHAR(20)', True, "'textbook'::character varying"),  # align
    ('tasks_master', 'sympy_solution', 'TEXT', True, None),  # add
    ('tasks_master', 'updated_at', 'TIMESTAMP', True, 'now()'),  # align
    ('tasks_master', 'verification_status', 'VARCHAR(20)', True, "'pending'::character varying"),  # align
    ('textbook_skill_map', 'confidence', 'NUMERIC(4,2)', True, '1.0'),  # align
    ('textbook_skill_map', 'role', 'VARCHAR(20)', True, "'primary'::character varying"),  # align
    ('textbook_skill_map', 'skill_id', 'VARCHAR(30)', False, None),  # align
    ('textbook_tasks', 'exercise_number', 'VARCHAR(20)', True, None),  # align
    ('textbook_tasks', 'id', 'INTEGER', False, None),  # add
    ('textbook_tasks', 'page_number', 'INTEGER', True, None),  # add
    ('textbook_tasks', 'paragraph_number', 'VARCHAR(30)', True, None),  # align
    ('textbook_toc', 'display_name', 'VARCHAR(500)', True, None),  # add
    ('textbook_toc', 'display_number', 'VARCHAR(30)', True, None),  # add
    ('textbook_toc', 'level', 'INTEGER', False, None),  # align
    ('textbook_toc', 'mapped_skill_id', 'VARCHAR(30)', True, None),  # add
    ('textbook_toc', 'mapped_topic_id', 'VARCHAR(30)', True, None),  # add
    ('textbook_toc', 'mapping_confidence', 'NUMERIC(4,2)', True, '0'),  # add
    ('textbook_toc', 'number', 'VARCHAR(255)', True, None),  # align
    ('textbook_toc', 'title', 'VARCHAR(500)', False, None),  # align
    ('textbooks', 'authors', 'TEXT[]', True, "'{}'::text[]"),  # align
    ('textbooks', 'country', 'VARCHAR(10)', True, "'UZ'::character varying"),  # align
    ('textbooks', 'created_at', 'TIMESTAMP', True, 'now()'),  # align
    ('textbooks', 'digitization_progress', 'NUMERIC(5,2)', True, '0'),  # align
    ('textbooks', 'digitization_status', 'VARCHAR(20)', True, "'pending'::character varying"),  # align
    ('textbooks', 'display_name', 'VARCHAR(400)', True, None),  # add
    ('textbooks', 'edition', 'VARCHAR(50)', True, None),  # align
    ('textbooks', 'isbn', 'VARCHAR(30)', True, None),  # align
    ('textbooks', 'language', 'VARCHAR(10)', True, "'ru'::character varying"),  # align
    ('textbooks', 'ocr_completed_at', 'TIMESTAMP', True, None),  # align
    ('textbooks', 'publisher', 'VARCHAR(200)', True, None),  # align
    ('textbooks', 'subject', 'VARCHAR(50)', True, "'math'::character varying"),  # align
    ('textbooks', 'subtitle', 'VARCHAR(300)', True, None),  # align
    ('textbooks', 'title', 'VARCHAR(300)', False, None),  # align
    ('textbooks', 'updated_at', 'TIMESTAMP', True, 'now()'),  # align
]


def _actual(conn, table: str, column: str):
    return conn.execute(
        sa.text("""
            SELECT data_type, character_maximum_length, numeric_precision,
                   numeric_scale, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :t AND column_name = :c
        """),
        {"t": table, "c": column},
    ).mappings().first()


def _render_type(row) -> str:
    dt = row["data_type"]
    if dt == "character varying":
        n = row["character_maximum_length"]
        return f"VARCHAR({n})" if n else "VARCHAR"
    if dt == "ARRAY":
        return "TEXT[]"
    if dt == "numeric" and row["numeric_precision"]:
        return f"NUMERIC({row['numeric_precision']},{row['numeric_scale']})"
    return {
        "timestamp without time zone": "TIMESTAMP",
        "timestamp with time zone": "TIMESTAMPTZ",
        "double precision": "DOUBLE PRECISION",
    }.get(dt, dt.upper())


#: Преобразования, которые не выражаются простым `column::type`.
#: `textbooks.authors` в репозитории `jsonb`, в проде `text[]` — ещё одно
#: следствие расхождения: код, читающий это поле, ведёт себя по-разному.
#: Postgres не допускает подзапрос в выражении `USING`, поэтому разворачивание
#: массива живёт во временной функции — она заводится перед выравниванием типов
#: и удаляется сразу после.
_JSONB_TO_TEXT_ARRAY = """
CREATE OR REPLACE FUNCTION _catchup_jsonb_to_text_array(j JSONB)
RETURNS TEXT[] AS $$
    SELECT CASE
        WHEN j IS NULL THEN NULL
        WHEN jsonb_typeof(j) <> 'array' THEN ARRAY[]::TEXT[]
        ELSE ARRAY(SELECT jsonb_array_elements_text(j))
    END
$$ LANGUAGE sql IMMUTABLE
"""

_USING: dict[tuple[str, str], str] = {
    ("textbooks", "authors"): "_catchup_jsonb_to_text_array(authors)",
}


def _dependent_triggers(conn, tables: set[str]) -> list[tuple[str, str]]:
    """(таблица, DDL) пользовательских триггеров на затронутых таблицах.

    Postgres запрещает менять тип колонки, от которой зависит триггер:
    `trg_tasks_master_skill_l4` (инвариант «навык обязан быть уровня L4»)
    держит `tasks_master.skill_id`. Определения снимаются из самой базы
    (`pg_get_triggerdef`), а не переписываются здесь по памяти — иначе
    восстановленный триггер мог бы отличаться от снятого.
    """
    rows = conn.execute(
        sa.text("""
            SELECT c.relname AS table_name, pg_get_triggerdef(t.oid) AS ddl,
                   t.tgname AS name
            FROM pg_trigger t
            JOIN pg_class c ON c.oid = t.tgrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE NOT t.tgisinternal AND n.nspname = 'public'
              AND c.relname = ANY(:tables)
        """),
        {"tables": sorted(tables)},
    ).mappings().all()
    return [(r["table_name"], r["name"], r["ddl"]) for r in rows]


def upgrade() -> None:
    conn = op.get_bind()

    # ── review_queue: таблица есть в проде и нет в репозитории ─────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS review_queue (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            item_type     VARCHAR(64)  NOT NULL,
            item_id       VARCHAR(128) NOT NULL,
            review_reason VARCHAR(255) NOT NULL,
            priority      VARCHAR(32)  DEFAULT 'medium',
            status        VARCHAR(32)  DEFAULT 'pending',
            ai_suggestion JSONB,
            created_at    TIMESTAMPTZ  DEFAULT now()
        )
    """)

    op.execute(_JSONB_TO_TEXT_ARRAY)

    touched = {t for t, *_ in _SPEC}
    saved = _dependent_triggers(conn, touched)
    for table, name, _ddl in saved:
        op.execute(f"DROP TRIGGER IF EXISTS {name} ON {table}")

    for table, column, type_, nullable, default in _SPEC:
        row = _actual(conn, table, column)

        if row is None:
            d = f" DEFAULT {default}" if default else ""
            op.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {type_}{d}"
            )
            if not nullable:
                op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL")
            continue

        # Тип: приводим только при фактическом расхождении — иначе Postgres
        # перепишет таблицу целиком без всякой нужды.
        if _render_type(row) != type_:
            # Значение по умолчанию сначала снимается: Postgres отказывается
            # менять тип, если старый default не приводится к новому автоматом
            # (`'{}'::jsonb` → `text[]`). Нужный default выставится ниже.
            if row["column_default"]:
                op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
            op.execute(
                f"ALTER TABLE {table} ALTER COLUMN {column} "
                f"TYPE {type_} USING {_USING.get((table, column), f'{column}::{type_}')}"
            )

        is_nullable = row["is_nullable"] == "YES"
        if is_nullable != nullable:
            verb = "DROP NOT NULL" if nullable else "SET NOT NULL"
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} {verb}")

        actual_default = None if _render_type(row) != type_ else row["column_default"]
        if (actual_default or "") != (default or ""):
            if default is None:
                op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
            else:
                op.execute(
                    f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT {default}"
                )

    for _table, _name, ddl in saved:
        op.execute(ddl)

    op.execute("DROP FUNCTION IF EXISTS _catchup_jsonb_to_text_array(JSONB)")

    # ── последовательности и ключи для суррогатных id ─────────────────────
    # В проде `skill_prerequisites` и `textbook_tasks` имеют серийный `id` как
    # первичный ключ, а прежняя пара колонок вынесена в UNIQUE. В схеме
    # репозитория первичным ключом была сама пара. Разница видна снаружи:
    # запись с одинаковой парой в проде отвергается уникальным ограничением,
    # а не первичным ключом, и на неё можно сослаться по числовому id.
    for table, column in (("skill_prerequisites", "id"), ("textbook_tasks", "id")):
        seq = f"{table}_{column}_seq"
        op.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq} OWNED BY {table}.{column}")
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} "
            f"SET DEFAULT nextval('{seq}'::regclass)"
        )
        op.execute(
            f"UPDATE {table} SET {column} = nextval('{seq}'::regclass) "
            f"WHERE {column} IS NULL"
        )
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL")
        op.execute(
            f"SELECT setval('{seq}', "
            f"COALESCE((SELECT MAX({column}) FROM {table}), 0) + 1, false)"
        )

    # Перекладывание первичного ключа делается только если он ещё на паре
    # колонок. На проде ключ уже на `id`, а уникальное ограничение на паре
    # заведено — там весь блок обязан быть no-op, иначе миграция падает на
    # «constraint already exists» (проверено фактом на копии дампа).
    pk_on_pair = conn.execute(
        sa.text("""
            SELECT COUNT(*) FROM pg_index i
            JOIN pg_class c ON c.oid = i.indrelid
            WHERE c.relname = 'skill_prerequisites' AND i.indisprimary
              AND array_length(i.indkey::int2[], 1) > 1
        """)
    ).scalar()
    if pk_on_pair:
        op.execute("ALTER TABLE skill_prerequisites DROP CONSTRAINT skill_prerequisites_pkey")
        op.execute("""
            ALTER TABLE skill_prerequisites
                ADD CONSTRAINT skill_prerequisites_skill_id_prerequisite_id_key
                UNIQUE (skill_id, prerequisite_id)
        """)
        op.execute("ALTER TABLE skill_prerequisites ADD PRIMARY KEY (id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sp_skill ON skill_prerequisites (skill_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sp_prereq ON skill_prerequisites (prerequisite_id)")
    op.execute("""
        ALTER TABLE skill_prerequisites
            DROP CONSTRAINT IF EXISTS skill_prerequisites_check
    """)
    op.execute("""
        ALTER TABLE skill_prerequisites
            ADD CONSTRAINT skill_prerequisites_check
            CHECK (skill_id <> prerequisite_id)
    """)

    # ── колонки, которые нужны коду, но которых в проде нет ───────────────
    # Выравнивание выше ведёт чистую базу к состоянию прода. Но расхождение
    # двустороннее, и одна колонка нужна в обратную сторону:
    # `curriculum_setup.py` пишет `skill_prerequisites.confidence`, которая
    # есть в цепочке репозитория и отсутствует в проде. Локально код работает,
    # на проде падает с «column confidence does not exist» — проверено
    # выполнением на копии дампа. Добавляем, а не убираем из кода: колонку
    # завели осознанно, и она несёт уверенность связи.
    #
    # `knowledge_hierarchy.is_advanced` и `origin` тоже есть только в
    # репозитории, но их не читает и не пишет никто — оставлены как есть.
    op.execute("""
        ALTER TABLE skill_prerequisites
            ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION DEFAULT 0.85
    """)

    # ── ограничения, разошедшиеся по значениям ────────────────────────────
    # В проде criticality 1–10, и все 588 настоящих связей имеют 6–10.
    # Ограничение 1–5 из репозитория не пропускает реальные данные вовсе.
    op.execute("""
        ALTER TABLE skill_prerequisites
            DROP CONSTRAINT IF EXISTS skill_prerequisites_criticality_check
    """)
    op.execute("""
        ALTER TABLE skill_prerequisites
            ADD CONSTRAINT skill_prerequisites_criticality_check
            CHECK (criticality >= 1 AND criticality <= 10)
    """)


def downgrade() -> None:
    # Откат намеренно пустой: эта миграция не вводит новое состояние, а
    # догоняет то, в котором прод уже находится. «Откатить» его означало бы
    # рассинхронизировать репозиторий с продом обратно — и уронить колонки,
    # в которых лежат данные 35 202 задач.
    pass
