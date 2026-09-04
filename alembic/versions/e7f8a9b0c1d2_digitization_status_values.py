"""digitization_status: привести CHECK к значениям, которые пишет конвейер

B12. Базовая схема разрешала `pending | ocr_done | extracting | extracted |
failed | complete`, а код пишет `processing | done | error` — **ни одного
пересечения**. `update_digitization_status` стоит первым действием
`_run_pdf_page_based`, поэтому любой прогон PDF на этой схеме падал на первом
же операторе, ещё до OCR. Обнаружено фактом при первом реальном прогоне книги
2026-08-30.

Констрейнт расширяется, а не заменяется: старые значения остаются валидными,
чтобы уже накопленные строки не стали нарушением. Тот же принцип, что в
c5d6e7f8a9b0 — миграция не должна ронять существующее содержимое.

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
"""

from alembic import op

revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None

_ALLOWED = (
    # historical
    "pending", "ocr_done", "extracting", "extracted", "failed", "complete",
    # то, что реально пишет src/pipeline/db_writer.py и src/worker/tasks.py
    "processing", "done", "error",
)


def upgrade() -> None:
    values = ", ".join(f"'{v}'" for v in _ALLOWED)
    op.execute(
        "ALTER TABLE textbooks DROP CONSTRAINT IF EXISTS textbooks_digitization_status_check"
    )
    op.execute(
        f"ALTER TABLE textbooks ADD CONSTRAINT textbooks_digitization_status_check "
        f"CHECK (digitization_status IN ({values}))"
    )


def downgrade() -> None:
    # Возврат к узкому набору намеренно НЕ делается: строки со статусом
    # `processing`/`done`/`error` стали бы нарушением, и откат схемы уронил бы
    # таблицу. Констрейнт просто снимается.
    op.execute(
        "ALTER TABLE textbooks DROP CONSTRAINT IF EXISTS textbooks_digitization_status_check"
    )
