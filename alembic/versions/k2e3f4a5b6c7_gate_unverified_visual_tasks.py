"""Gate visual tasks until the exact source figure is verified.

The figure-link audit established that a source-book match alone is not enough:
an image can still be a different numbered figure from the same textbook.
This revision applies the content-safety policy for the current bank:

* keep tasks whose condition ↔ source figure relationship was verified;
* preserve three tasks whose complete numerical condition is self-contained,
  but remove their unverified illustrative image;
* deactivate every remaining visual task until the exact source crop is
  verified.  The task text and its current image URL remain available to
  curators, but students and exam generators cannot receive an unproven visual.

All decisions and the prior active state are retained in ``task_visual_audit``
so the action is fully reviewable and reversible.

Revision ID: k2e3f4a5b6c7
Revises: j1d2e3f4a5b6
Create Date: 2026-08-30
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "k2e3f4a5b6c7"
down_revision = "j1d2e3f4a5b6"
branch_labels = None
depends_on = None


# Exact task ↔ source-image matches established by source OCR / visual review.
VERIFIED_TASKS = (
    "G11_TB_§2_10_1",  # Fig. 2.11
    "G11_TB_§2_10_2",
    "G11_TB_§2_10_3",
    "G11_TB_§2_11_1",  # Fig. 2.12
    "G11_TB_§2_11_2",
    "G11_TB_§2_11_3",
    "G11_TB_5_10*_5_101",  # Fig. 131
    "G11_TB_§5_5_101",
    "G5_TB_31_554",  # verified AOB = 60° diagram
    "G11_TB_22_1_15_1",  # Fig. 22.5
    "G11_TB_22_1_15_2",
    "G11_TB_22_1_15_3",
)

# Each condition contains all data necessary for a correct solution.  The
# historical picture is therefore removed, but the task remains active.
OPTIONAL_IMAGE_TASKS = (
    "G5_TB_27_474",  # speeds and delay are explicit in the text
    "G7_ALG_13_4",  # all rectangle dimensions are explicit in the text
    "G7_ALG_38_13",  # denomination set is explicit in the text
)

# These ten tasks were already visually proven to have a wrong same-book image
# and were detached from it in the preceding revision.  They require a visual,
# so must not remain selectable while the correct crop is unavailable.
PROVEN_WRONG_VISUAL_TASKS = (
    "G11_TB_5_10*_5_96",  # requires Fig. 129
    "G11_TB_§5_5_96",
    "G11_TB_5_10*_5_98",  # requires Fig. 130
    "G11_TB_§5_5_98",
    "G11_TB_22_1_13",  # requires Fig. 22.4
    "G5_TB_31_530",  # requires Fig. 21
    "G5_TB_31_548",  # requires Fig. 25
    "G5_TB_31_549",  # requires Figs. 26–27
    "G5_TB_31_550",  # requires Fig. 28
    "G5_TB_31_553",  # requires Fig. 30
)


def _sql_list(items: tuple[str, ...]) -> str:
    return ", ".join(f"'{item}'" for item in items)


def upgrade() -> None:
    op.create_table(
        "task_visual_audit",
        sa.Column("task_id", sa.String(length=60), nullable=False),
        sa.Column("decision", sa.String(length=48), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("image_url_before", sa.Text(), nullable=True),
        sa.Column("is_active_before", sa.Boolean(), nullable=False),
        sa.Column(
            "audited_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks_master.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id"),
    )

    # Record verified tasks first.  They stay in their existing active state.
    op.execute(
        f"""
        INSERT INTO task_visual_audit (
            task_id, decision, reason, image_url_before, is_active_before
        )
        SELECT
            id,
            'verified_exact_visual',
            'Exact task-to-source-figure match verified by source caption or visual audit.',
            question_image_url,
            is_active
        FROM tasks_master
        WHERE id IN ({_sql_list(VERIFIED_TASKS)})
        """
    )

    # These are self-contained tasks: retain them without the unproven image.
    op.execute(
        f"""
        INSERT INTO task_visual_audit (
            task_id, decision, reason, image_url_before, is_active_before
        )
        SELECT
            id,
            'image_removed_not_required',
            'All data required to solve the task are present in the written condition.',
            question_image_url,
            is_active
        FROM tasks_master
        WHERE id IN ({_sql_list(OPTIONAL_IMAGE_TASKS)})
        """
    )
    op.execute(
        f"""
        UPDATE tasks_master
        SET question_image_url = NULL
        WHERE id IN ({_sql_list(OPTIONAL_IMAGE_TASKS)})
        """
    )

    # Every other task still carrying an image is visual-dependent but lacks a
    # verified exact source relation.  Keep the data for curation, but remove
    # it from all active selection paths.
    op.execute(
        f"""
        INSERT INTO task_visual_audit (
            task_id, decision, reason, image_url_before, is_active_before
        )
        SELECT
            id,
            'deactivated_unverified_required_visual',
            'The task depends on a visual, but its exact source figure has not been verified.',
            question_image_url,
            is_active
        FROM tasks_master
        WHERE question_image_url IS NOT NULL
          AND btrim(question_image_url) <> ''
          AND id NOT IN ({_sql_list(VERIFIED_TASKS + OPTIONAL_IMAGE_TASKS)})
        """
    )
    op.execute(
        """
        UPDATE tasks_master
        SET is_active = FALSE
        WHERE id IN (
            SELECT task_id
            FROM task_visual_audit
            WHERE decision = 'deactivated_unverified_required_visual'
        )
        """
    )

    # The preceding revision removed their wrong displayed image; this gate
    # also removes the tasks themselves from active pools until re-curated.
    op.execute(
        f"""
        INSERT INTO task_visual_audit (
            task_id, decision, reason, image_url_before, is_active_before
        )
        SELECT
            id,
            'deactivated_verified_wrong_visual',
            'The displayed image was proven to be a different numbered figure; the correct crop is unavailable.',
            question_image_url,
            is_active
        FROM tasks_master
        WHERE id IN ({_sql_list(PROVEN_WRONG_VISUAL_TASKS)})
        """
    )
    op.execute(
        f"""
        UPDATE tasks_master
        SET is_active = FALSE
        WHERE id IN ({_sql_list(PROVEN_WRONG_VISUAL_TASKS)})
        """
    )


def downgrade() -> None:
    # The audit row contains the precise state captured immediately before the
    # gate, so downgrade restores only what this revision changed.
    op.execute(
        """
        UPDATE tasks_master t
        SET
            question_image_url = a.image_url_before,
            is_active = a.is_active_before
        FROM task_visual_audit a
        WHERE a.task_id = t.id
          AND a.decision = 'image_removed_not_required'
        """
    )
    op.execute(
        """
        UPDATE tasks_master t
        SET is_active = a.is_active_before
        FROM task_visual_audit a
        WHERE a.task_id = t.id
          AND a.decision IN (
              'deactivated_unverified_required_visual',
              'deactivated_verified_wrong_visual'
          )
        """
    )
    op.drop_table("task_visual_audit")
