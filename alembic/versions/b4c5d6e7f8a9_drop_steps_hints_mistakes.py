"""Drop solution_steps, hints, common_mistakes columns from tasks_master

Эти поля убраны как архитектурное решение: статические шаги решения и подсказки
из БД не несут ценности — их заменит real-time AI-тьютор, персонализированный
под конкретную ошибку ученика. Аналитика ошибок живёт в distractor_meta.

Revision ID: b4c5d6e7f8a9
Revises: a8b9c0d1e2f3
Create Date: 2026-06-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "b4c5d6e7f8a9"
# The migration file that used this temporary revision name was never present
# in the repository. The documented, existing predecessor is a8b9c0d1e2f3.
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    existing = _columns("tasks_master")
    for column in ("solution_steps", "hints", "common_mistakes"):
        if column in existing:
            op.drop_column("tasks_master", column)


def downgrade() -> None:
    op.execute("ALTER TABLE tasks_master ADD COLUMN solution_steps JSONB DEFAULT '[]'")
    op.execute("ALTER TABLE tasks_master ADD COLUMN hints JSONB DEFAULT '[]'")
    op.execute("ALTER TABLE tasks_master ADD COLUMN common_mistakes JSONB DEFAULT '[]'")
