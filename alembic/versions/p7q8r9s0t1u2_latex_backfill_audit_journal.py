"""Add an append-only audit and rollback journal for LaTeX display backfills.

Revision ID: p7q8r9s0t1u2
Revises: o6c7d8e9f0a1
Create Date: 2026-09-19

The backfill intentionally changes only derived display projections, but those
projections are still learner-facing content.  A durable run manifest and a
per-task before/after journal make each automated edit attributable and enable
conflict-safe rollback without ever restoring raw educational source fields.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "p7q8r9s0t1u2"
down_revision = "o6c7d8e9f0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("latex_backfill_runs"):
        op.create_table(
            "latex_backfill_runs",
            sa.Column("run_id", postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column("label", sa.String(160), nullable=False),
            sa.Column("actor", sa.String(80), nullable=False),
            sa.Column("status", sa.String(30), nullable=False),
            sa.Column("model", sa.String(120), nullable=False),
            sa.Column("prompt_version", sa.String(120), nullable=False),
            sa.Column("policy_version", sa.String(120), nullable=False),
            sa.Column("config", postgresql.JSONB(), nullable=False),
            sa.Column("queue_sha256", sa.String(64), nullable=True),
            sa.Column("summary", postgresql.JSONB(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "status IN ('running', 'completed', 'completed_with_review', 'failed', 'rolled_back')",
                name="ck_latex_backfill_runs_status",
            ),
        )

    if not inspector.has_table("task_latex_change_audit"):
        op.create_table(
            "task_latex_change_audit",
            sa.Column("audit_id", postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column(
                "run_id", postgresql.UUID(as_uuid=False),
                sa.ForeignKey("latex_backfill_runs.run_id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column(
                "task_id", sa.String(60),
                sa.ForeignKey("tasks_master.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("event_type", sa.String(20), nullable=False),
            sa.Column(
                "rollback_of", postgresql.UUID(as_uuid=False),
                sa.ForeignKey("task_latex_change_audit.audit_id", ondelete="RESTRICT"),
                nullable=True,
            ),
            sa.Column("source_fingerprint_sha256", sa.String(64), nullable=False),
            sa.Column("before_snapshot", postgresql.JSONB(), nullable=False),
            sa.Column("after_snapshot", postgresql.JSONB(), nullable=False),
            sa.Column("before_display_sha256", sa.String(64), nullable=False),
            sa.Column("after_display_sha256", sa.String(64), nullable=False),
            sa.Column("validation", postgresql.JSONB(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
            sa.CheckConstraint(
                "event_type IN ('write', 'rollback')",
                name="ck_task_latex_change_audit_event_type",
            ),
        )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_latex_backfill_runs_started "
        "ON latex_backfill_runs (started_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_task_latex_audit_run_created "
        "ON task_latex_change_audit (run_id, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_task_latex_audit_task_created "
        "ON task_latex_change_audit (task_id, created_at DESC)"
    )
    # A source revision can be restored once. Re-running the same rollback is
    # harmlessly reported as already applied instead of overwriting later work.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_task_latex_audit_rollback_once "
        "ON task_latex_change_audit (rollback_of) WHERE rollback_of IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS task_latex_change_audit")
    op.execute("DROP TABLE IF EXISTS latex_backfill_runs")
