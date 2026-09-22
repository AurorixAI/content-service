"""Add field-level LaTeX display projection attestations.

Revision ID: q8r9s0t1u2v3
Revises: p7q8r9s0t1u2
Create Date: 2026-09-20

An attestation is the durable evidence that one learner-facing LaTeX field was
independently reviewed against its immutable raw source.  New evidence is
always appended; a previous attestation is retained and explicitly revoked
before a replacement can become active.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "q8r9s0t1u2v3"
down_revision = "p7q8r9s0t1u2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("task_latex_display_attestations"):
        op.create_table(
            "task_latex_display_attestations",
            sa.Column("attestation_id", postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column(
                "task_id",
                sa.String(60),
                sa.ForeignKey("tasks_master.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            # E.g. question, answer, dmeta[2].description.  This identifies
            # the exact display projection rather than the task as a whole.
            sa.Column("field_key", sa.String(160), nullable=False),
            # Exact immutable raw source and exact learner-facing projection.
            # They are intentionally stored independently from the mutable
            # task row, together with their individual content fingerprints.
            sa.Column("source_value", sa.Text(), nullable=False),
            sa.Column("display_value", sa.Text(), nullable=False),
            sa.Column("source_sha256", sa.String(64), nullable=False),
            sa.Column("display_sha256", sa.String(64), nullable=False),
            sa.Column(
                "run_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("latex_backfill_runs.run_id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column(
                "audit_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("task_latex_change_audit.audit_id", ondelete="RESTRICT"),
                nullable=True,
            ),
            sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'active'")),
            sa.Column(
                "review_metadata",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "attested_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("NOW()"),
            ),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revocation_reason", sa.Text(), nullable=True),
            sa.CheckConstraint(
                "status IN ('active', 'revoked')",
                name="ck_task_latex_attestation_status",
            ),
            sa.CheckConstraint(
                "char_length(btrim(field_key)) > 0",
                name="ck_task_latex_attestation_field_key",
            ),
            sa.CheckConstraint(
                "source_sha256 ~ '^[0-9a-f]{64}$'",
                name="ck_task_latex_attestation_source_sha256",
            ),
            sa.CheckConstraint(
                "display_sha256 ~ '^[0-9a-f]{64}$'",
                name="ck_task_latex_attestation_display_sha256",
            ),
            sa.CheckConstraint(
                "(status = 'active' AND revoked_at IS NULL AND revocation_reason IS NULL) "
                "OR (status = 'revoked' AND revoked_at IS NOT NULL "
                "AND char_length(btrim(revocation_reason)) > 0)",
                name="ck_task_latex_attestation_lifecycle",
            ),
        )

    # A task field can have one current evidence record.  Revoking it retains
    # the historical row and permits a newly reviewed projection to be added.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_task_latex_attestation_active_field "
        "ON task_latex_display_attestations (task_id, field_key) "
        "WHERE status = 'active'"
    )
    # Serves current display selection (one task, all its active fields) and
    # chronological evidence views without scanning all runs.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_task_latex_attestation_task_field_time "
        "ON task_latex_display_attestations (task_id, field_key, attested_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_task_latex_attestation_run_time "
        "ON task_latex_display_attestations (run_id, attested_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_task_latex_attestation_audit "
        "ON task_latex_display_attestations (audit_id) WHERE audit_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS task_latex_display_attestations")
