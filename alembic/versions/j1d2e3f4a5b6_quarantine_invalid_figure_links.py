"""Quarantine invalid legacy figure links and remove proven wrong PDF images.

The original figure key (``fig-pN-K``) was global even though PDF page numbers
repeat between textbooks.  Consequently, a later import could overwrite a
figure record and make tasks from another textbook point to it.  This revision
does two deliberately separate things:

* moves every cross-textbook legacy reference into an auditable quarantine
  table before unlinking it;
* removes only direct PDF images that were visually verified as the wrong
  *numbered* figure within the correct textbook.  No guessed replacement is
  introduced when the required source crop is unavailable.

It also adds scoped entries for the three images that were verified during the
audit, so their correct task links cannot collide in future imports.

Revision ID: j1d2e3f4a5b6
Revises: i0c1d2e3f4a5
Create Date: 2026-08-30
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "j1d2e3f4a5b6"
down_revision = "i0c1d2e3f4a5"
branch_labels = None
depends_on = None


NIKOLSKY_ID = "3aeaf6a8-3b03-4b74-beb6-9a282b6749f1"
IDUM_G5_P1_ID = "5630a994-061d-4c20-9863-fe049c8059fb"
NELIN_ID = "1b758c3d-9d0d-41f6-ad0b-dcf3c3872a75"

URL_FIG_131 = f"/api/v1/figures/{NIKOLSKY_ID}/fig-p150-1.png"
URL_ANGLE_AOB = f"/api/v1/figures/{IDUM_G5_P1_ID}/fig-p118-2.png"
URL_FIG_225 = f"/api/v1/figures/{NELIN_ID}/fig-p298-1.png"

FIG_131_ID = "fig-3aeaf6a8-p150-1"
FIG_ANGLE_AOB_ID = "fig-5630a994-p118-2"
FIG_225_ID = "fig-1b758c3d-p298-1"

# These tasks were visually checked against the extracted PNGs and their
# source wording.  Their required figures (129, 130, 21, 25, 26–27, 28, 30,
# 22.4) are not available as extracted files, so a blank image is truthful.
TASKS_CLEAR_FIG_131 = (
    "G11_TB_5_10*_5_96",  # needs Fig. 129, not Fig. 131
    "G11_TB_§5_5_96",
    "G11_TB_5_10*_5_98",  # needs Fig. 130, not Fig. 131
    "G11_TB_§5_5_98",
)
TASKS_CLEAR_ANGLE_AOB = (
    "G5_TB_31_530",  # needs Fig. 21
    "G5_TB_31_548",  # needs Fig. 25
    "G5_TB_31_549",  # needs Figs. 26–27
    "G5_TB_31_550",  # needs Fig. 28
    "G5_TB_31_553",  # needs Fig. 30
)
TASKS_CLEAR_FIG_225 = ("G11_TB_22_1_13",)  # needs Fig. 22.4, not 22.5

# These tasks were visually confirmed to match the indicated file.
TASKS_FIG_131 = ("G11_TB_5_10*_5_101", "G11_TB_§5_5_101")
TASKS_ANGLE_AOB = ("G5_TB_31_554",)
TASKS_FIG_225 = (
    "G11_TB_22_1_15_1",
    "G11_TB_22_1_15_2",
    "G11_TB_22_1_15_3",
)


def _sql_list(items: tuple[str, ...]) -> str:
    return ", ".join(f"'{item}'" for item in items)


def upgrade() -> None:
    # Keep an auditable, reversible record before removing legacy collisions.
    op.create_table(
        "task_figure_ref_quarantine",
        sa.Column("task_id", sa.String(length=60), nullable=False),
        sa.Column("figure_id", sa.String(length=64), nullable=False),
        sa.Column("order_idx", sa.Integer(), nullable=False),
        sa.Column("source_textbook_id", sa.String(length=36), nullable=False),
        sa.Column("figure_textbook_id", sa.String(length=36), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column(
            "quarantined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("task_id", "figure_id"),
    )

    # Archive every cross-textbook link before removal.  A task's source UUID
    # is authoritative; intentional cross-textbook figure references are not
    # supported by this content model.
    op.execute(
        """
        INSERT INTO task_figure_ref_quarantine (
            task_id, figure_id, order_idx, source_textbook_id,
            figure_textbook_id, reason
        )
        SELECT
            r.task_id,
            r.figure_id,
            r.order_idx,
            substring(t.source_reference from '^[0-9a-f-]{36}'),
            f.textbook_id::text,
            'cross_textbook_legacy_collision'
        FROM task_figure_refs r
        JOIN tasks_master t ON t.id = r.task_id
        JOIN task_figures f ON f.figure_id = r.figure_id
        WHERE substring(t.source_reference from '^[0-9a-f-]{36}')
              <> f.textbook_id::text
        """
    )
    op.execute(
        """
        DELETE FROM task_figure_refs r
        USING tasks_master t, task_figures f
        WHERE r.task_id = t.id
          AND r.figure_id = f.figure_id
          AND substring(t.source_reference from '^[0-9a-f-]{36}')
              <> f.textbook_id::text
        """
    )

    # Fig. 22.5 is from the right book but was attached to a task explicitly
    # asking for Fig. 22.4.  Preserve that reference in the same quarantine.
    op.execute(
        f"""
        INSERT INTO task_figure_ref_quarantine (
            task_id, figure_id, order_idx, source_textbook_id,
            figure_textbook_id, reason
        )
        SELECT
            r.task_id,
            r.figure_id,
            r.order_idx,
            substring(t.source_reference from '^[0-9a-f-]{{36}}'),
            f.textbook_id::text,
            'verified_wrong_figure_number'
        FROM task_figure_refs r
        JOIN tasks_master t ON t.id = r.task_id
        JOIN task_figures f ON f.figure_id = r.figure_id
        WHERE r.task_id IN ({_sql_list(TASKS_CLEAR_FIG_225)})
        ON CONFLICT (task_id, figure_id) DO NOTHING
        """
    )
    op.execute(
        f"""
        DELETE FROM task_figure_refs
        WHERE task_id IN ({_sql_list(TASKS_CLEAR_FIG_225)})
        """
    )

    # Scoped IDs preserve ownership even where the old unscoped record was
    # overwritten by another textbook.  The full-image bbox is intentional:
    # these PNGs are already extracted crops served to the client.
    op.execute(
        f"""
        INSERT INTO task_figures (
            figure_id, textbook_id, page, bbox, image_url, alt_text, semantic_json
        ) VALUES
            (
                '{FIG_131_ID}', '{NIKOLSKY_ID}'::uuid, 150,
                '{{"x0": 0, "y0": 0, "x1": 1, "y1": 1}}'::jsonb,
                '{URL_FIG_131}',
                'Рис. 131. Наблюдатель и статуя на постаменте.',
                '{{"figure_number":"131","type":"math_diagram"}}'::jsonb
            ),
            (
                '{FIG_ANGLE_AOB_ID}', '{IDUM_G5_P1_ID}'::uuid, 118,
                '{{"x0": 0, "y0": 0, "x1": 1, "y1": 1}}'::jsonb,
                '{URL_ANGLE_AOB}',
                'Схема с транспортиром: угол AOB равен 60 градусам.',
                '{{"type":"math_diagram"}}'::jsonb
            ),
            (
                '{FIG_225_ID}', '{NELIN_ID}'::uuid, 298,
                '{{"x0": 0, "y0": 0, "x1": 1, "y1": 1}}'::jsonb,
                '{URL_FIG_225}',
                'Рис. 22.5. Набор монет достоинством 1, 25, 2, 5, 10 и 50 копеек.',
                '{{"figure_number":"22.5","type":"math_diagram"}}'::jsonb
            )
        ON CONFLICT (figure_id) DO UPDATE SET
            textbook_id = EXCLUDED.textbook_id,
            page = EXCLUDED.page,
            bbox = EXCLUDED.bbox,
            image_url = EXCLUDED.image_url,
            alt_text = EXCLUDED.alt_text,
            semantic_json = EXCLUDED.semantic_json
        """
    )

    for figure_id, task_ids in (
        (FIG_131_ID, TASKS_FIG_131),
        (FIG_ANGLE_AOB_ID, TASKS_ANGLE_AOB),
        (FIG_225_ID, TASKS_FIG_225),
    ):
        for task_id in task_ids:
            op.execute(
                f"""
                INSERT INTO task_figure_refs (task_id, figure_id, order_idx)
                VALUES ('{task_id}', '{figure_id}', 0)
                ON CONFLICT (task_id, figure_id) DO UPDATE
                  SET order_idx = EXCLUDED.order_idx
                """
            )

    # Remove only the rendered URLs whose numbered figure was proven wrong.
    op.execute(
        f"""
        UPDATE tasks_master
        SET question_image_url = NULL
        WHERE id IN ({_sql_list(TASKS_CLEAR_FIG_131)})
          AND question_image_url = '{URL_FIG_131}'
        """
    )
    op.execute(
        f"""
        UPDATE tasks_master
        SET question_image_url = NULL
        WHERE id IN ({_sql_list(TASKS_CLEAR_ANGLE_AOB)})
          AND question_image_url = '{URL_ANGLE_AOB}'
        """
    )
    op.execute(
        f"""
        UPDATE tasks_master
        SET question_image_url = NULL
        WHERE id IN ({_sql_list(TASKS_CLEAR_FIG_225)})
          AND question_image_url = '{URL_FIG_225}'
        """
    )


def downgrade() -> None:
    # Restore the direct URLs first, then exact archived references.  This is
    # intentionally precise rather than attempting to reconstruct links from
    # current figure IDs.
    op.execute(
        f"""
        UPDATE tasks_master
        SET question_image_url = '{URL_FIG_131}'
        WHERE id IN ({_sql_list(TASKS_CLEAR_FIG_131)})
          AND question_image_url IS NULL
        """
    )
    op.execute(
        f"""
        UPDATE tasks_master
        SET question_image_url = '{URL_ANGLE_AOB}'
        WHERE id IN ({_sql_list(TASKS_CLEAR_ANGLE_AOB)})
          AND question_image_url IS NULL
        """
    )
    op.execute(
        f"""
        UPDATE tasks_master
        SET question_image_url = '{URL_FIG_225}'
        WHERE id IN ({_sql_list(TASKS_CLEAR_FIG_225)})
          AND question_image_url IS NULL
        """
    )

    op.execute(
        f"""
        DELETE FROM task_figure_refs
        WHERE figure_id IN ('{FIG_131_ID}', '{FIG_ANGLE_AOB_ID}', '{FIG_225_ID}')
          AND task_id IN ({_sql_list(TASKS_FIG_131 + TASKS_ANGLE_AOB + TASKS_FIG_225)})
        """
    )
    op.execute(
        """
        INSERT INTO task_figure_refs (task_id, figure_id, order_idx)
        SELECT task_id, figure_id, order_idx
        FROM task_figure_ref_quarantine
        ON CONFLICT (task_id, figure_id) DO NOTHING
        """
    )
    op.execute(
        f"""
        DELETE FROM task_figures
        WHERE figure_id IN ('{FIG_131_ID}', '{FIG_ANGLE_AOB_ID}', '{FIG_225_ID}')
        """
    )
    op.drop_table("task_figure_ref_quarantine")
