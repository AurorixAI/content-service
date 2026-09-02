"""Turn the curated G8 trend task into a fully instrumented MCQ.

The coverage task is deliberately self-contained: it keeps no image relation
and all values needed to identify the trend are written in the condition.
This revision adds authored options, parallel LaTeX fields and three
diagnostic distractors with precise error explanations.

Revision ID: n5b6c7d8e9f0
Revises: m4a5b6c7d8e9
Create Date: 2026-08-30
"""
from alembic import op


revision = "n5b6c7d8e9f0"
down_revision = "m4a5b6c7d8e9"
branch_labels = None
depends_on = None


TASK_ID = "G8_CURATED_S28_04_001"


def upgrade() -> None:
    op.execute(
        """
        UPDATE tasks_master
        SET
            question_text = 'В течение пяти дней число решённых задач было таким: в понедельник — 3, во вторник — 5, в среду — 7, в четверг — 9, в пятницу — 11. Какова тенденция изменения числа решённых задач?',
            question_latex = 'В течение пяти дней число решённых задач было таким: в понедельник — $3$, во вторник — $5$, в среду — $7$, в четверг — $9$, в пятницу — $11$. Какова тенденция изменения числа решённых задач?',
            question_image_url = NULL,
            answer_type = 'multiple_choice',
            correct_answer = 'Число решённых задач ежедневно увеличивалось на 2.',
            correct_answer_latex = 'Число решённых задач ежедневно увеличивалось на $2$.',
            answer_options = '[
                "Число решённых задач ежедневно увеличивалось на 2.",
                "Число решённых задач ежедневно увеличивалось на 4.",
                "Число решённых задач ежедневно уменьшалось на 2.",
                "Число решённых задач увеличивалось, но неравномерно."
            ]'::jsonb,
            answer_options_latex = '[
                "Число решённых задач ежедневно увеличивалось на $2$.",
                "Число решённых задач ежедневно увеличивалось на $4$.",
                "Число решённых задач ежедневно уменьшалось на $2$.",
                "Число решённых задач увеличивалось, но неравномерно."
            ]'::jsonb,
            distractor_meta = '[
                {
                    "value": "Число решённых задач ежедневно увеличивалось на 4.",
                    "value_latex": "Число решённых задач ежедневно увеличивалось на $4$.",
                    "error_type": "non_adjacent_difference",
                    "broken_step": "comparison_of_adjacent_values",
                    "plausibility": 0.82,
                    "error_logic": "Ученик сравнил значения через один день: 7 - 3 = 4, и ошибочно принял эту разность за ежедневное изменение. Для определения ежедневной тенденции нужно сравнивать соседние значения: 5 - 3 = 2, 7 - 5 = 2, 9 - 7 = 2, 11 - 9 = 2.",
                    "error_logic_latex": "Ученик сравнил значения через один день: $7 - 3 = 4$, и ошибочно принял эту разность за ежедневное изменение. Для определения ежедневной тенденции нужно сравнивать соседние значения: $5 - 3 = 2$, $7 - 5 = 2$, $9 - 7 = 2$, $11 - 9 = 2$.",
                    "explanation": "Ошибка в сравнении несоседних значений ряда."
                },
                {
                    "value": "Число решённых задач ежедневно уменьшалось на 2.",
                    "value_latex": "Число решённых задач ежедневно уменьшалось на $2$.",
                    "error_type": "trend_direction_reversal",
                    "broken_step": "trend_direction",
                    "plausibility": 0.72,
                    "error_logic": "Ученик верно заметил модуль разности 2, но перепутал направление изменения. Каждое следующее значение больше предыдущего: 5 > 3, 7 > 5, 9 > 7, 11 > 9.",
                    "error_logic_latex": "Ученик верно заметил модуль разности $2$, но перепутал направление изменения. Каждое следующее значение больше предыдущего: $5 > 3$, $7 > 5$, $9 > 7$, $11 > 9$.",
                    "explanation": "Ошибка в определении направления тенденции."
                },
                {
                    "value": "Число решённых задач увеличивалось, но неравномерно.",
                    "value_latex": "Число решённых задач увеличивалось, но неравномерно.",
                    "error_type": "uniform_pattern_missed",
                    "broken_step": "verification_of_common_difference",
                    "plausibility": 0.68,
                    "error_logic": "Ученик увидел общий рост, но не проверил разности соседних значений. Все они одинаковы и равны 2, поэтому рост равномерный.",
                    "error_logic_latex": "Ученик увидел общий рост, но не проверил разности соседних значений. Все они одинаковы и равны $2$, поэтому рост равномерный.",
                    "explanation": "Не проверена постоянная разность соседних значений."
                }
            ]'::jsonb,
            difficulty = 'B',
            cognitive_load = 'apply',
            irt_discrimination = 1.0,
            irt_difficulty = 0.5,
            irt_guessing = 0.25,
            verification_status = 'verified',
            source_type = 'ai_generated',
            source_reference = 'curated:coverage:G8_S28_04:001',
            tags = '{
                "content_origin": "manual_curated_coverage_fix",
                "coverage_replacement_for": "G8_TB_43_1091",
                "skill_alignment": "G8_S28_04",
                "mapping_l3": "G8_P28",
                "mapping_confidence": 1.0,
                "mapping_reasoning": "Задача требует выявить устойчивую закономерность в числовом ряду по разностям соседних значений, что напрямую соответствует навыку G8_S28_04.",
                "answer_source": "manual_curated",
                "answer_verify_mode": "manual_verified",
                "answer_canonical_source": "manual_curated",
                "verification_explanation": "Разности соседних значений равны: 5 - 3 = 2, 7 - 5 = 2, 9 - 7 = 2, 11 - 9 = 2. Следовательно, число решённых задач ежедневно увеличивалось на 2.",
                "step_by_step_solution": "1) Сравним 5 и 3: увеличение на 2. 2) Сравним 7 и 5: увеличение на 2. 3) Сравним 9 и 7: увеличение на 2. 4) Сравним 11 и 9: увеличение на 2. Разность постоянна, значит тенденция — равномерный рост на 2 в день.",
                "choices_complete": true,
                "distractor_validation": "manual_reviewed",
                "distractor_count": 3,
                "sympy_verified": false,
                "sympy_gate_reason": "textual_trend_task",
                "visual_independent": true,
                "metadata_schema_version": 1
            }'::jsonb,
            is_star = FALSE,
            task_category = 'standard',
            latex_status = 'verified',
            is_active = TRUE,
            updated_at = NOW()
        WHERE id = 'G8_CURATED_S28_04_001'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE tasks_master
        SET
            question_text = 'В течение пяти дней число решённых задач было таким: в понедельник — 3, во вторник — 5, в среду — 7, в четверг — 9, в пятницу — 11. Какова тенденция изменения числа решённых задач?',
            question_latex = 'В течение пяти дней число решённых задач было таким: в понедельник — 3, во вторник — 5, в среду — 7, в четверг — 9, в пятницу — 11. Какова тенденция изменения числа решённых задач?',
            question_image_url = NULL,
            answer_type = 'text',
            correct_answer = 'Число решённых задач увеличивалось на 2 каждый день.',
            correct_answer_latex = 'Число решённых задач увеличивалось на 2 каждый день.',
            answer_options = '[]'::jsonb,
            answer_options_latex = '[]'::jsonb,
            distractor_meta = '[]'::jsonb,
            irt_discrimination = 1.0,
            irt_difficulty = 0.5,
            irt_guessing = 0.0,
            tags = '{
                "content_origin": "manual_curated_coverage_fix",
                "skill_alignment": "G8_S28_04",
                "mapping_confidence": 1.0,
                "answer_verify_mode": "manual_verified",
                "visual_independent": true,
                "step_by_step_solution": "Разности соседних значений равны: 5 - 3 = 2, 7 - 5 = 2, 9 - 7 = 2, 11 - 9 = 2. Следовательно, число решённых задач ежедневно увеличивалось на 2."
            }'::jsonb,
            updated_at = NOW()
        WHERE id = 'G8_CURATED_S28_04_001'
        """
    )
