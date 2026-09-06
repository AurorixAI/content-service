"""Add the LaTeX normalisation columns the chain assumed already existed.

Revision ID: h9c0d1e2f3a4
Revises: h9b0c1d2e3f4
Create Date: 2026-09-06

``tasks_master.latex_status`` and ``latex_normalized_at`` are written by the
LaTeX backfill pipeline and read by ``content_router``'s task query, but no
revision has ever created them — they exist only on databases a script happened
to touch. On preview and production they were absent, so every
``GET /api/v1/content/tasks`` answered 500 with ``UndefinedColumn``, and both
exam generation and diagnostic session creation failed through it. Revision
``m4a5b6c7d8e9`` also inserts a row naming ``latex_status``, so the columns have
to exist before it runs.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h9c0d1e2f3a4"
down_revision: Union[str, Sequence[str], None] = "h9b0c1d2e3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable on purpose: an existing row has simply never been through the
    # normaliser, which is different from having failed it. The pipeline's own
    # states are 'verified' | 'partial' | 'failed'.
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("tasks_master")}
    if "latex_status" not in existing:
        op.add_column("tasks_master", sa.Column("latex_status", sa.String(20), nullable=True))
    if "latex_normalized_at" not in existing:
        op.add_column("tasks_master", sa.Column("latex_normalized_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks_master", "latex_normalized_at")
    op.drop_column("tasks_master", "latex_status")
