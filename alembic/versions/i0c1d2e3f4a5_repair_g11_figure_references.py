"""Repair confirmed Figure 2.11/2.12 links without corrupting other books.

The old global ``fig-pN-K`` IDs collide between textbooks.  This migration
creates scoped records for the two verified images from the Grade 11 Nelin
textbook and repairs only the fifteen reviewed task links.  The visual URL is
also corrected because print packages consume ``question_image_url`` directly.

Revision ID: i0c1d2e3f4a5
Revises: h9b0c1d2e3f4
Create Date: 2026-08-29
"""
from __future__ import annotations

from alembic import op


revision = "i0c1d2e3f4a5"
down_revision = "h9b0c1d2e3f4"
branch_labels = None
depends_on = None


TEXTBOOK_ID = "1b758c3d-9d0d-41f6-ad0b-dcf3c3872a75"
LEGACY_P30_URL = f"/api/v1/figures/{TEXTBOOK_ID}/fig-p30-1.png"
LEGACY_P31_URL = f"/api/v1/figures/{TEXTBOOK_ID}/fig-p31-1.png"
FIG_211_ID = "fig-1b758c3d-p30-1"
FIG_212_ID = "fig-1b758c3d-p31-1"

TASKS_TO_UNLINK = (
    "G11_TB_§2_3",
    "G11_TB_§2_3_1",
    "G11_TB_§2_3_2",
    "G11_TB_§2_3_3",
    "G11_TB_§2_3_4",
    "G11_TB_§2_9_1",
    "G11_TB_§2_9_2",
    "G11_TB_§2_9_3",
    "G11_TB_§2_9_4",
    "G11_TB_§2_10_1",
    "G11_TB_§2_10_2",
    "G11_TB_§2_10_3",
    "G11_TB_§2_11_1",
    "G11_TB_§2_11_2",
    "G11_TB_§2_11_3",
)
TASKS_FIG_211 = (
    "G11_TB_§2_10_1",
    "G11_TB_§2_10_2",
    "G11_TB_§2_10_3",
)
TASKS_FIG_212 = (
    "G11_TB_§2_11_1",
    "G11_TB_§2_11_2",
    "G11_TB_§2_11_3",
)


def _sql_list(items: tuple[str, ...]) -> str:
    return ", ".join(f"'{item}'" for item in items)


def upgrade() -> None:
    # These image files already exist in the textbook's storage directory.
    # The normalized bbox deliberately describes the whole extracted PNG.
    op.execute(
        f"""
        INSERT INTO task_figures (
            figure_id, textbook_id, page, bbox, image_url, alt_text, semantic_json
        ) VALUES
            (
                '{FIG_211_ID}', '{TEXTBOOK_ID}'::uuid, 30,
                '{{"x0": 0, "y0": 0, "x1": 1, "y1": 1}}'::jsonb,
                '{LEGACY_P30_URL}',
                'Рис. 2.11. График зависимости пути s = s(t) от времени t.',
                '{{"figure_number": "2.11", "type": "function_plot"}}'::jsonb
            ),
            (
                '{FIG_212_ID}', '{TEXTBOOK_ID}'::uuid, 31,
                '{{"x0": 0, "y0": 0, "x1": 1, "y1": 1}}'::jsonb,
                '{LEGACY_P31_URL}',
                'Рис. 2.12. График функции y = f(x) на промежутке от −4 до 7.',
                '{{"figure_number": "2.12", "type": "function_plot"}}'::jsonb
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

    # All fifteen reviewed links incorrectly point to the Grade 10 image that
    # later overwrote the global legacy ID ``fig-p30-1``.
    op.execute(
        f"""
        DELETE FROM task_figure_refs
        WHERE figure_id = 'fig-p30-1'
          AND task_id IN ({_sql_list(TASKS_TO_UNLINK)})
        """
    )

    for task_id in TASKS_FIG_211:
        op.execute(
            f"""
            INSERT INTO task_figure_refs (task_id, figure_id, order_idx)
            VALUES ('{task_id}', '{FIG_211_ID}', 0)
            ON CONFLICT (task_id, figure_id) DO UPDATE SET order_idx = EXCLUDED.order_idx
            """
        )
    for task_id in TASKS_FIG_212:
        op.execute(
            f"""
            INSERT INTO task_figure_refs (task_id, figure_id, order_idx)
            VALUES ('{task_id}', '{FIG_212_ID}', 0)
            ON CONFLICT (task_id, figure_id) DO UPDATE SET order_idx = EXCLUDED.order_idx
            """
        )

    # §2.11 is the user-reported problem: all three tasks now show Fig. 2.12.
    op.execute(
        f"""
        UPDATE tasks_master
        SET question_image_url = '{LEGACY_P31_URL}'
        WHERE id IN ({_sql_list(TASKS_FIG_212)})
        """
    )

    # The long introductory task §2.3 mentioned Fig. 2.3, but was displaying
    # Fig. 2.11.  Until its own figure is explicitly curated, no image is safer
    # than a demonstrably wrong one.
    op.execute(
        f"""
        UPDATE tasks_master
        SET question_image_url = NULL
        WHERE id = 'G11_TB_§2_3'
          AND question_image_url = '{LEGACY_P30_URL}'
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DELETE FROM task_figure_refs
        WHERE task_id IN ({_sql_list(TASKS_FIG_211 + TASKS_FIG_212)})
          AND figure_id IN ('{FIG_211_ID}', '{FIG_212_ID}')
        """
    )
    for task_id in TASKS_TO_UNLINK:
        op.execute(
            f"""
            INSERT INTO task_figure_refs (task_id, figure_id, order_idx)
            VALUES ('{task_id}', 'fig-p30-1', 0)
            ON CONFLICT (task_id, figure_id) DO UPDATE SET order_idx = EXCLUDED.order_idx
            """
        )
    op.execute(
        f"""
        UPDATE tasks_master
        SET question_image_url = '{LEGACY_P30_URL}'
        WHERE id IN ({_sql_list(TASKS_FIG_212 + ('G11_TB_§2_3',))})
        """
    )
    op.execute(
        f"""
        DELETE FROM task_figures
        WHERE figure_id IN ('{FIG_211_ID}', '{FIG_212_ID}')
        """
    )
