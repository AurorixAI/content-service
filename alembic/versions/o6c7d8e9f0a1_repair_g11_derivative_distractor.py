"""Repair a malformed and duplicate derivative distractor.

The authored second distractor for ``G11_TB_4_6_4_48_6`` contained an
unmatched inline-math delimiter.  It therefore reached every delivery mode as
two separate math fragments.  It also simplified to the correct derivative,
which made it an invalid distractor.  This migration replaces only that exact
legacy value with one well-formed, pedagogically meaningful wrong answer.

Revision ID: o6c7d8e9f0a1
Revises: n5b6c7d8e9f0
Create Date: 2026-08-30
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op


revision = "o6c7d8e9f0a1"
down_revision = "n5b6c7d8e9f0"
branch_labels = None
depends_on = None


TASK_ID = "G11_TB_4_6_4_48_6"
LEGACY_VALUE = r"$25x^{24} \cdot 4\cos(x) - $x^{25}$ \cdot 4\sin(x)$"
CORRECTED_VALUE = r"$25x^{24} \cdot \cos(x) - x^{25} \cdot \sin(x)$"
LEGACY_LOGIC = (
    "Ученик применил правило произведения, но забыл умножить производную "
    "степенной функции на второй множитель: вместо $25*4=100$ оставил "
    "$25*4$ как отдельные множители, не выполнив умножение коэффициентов."
)
LEGACY_LOGIC_LATEX = (
    "Ученик применил правило произведения, но забыл умножить производную "
    "степенной функции на второй множитель: вместо $25 \\cdot 4 = 100$ "
    "оставил $25 \\cdot 4$ как отдельные множители, не выполнив умножение коэффициентов."
)
CORRECTED_LOGIC = (
    "Ученик применил правило произведения, но потерял постоянный множитель 4 "
    "в обоих слагаемых производной."
)


def _replace(metadata: object, *, restore_legacy: bool) -> list[dict[str, object]] | None:
    if not isinstance(metadata, list) or len(metadata) < 2:
        return None
    items = [dict(item) if isinstance(item, dict) else item for item in metadata]
    item = items[1]
    if not isinstance(item, dict):
        return None

    expected = CORRECTED_VALUE if restore_legacy else LEGACY_VALUE
    if item.get("value") != expected or item.get("value_latex") != expected:
        return None

    if restore_legacy:
        item.update(
            value=LEGACY_VALUE,
            value_latex=LEGACY_VALUE,
            error_logic=LEGACY_LOGIC,
            explanation=LEGACY_LOGIC,
            error_logic_latex=LEGACY_LOGIC_LATEX,
        )
    else:
        item.update(
            value=CORRECTED_VALUE,
            value_latex=CORRECTED_VALUE,
            error_logic=CORRECTED_LOGIC,
            explanation=CORRECTED_LOGIC,
            error_logic_latex=CORRECTED_LOGIC,
        )
    return items


def _apply(*, restore_legacy: bool) -> None:
    bind = op.get_bind()
    metadata = bind.execute(
        sa.text("SELECT distractor_meta FROM tasks_master WHERE id = :task_id FOR UPDATE"),
        {"task_id": TASK_ID},
    ).scalar_one_or_none()
    patched = _replace(metadata, restore_legacy=restore_legacy)
    if patched is None:
        return
    bind.execute(
        sa.text(
            """
            UPDATE tasks_master
            SET distractor_meta = CAST(:distractor_meta AS jsonb), updated_at = NOW()
            WHERE id = :task_id
            """
        ),
        {"task_id": TASK_ID, "distractor_meta": json.dumps(patched, ensure_ascii=False)},
    )


def upgrade() -> None:
    _apply(restore_legacy=False)


def downgrade() -> None:
    _apply(restore_legacy=True)
