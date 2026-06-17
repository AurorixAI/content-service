"""Fill remaining G6 distractor gaps using AIDistractorGenerator fallback."""
from __future__ import annotations

import json
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, "/app")

from src.core.config import get_settings
from src.pipeline.enrichment import AIDistractorGenerator

IDS = [
    "G6_TB_118–119_1024",
    "G6_TB_89–90_767.1",
    "G6_TB_89–90_767.2",
    "G6_TB_89–90_767.3",
]


def main() -> None:
    engine = create_engine(get_settings().database_url)
    gen = AIDistractorGenerator()

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, question_text, correct_answer, answer_type
                FROM tasks_master WHERE id = ANY(:ids)
            """),
            {"ids": IDS},
        ).mappings().fetchall()

    updated = 0
    for row in rows:
        dmeta = gen.generate(
            row["question_text"],
            row["correct_answer"],
            row["answer_type"],
            count=3,
        )
        if not dmeta:
            print(f"SKIP {row['id']}")
            continue
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET distractor_meta = cast(:dmeta as jsonb)
                    WHERE id = :id
                """),
                {"id": row["id"], "dmeta": json.dumps(dmeta, ensure_ascii=False)},
            )
        print(f"OK {row['id']} -> {[d['value'] for d in dmeta]}")
        updated += 1

    print(f"Updated {updated}/{len(rows)}")


if __name__ == "__main__":
    main()
