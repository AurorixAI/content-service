"""
Ручной запуск post-processing по всем классам (или конкретным).

Использование:
  python run_post_processing_all.py               # все классы 5-8
  python run_post_processing_all.py --classes 6 7 # только G6 и G7
"""
from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import create_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("run_post_processing_all")

sys.path.insert(0, "/app")

from src.core.config import get_settings
from src.pipeline.post_processing import (
    generate_missing_skills,
    generate_missing_difficulties,
    fill_missing_distractors,
)


def run_for_class(engine, class_level: int) -> dict:
    log.info("=" * 60)
    log.info("Post-processing G%d", class_level)
    log.info("=" * 60)

    result = {"class": class_level, "new_tasks": 0, "distractors": 0}

    s1 = generate_missing_skills(engine, class_level)
    log.info("Step 1 (missing skills tasks): +%d", s1)
    result["new_tasks"] += s1

    s2 = generate_missing_difficulties(engine, class_level)
    log.info("Step 2 (missing A/B/C levels): +%d", s2)
    result["new_tasks"] += s2

    s3 = fill_missing_distractors(engine, class_level)
    log.info("Step 3 (distractors): %d updated", s3)
    result["distractors"] = s3

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--classes", nargs="*", type=int, default=[5, 6, 7, 8],
        help="Классы для обработки (default: 5 6 7 8)",
    )
    args = ap.parse_args()

    db_url = get_settings().database_url
    engine = create_engine(db_url)

    totals = {"new_tasks": 0, "distractors": 0}
    for cls in sorted(args.classes):
        r = run_for_class(engine, cls)
        totals["new_tasks"]   += r["new_tasks"]
        totals["distractors"] += r["distractors"]

    log.info("=" * 60)
    log.info(
        "ИТОГО: +%d новых задач | %d дистракторов",
        totals["new_tasks"], totals["distractors"],
    )
    log.info("=" * 60)


if __name__ == "__main__":
    main()
