"""Add textbooks.figures_skipped — счётчик бесполезных рисунков

Аналог tasks_skipped: рисунки, помеченные Gemini Vision как «не полезные для
решения мат-задачи онлайн» (фото детей, портреты, орнаменты, обложки) удаляются
с диска и не пишутся в task_figures. Счётчик копится для аналитики покрытия.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-05-28
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "textbooks",
        sa.Column(
            "figures_skipped",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("textbooks", "figures_skipped")
