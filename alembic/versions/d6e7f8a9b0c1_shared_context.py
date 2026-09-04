"""shared_context: общее условие группы задач

Сессия 4 (структурный слой). «В задачах 140–145 решите уравнение:» напечатано
в учебнике один раз, а относится ко всем задачам диапазона. До этой колонки
условие группы было негде хранить, и записи вида «а) x² − 9 = 0» уезжали в
банк без указания, что с ними делать.

Колонка добавляется в обе таблицы: в `tasks_staging` её пишет конвейер,
в `tasks_master` переносит промоушен. `ADD COLUMN IF NOT EXISTS` — миграция
безопасна и там, где колонку успели завести руками.

`downgrade` колонку НЕ удаляет: откат схемы не должен уносить содержимое
(тот же принцип, что в c5d6e7f8a9b0 для correct_answer_latex).

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
"""

from alembic import op

revision = "d6e7f8a9b0c1"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE tasks_staging ADD COLUMN IF NOT EXISTS shared_context TEXT")
    op.execute("ALTER TABLE tasks_master  ADD COLUMN IF NOT EXISTS shared_context TEXT")


def downgrade() -> None:
    # Намеренно пусто: колонка с содержимым переживает откат схемы.
    pass
