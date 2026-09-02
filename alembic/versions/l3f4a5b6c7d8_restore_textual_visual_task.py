"""Keep the self-contained G9 geometric-series task active without its image.

The visual audit initially placed this task behind the visual gate because its
source text mentioned Figure 86.  Manual review established that every value
needed for the solution is written in the condition itself: the figure does
not supply any mathematical information.  The task is therefore safe to keep
active after detaching the unverified image.

Revision ID: l3f4a5b6c7d8
Revises: k2e3f4a5b6c7
Create Date: 2026-08-30
"""
from alembic import op


revision = "l3f4a5b6c7d8"
down_revision = "k2e3f4a5b6c7"
branch_labels = None
depends_on = None


TASK_ID = "G9_TB_33_420"


def upgrade() -> None:
    op.execute(
        """
        UPDATE task_visual_audit
        SET
            decision = 'image_removed_not_required',
            reason = 'All data required to solve the task are present in the written condition; the figure is illustrative only.'
        WHERE task_id = 'G9_TB_33_420'
        """
    )
    op.execute(
        """
        UPDATE tasks_master
        SET question_image_url = NULL, is_active = TRUE
        WHERE id = 'G9_TB_33_420'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE task_visual_audit
        SET
            decision = 'deactivated_unverified_required_visual',
            reason = 'The task depends on a visual, but its exact source figure has not been verified.'
        WHERE task_id = 'G9_TB_33_420'
        """
    )
    op.execute(
        """
        UPDATE tasks_master
        SET question_image_url = a.image_url_before, is_active = FALSE
        FROM task_visual_audit a
        WHERE tasks_master.id = a.task_id
          AND tasks_master.id = 'G9_TB_33_420'
        """
    )
