"""Set server_default NOW() on tasks_master.updated_at

Without server_default, INSERT without specifying updated_at leaves NULL.
This migration adds the server default so the DB fills it automatically.

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-05-27
"""
from __future__ import annotations

from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tasks_master ALTER COLUMN updated_at SET DEFAULT NOW()"
    )
    # Back-fill any existing NULLs (none expected, but defensive)
    op.execute(
        "UPDATE tasks_master SET updated_at = NOW() WHERE updated_at IS NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE tasks_master ALTER COLUMN updated_at DROP DEFAULT"
    )
