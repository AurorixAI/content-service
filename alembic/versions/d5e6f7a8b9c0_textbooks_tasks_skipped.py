"""Add textbooks.tasks_skipped — счётчик offline-задач, отброшенных фильтром

Платформа онлайн-only: задачи вида «проговори вслух», «начерти в тетради»,
«измерь линейкой», «сделай проект» и т.п. не пишутся в tasks_master.
Чтобы видеть качество оцифровки, считаем сколько было выкинуто на учебник.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-05-28
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "textbooks",
        sa.Column(
            "tasks_skipped",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("textbooks", "tasks_skipped")
