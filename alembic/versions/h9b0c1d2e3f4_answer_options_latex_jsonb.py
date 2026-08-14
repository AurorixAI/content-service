"""Convert answer_options_latex to JSONB.

Revision ID: h9b0c1d2e3f4
Revises: g8a9b0c1d2e3
Create Date: 2026-08-08
"""
from __future__ import annotations

from alembic import op
from sqlalchemy.dialects import postgresql


revision = "h9b0c1d2e3f4"
down_revision = "g8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "tasks_master",
        "answer_options_latex",
        existing_type=postgresql.JSON(),
        type_=postgresql.JSONB(),
        postgresql_using="answer_options_latex::jsonb",
    )


def downgrade() -> None:
    op.alter_column(
        "tasks_master",
        "answer_options_latex",
        existing_type=postgresql.JSONB(),
        type_=postgresql.JSON(),
        postgresql_using="answer_options_latex::json",
    )
