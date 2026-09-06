"""Add an isolated display layer for legacy answer_options.

The raw answer_options JSON remains canonical and untouched. Its parallel
answer_options_latex JSONB column lets realtime diagnostic UI render every
option without inferring or rewriting mathematical meaning on the frontend.

Revision ID: g8a9b0c1d2e3
Revises: b4c5d6e7f8a9
Create Date: 2026-08-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "g8a9b0c1d2e3"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    if "answer_options_latex" not in _columns("tasks_master"):
        op.add_column(
            "tasks_master",
            sa.Column("answer_options_latex", postgresql.JSONB(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("tasks_master", "answer_options_latex")
