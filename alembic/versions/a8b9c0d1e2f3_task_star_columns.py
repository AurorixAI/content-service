"""Explicit is_star + task_category columns on tasks_master

Раньше эти поля лежали только в tags JSONB, что мешало индексам и фильтрации.
Теперь это первоклассные колонки + индексы.

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-05-28
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "a8b9c0d1e2f3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    # Parts of this change were applied to the deployed databases by hand,
    # without stamping Alembic, so the columns can already be there while the
    # revision still counts as pending. Converge instead of aborting.
    existing = _columns("tasks_master")
    if "is_star" not in existing:
        op.add_column(
            "tasks_master",
            sa.Column("is_star", sa.Boolean(), nullable=False, server_default="false"),
        )
    if "task_category" not in existing:
        op.add_column(
            "tasks_master",
            sa.Column("task_category", sa.String(20), nullable=False, server_default="standard"),
        )
    # Backfill из JSONB
    op.execute("""
        UPDATE tasks_master
        SET is_star = COALESCE((tags->>'star')::boolean, FALSE)
        WHERE tags ? 'star'
    """)
    op.execute("""
        UPDATE tasks_master
        SET task_category = COALESCE(tags->>'category', 'standard')
        WHERE tags ? 'category'
    """)
    present = _indexes("tasks_master")
    if "ix_tasks_master_is_star" not in present:
        op.create_index(
            "ix_tasks_master_is_star", "tasks_master", ["is_star"],
            postgresql_where=sa.text("is_star = TRUE"),
        )
    if "ix_tasks_master_task_category" not in present:
        op.create_index("ix_tasks_master_task_category", "tasks_master", ["task_category"])


def downgrade() -> None:
    op.drop_index("ix_tasks_master_task_category", table_name="tasks_master")
    op.drop_index("ix_tasks_master_is_star", table_name="tasks_master")
    op.drop_column("tasks_master", "task_category")
    op.drop_column("tasks_master", "is_star")
