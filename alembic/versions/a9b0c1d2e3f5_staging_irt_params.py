"""tasks_staging: параметры IRT (B39)

Промоушен не писал в `tasks_master` ни `irt_difficulty`, ни
`irt_discrimination`, ни `irt_guessing` — и не мог: таких колонок не было
в `tasks_staging`, то есть значение не терялось на записи, оно **не доезжало
до staging вообще**. Всё уезжало на дефолт схемы (`irt_difficulty` 0.0,
`irt_guessing` 0.0), а значит у каждой задачи банка выходила одинаковая
сложность и нулевое угадывание для `multiple_choice`.

Бьёт это не по content-service, а по CAT/IRT в diagnostics-service: подбор
задачи под theta перестаёт различать задачи, алгоритм формально работает и
выдаёт бессмысленный выбор.

Старый путь записи (`db_writer`) параметры считал — регрессия ровно нового шва.
Формула теперь одна на оба пути: `schema_vocab.irt_params`.

Типы взяты у `tasks_master` из выгрузки прода (`NUMERIC(6,4)`), чтобы значение
не меняло представление при переносе из карантина в банк.

Revision ID: a9b0c1d2e3f5
Revises: e7f8a9b0c1d2
"""

from alembic import op

revision = "a9b0c1d2e3f5"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


_COLUMNS = (
    ("irt_discrimination", "NUMERIC(6,4)", "1.0"),
    ("irt_difficulty", "NUMERIC(6,4)", "0.0"),
    ("irt_guessing", "NUMERIC(6,4)", "0.0"),
)


def upgrade() -> None:
    # IF NOT EXISTS: колонки могли быть заведены руками на стенде — миграция
    # обязана быть безопасной и там (та же логика, что в B10/c5d6e7f8a9b0).
    for name, sql_type, default in _COLUMNS:
        op.execute(
            f"ALTER TABLE tasks_staging "
            f"ADD COLUMN IF NOT EXISTS {name} {sql_type} DEFAULT {default}"
        )


def downgrade() -> None:
    # Откат схемы уносит только то, что эта ревизия завела: колонки в
    # карантинной таблице. `tasks_master` не трогаем — там эти колонки из
    # baseline, и их удаление увезло бы прод-содержимое.
    for name, _sql_type, _default in _COLUMNS:
        op.execute(f"ALTER TABLE tasks_staging DROP COLUMN IF EXISTS {name}")
