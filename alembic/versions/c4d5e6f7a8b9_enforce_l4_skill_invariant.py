"""Enforce digitization invariants: tasks_master.skill_id NOT NULL + L4-only

Tasks must always be tied to a specific atomic skill (L4 level in
knowledge_hierarchy). The diagnostic IRT engine depends on this:
every task measures exactly one L4 skill.

This migration:
  1) Enforces NOT NULL on tasks_master.skill_id (was nullable)
  2) Adds CHECK constraint that the referenced skill is L4
     (validated via a trigger because PG CHECK cannot reference other tables)

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-05-27
"""
from __future__ import annotations

from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Safety: refuse upgrade if any orphan rows remain
    op.execute(
        """
        DO $$
        DECLARE
            orphan_count integer;
        BEGIN
            SELECT COUNT(*) INTO orphan_count
            FROM tasks_master WHERE skill_id IS NULL;
            IF orphan_count > 0 THEN
                RAISE EXCEPTION
                  'Cannot enforce NOT NULL: % tasks have NULL skill_id. '
                  'Either back-fill skill_id or DELETE them first.',
                  orphan_count;
            END IF;
        END $$;
        """
    )

    # 1) skill_id must be NOT NULL — every task is tied to an atomic skill
    op.alter_column("tasks_master", "skill_id", nullable=False)

    # 2) Trigger: skill_id must reference an L4 node
    op.execute(
        """
        CREATE OR REPLACE FUNCTION check_tasks_master_skill_is_l4()
        RETURNS TRIGGER AS $$
        DECLARE
            node_level text;
        BEGIN
            SELECT level INTO node_level
            FROM knowledge_hierarchy WHERE id = NEW.skill_id;
            IF node_level IS NULL THEN
                RAISE EXCEPTION
                  'tasks_master.skill_id=% does not exist in knowledge_hierarchy',
                  NEW.skill_id;
            END IF;
            IF node_level <> 'L4' THEN
                RAISE EXCEPTION
                  'tasks_master.skill_id=% has level=% — must be L4 (atomic skill)',
                  NEW.skill_id, node_level;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_tasks_master_skill_l4 ON tasks_master;
        CREATE TRIGGER trg_tasks_master_skill_l4
        BEFORE INSERT OR UPDATE OF skill_id ON tasks_master
        FOR EACH ROW
        EXECUTE FUNCTION check_tasks_master_skill_is_l4();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_tasks_master_skill_l4 ON tasks_master")
    op.execute("DROP FUNCTION IF EXISTS check_tasks_master_skill_is_l4()")
    op.alter_column("tasks_master", "skill_id", nullable=True)
