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

revision = "b4c5d6e7f8a9"
down_revision = "exam_support_nullable_skillid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("tasks_master", "solution_steps")
    op.drop_column("tasks_master", "hints")
    op.drop_column("tasks_master", "common_mistakes")


def downgrade() -> None:
    op.execute("ALTER TABLE tasks_master ADD COLUMN solution_steps JSONB DEFAULT '[]'")
    op.execute("ALTER TABLE tasks_master ADD COLUMN hints JSONB DEFAULT '[]'")
    op.execute("ALTER TABLE tasks_master ADD COLUMN common_mistakes JSONB DEFAULT '[]'")
