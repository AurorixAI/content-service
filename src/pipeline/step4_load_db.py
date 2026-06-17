"""
Step 4 — Load pipeline results into the database
==================================================
Reads importance_classN.json and prerequisites_classN.json,
then upserts into knowledge_hierarchy and skill_prerequisites.

Operations:
  1. UPDATE knowledge_hierarchy SET importance=..., cognitive_type=...
     WHERE id=... AND level='L3'
  2. INSERT INTO skill_prerequisites ... ON CONFLICT DO UPDATE

Запуск (один класс):
  python3 -m src.pipeline.step4_load_db --class 5

Запуск (все классы):
  python3 -m src.pipeline.step4_load_db --all
"""
from __future__ import annotations

import argparse
import json
import logging
import os

from sqlalchemy import create_engine, text

from src.core.config import get_settings

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "curriculum")


def _load_importance(class_level: int) -> None:
    path = os.path.join(DATA_DIR, f"importance_class{class_level}.json")
    if not os.path.exists(path):
        log.error("File not found: %s", path)
        return

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    engine = create_engine(get_settings().database_url)
    updated = 0
    skipped = 0

    with engine.begin() as conn:
        for cluster in data.get("data", []):
            for item in cluster.get("subtopics", []):
                node_id = item.get("node_id")
                importance = item.get("importance")
                cognitive_type = item.get("cognitive_type")

                if not node_id or importance is None:
                    skipped += 1
                    continue

                # Validate cognitive_type against DB check constraint (if any)
                result = conn.execute(
                    text("""
                        UPDATE knowledge_hierarchy
                        SET importance = :imp,
                            cognitive_type = :ctype,
                            updated_at = now()
                        WHERE id = :nid AND level = 'L3'
                    """),
                    {"imp": importance, "ctype": cognitive_type, "nid": node_id},
                )
                if result.rowcount > 0:
                    updated += 1
                else:
                    log.warning("  Node not found or not L3: %s", node_id)
                    skipped += 1

    log.info("Importance class %d: updated=%d skipped=%d", class_level, updated, skipped)


def _load_prerequisites(class_level: int) -> None:
    path = os.path.join(DATA_DIR, f"prerequisites_class{class_level}.json")
    if not os.path.exists(path):
        log.error("File not found: %s", path)
        return

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    edges = data.get("edges", [])
    if not edges:
        log.warning("No edges in %s", path)
        return

    engine = create_engine(get_settings().database_url)
    inserted = 0
    updated = 0
    skipped = 0

    with engine.begin() as conn:
        # Verify all referenced skill_ids exist in knowledge_hierarchy
        all_ids = set()
        for e in edges:
            all_ids.add(e["skill_id"])
            all_ids.add(e["prerequisite_id"])

        existing_ids = set()
        if all_ids:
            rows = conn.execute(
                text("SELECT id FROM knowledge_hierarchy WHERE id = ANY(:ids)"),
                {"ids": list(all_ids)},
            ).fetchall()
            existing_ids = {r[0] for r in rows}

        for e in edges:
            skill_id = e.get("skill_id")
            prereq_id = e.get("prerequisite_id")

            if skill_id not in existing_ids:
                log.warning("  Skipping: skill_id %s not in DB", skill_id)
                skipped += 1
                continue
            if prereq_id not in existing_ids:
                log.warning("  Skipping: prerequisite_id %s not in DB", prereq_id)
                skipped += 1
                continue

            dep_type = e.get("dependency_type", "soft")
            weight = e.get("weight", 1.0)
            criticality = max(1, min(10, int(e.get("criticality", 5))))
            description = e.get("relationship_description", "")

            result = conn.execute(
                text("""
                    INSERT INTO skill_prerequisites
                        (skill_id, prerequisite_id, dependency_type, weight,
                         criticality, relationship_description, discovery_source)
                    VALUES
                        (:sid, :pid, :dtype, :w, :crit, :desc, 'expert')
                    ON CONFLICT (skill_id, prerequisite_id) DO UPDATE SET
                        dependency_type = EXCLUDED.dependency_type,
                        weight = EXCLUDED.weight,
                        criticality = EXCLUDED.criticality,
                        relationship_description = EXCLUDED.relationship_description,
                        discovery_source = 'expert',
                        last_validated_at = now()
                """),
                {
                    "sid": skill_id,
                    "pid": prereq_id,
                    "dtype": dep_type,
                    "w": weight,
                    "crit": criticality,
                    "desc": description,
                },
            )
            if result.rowcount > 0:
                inserted += 1  # covers both INSERT and UPDATE (upsert)

    log.info(
        "Prerequisites class %d: upserted=%d skipped=%d (total edges=%d)",
        class_level, inserted, skipped, len(edges),
    )


def run(class_level: int) -> None:
    log.info("=== Loading class %d into DB ===", class_level)
    _load_importance(class_level)
    _load_prerequisites(class_level)
    log.info("=== Class %d done ===", class_level)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--class", dest="class_level", type=int)
    group.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if args.all:
        for cl in [5, 6, 7, 8, 9]:
            run(cl)
    else:
        run(args.class_level)
