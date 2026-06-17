"""Add task_figures + task_figure_refs — изображения учебника, привязанные к задачам

task_figures хранит каждый рисунок/график из PDF (PNG, вырезка bbox).
semantic_json — машиночитаемое описание для AI (classifier, distractors, LLM-grader);
alt_text — для accessibility.

task_figure_refs: many-to-many между tasks_master и task_figures
(одна фигура может относиться к нескольким задачам, одна задача — иметь несколько фигур).

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-05-28
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_figures",
        sa.Column("figure_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "textbook_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("textbooks.textbook_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("bbox", postgresql.JSONB(), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("alt_text", sa.Text(), nullable=True),
        sa.Column("semantic_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_task_figures_textbook_page",
        "task_figures",
        ["textbook_id", "page"],
    )

    op.create_table(
        "task_figure_refs",
        sa.Column(
            "task_id",
            sa.String(length=60),
            sa.ForeignKey("tasks_master.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "figure_id",
            sa.String(length=64),
            sa.ForeignKey("task_figures.figure_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("order_idx", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_task_figure_refs_figure",
        "task_figure_refs",
        ["figure_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_figure_refs_figure", table_name="task_figure_refs")
    op.drop_table("task_figure_refs")
    op.drop_index("ix_task_figures_textbook_page", table_name="task_figures")
    op.drop_table("task_figures")
