"""Add a self-contained coverage task for the G8 data-trend skill.

The only textbook task for G8_S28_04 requires an unverified source graph and
was correctly placed behind the visual-content gate.  This task covers the
same atomic skill using every datum in the written condition, so it is safe
for diagnostics and exams without any image dependency.

Revision ID: m4a5b6c7d8e9
Revises: l3f4a5b6c7d8
Create Date: 2026-08-30
"""
from alembic import op


revision = "m4a5b6c7d8e9"
down_revision = "l3f4a5b6c7d8"
branch_labels = None
depends_on = None


TASK_ID = "G8_CURATED_S28_04_001"


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO tasks_master (
            id, skill_id, question_text, question_latex, question_image_url,
            answer_type, correct_answer, correct_answer_latex,
            answer_options, answer_options_latex, distractor_meta,
            difficulty, cognitive_load,
            irt_discrimination, irt_difficulty, irt_guessing,
            verification_status, source_type, source_reference, tags,
            is_star, task_category, latex_status, is_active
        ) VALUES (
            'G8_CURATED_S28_04_001',
            'G8_S28_04',
            'В течение пяти дней число решённых задач было таким: в понедельник — 3, во вторник — 5, в среду — 7, в четверг — 9, в пятницу — 11. Какова тенденция изменения числа решённых задач?',
            'В течение пяти дней число решённых задач было таким: в понедельник — 3, во вторник — 5, в среду — 7, в четверг — 9, в пятницу — 11. Какова тенденция изменения числа решённых задач?',
            NULL,
            'text',
            'Число решённых задач увеличивалось на 2 каждый день.',
            'Число решённых задач увеличивалось на 2 каждый день.',
            '[]'::jsonb,
            '[]'::jsonb,
            '[]'::jsonb,
            'B',
            'apply',
            1.0,
            0.5,
            0.0,
            'verified',
            'ai_generated',
            'curated:coverage:G8_S28_04:001',
            '{
                "content_origin": "manual_curated_coverage_fix",
                "skill_alignment": "G8_S28_04",
                "mapping_confidence": 1.0,
                "answer_verify_mode": "manual_verified",
                "visual_independent": true,
                "step_by_step_solution": "Разности соседних значений равны: 5 - 3 = 2, 7 - 5 = 2, 9 - 7 = 2, 11 - 9 = 2. Следовательно, число решённых задач ежедневно увеличивалось на 2."
            }'::jsonb,
            FALSE,
            'standard',
            'verified',
            TRUE
        )
        ON CONFLICT (id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM tasks_master WHERE id = 'G8_CURATED_S28_04_001'")
