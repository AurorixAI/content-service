#!/usr/bin/env python3
"""Перепрогнать отдельные параграфы книги, не трогая остальные.

Нужен, когда правка касается конкретных страниц: чинить один параграф дешевле,
чем гонять книгу целиком. Особенно сейчас — резюме прогона сломано (B16:
`paragraph_has_tasks` смотрит в `tasks_master`, а конвейер пишет в
`tasks_staging`), поэтому обычный повторный запуск оплатил бы всю книгу заново.

Старые строки этих параграфов в `tasks_staging` удаляются перед прогоном:
`ON CONFLICT` разошёлся бы по `task_id`, а номера задач после переизвлечения
могут смениться — иначе останется смесь двух прогонов.

    docker exec content-worker python /app/scripts/rerun_paragraphs.py \\
        --textbook-id <uuid> --pdf /textbooks/book.pdf --paragraphs 1.2 1.3
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import uuid

# Работает и в контейнере (/app), и из корня репозитория на хосте.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from src.core.job_state import JobStateManager  # noqa: E402
from src.pipeline.db_writer import _engine  # noqa: E402
from src.pipeline.orchestrator import DigitizationOrchestrator  # noqa: E402


def purge(textbook_id: str, paragraphs: list[str]) -> int:
    with _engine().begin() as conn:
        res = conn.execute(
            text("""DELETE FROM tasks_staging
                    WHERE textbook_id = CAST(:tb AS UUID)
                      AND paragraph_number = ANY(:paras)
                      AND promoted_at IS NULL"""),
            {"tb": textbook_id, "paras": paragraphs},
        )
        return res.rowcount or 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--textbook-id", required=True)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--paragraphs", nargs="+", required=True)
    ap.add_argument("--class", dest="class_level", type=int, default=5)
    ap.add_argument("--keep-old", action="store_true",
                    help="не удалять прежние строки staging по этим параграфам")
    args = ap.parse_args()

    if not args.keep_old:
        n = purge(args.textbook_id, args.paragraphs)
        print(f"удалено прежних строк staging: {n}")

    job_id = str(uuid.uuid4())
    JobStateManager().create(
        job_id=job_id, textbook_id=args.textbook_id, class_level=args.class_level,
        source_type="pdf", source_path=args.pdf,
    )
    orch = DigitizationOrchestrator(
        job_id=job_id,
        textbook_id=args.textbook_id,
        class_level=args.class_level,
        target_paragraphs=set(args.paragraphs),
    )
    print(f"перепрогон §{', §'.join(args.paragraphs)} (job={job_id}, run={orch.run_id})")
    written = orch.run_pdf(args.pdf)
    print(f"записано в staging: {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
