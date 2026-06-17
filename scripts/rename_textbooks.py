#!/usr/bin/env python3
"""
Canonical user-facing names for textbooks (shown on platform: title + authors).

Verified against PDF paths, TOC insert scripts, and publisher metadata.
Idempotent — safe to re-run.

Usage:
    docker exec content-worker python /app/scripts/rename_textbooks.py
    docker exec content-worker python /app/scripts/rename_textbooks.py --dry-run
"""
from __future__ import annotations

import argparse
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings

# title        — primary label in teacher UI (exam creation)
# subtitle     — edition / series (API detail, future UI)
# display_name — full canonical string (COALESCE fallback)
# authors      — shown under title in UI
TEXTBOOKS: list[dict] = [
    {
        "id": "184640af-64e7-47af-a974-8b8112e6ffb2",
        "title": "Математика 5 класс — Виленкин",
        "subtitle": "Мнемозина, 2013",
        "display_name": "Математика 5 класс — Виленкин (Мнемозина, 2013)",
        "authors": ["Н.Я. Виленкин", "В.И. Жохов", "А.С. Чесноков", "С.И. Шварцбурд"],
        "publisher": "Мнемозина",
        "edition": "2013",
        "total_pages": 285,
        "country": "RU",
    },
    {
        "id": "5630a994-061d-4c20-9863-fe049c8059fb",
        "title": "Математика 5 класс — IDUM, часть 1",
        "subtitle": "IDUM, 2020",
        "display_name": "Математика 5 класс — IDUM, часть 1 (2020)",
        "authors": ["Авторский коллектив IDUM"],
        "publisher": "IDUM",
        "edition": "2020",
        "total_pages": 144,
        "country": "UZ",
    },
    {
        "id": "47167115-5961-4405-bb55-1bda8ce1b687",
        "title": "Математика 5 класс — IDUM, часть 2",
        "subtitle": "Издание 3-е, 2020",
        "display_name": "Математика 5 класс — IDUM, часть 2 (изд. 3-е, 2020)",
        "authors": ["Б.К. Хайдаров"],
        "publisher": "Huquq va Jamiyat",
        "edition": "Издание третье, исправленное и дополненное",
        "total_pages": 144,
        "country": "UZ",
    },
    {
        "id": "351a95c1-5208-4ae9-8323-6d7dd5e8bb82",
        "title": "Математика 6 класс — Виленкин",
        "subtitle": "Мнемозина",
        "display_name": "Математика 6 класс — Виленкин (Мнемозина)",
        "authors": ["Н.Я. Виленкин", "В.И. Жохов", "А.С. Чесноков", "С.И. Шварцбурд"],
        "publisher": "Мнемозина",
        "edition": None,
        "total_pages": 288,
        "country": "UZ",
    },
    {
        "id": "a7585f33-4f43-47b2-8ca6-c4ef6c8020c8",
        "title": "Математика 6 класс — Школьное издание",
        "subtitle": "O'qituvchi, 2017",
        "display_name": "Математика 6 класс — Школьное издание (O'qituvchi, 2017)",
        "authors": ["Учебный коллектив"],
        "publisher": "O'qituvchi",
        "edition": "2017",
        "total_pages": 240,
        "country": "UZ",
    },
    {
        "id": "69fc47e1-7f72-4e79-9bf4-9ee6fb7e9b7f",
        "title": "Алгебра 7 класс — Макарычев",
        "subtitle": "Просвещение, 15-е изд., 2023",
        "display_name": "Алгебра 7 класс — Макарычев (Просвещение, 15-е изд., 2023)",
        "authors": [
            "Ю.Н. Макарычев",
            "М.А. Миндюк",
            "К.И. Нешков",
            "Н.Г. Суворов",
            "С.Б. Суворова",
        ],
        "publisher": "Просвещение",
        "edition": "15-е издание, 2023",
        "total_pages": 257,
        "country": "UZ",
    },
    {
        "id": "4b19752a-3d54-4538-b6a6-26ce1fbb48fd",
        "title": "Алгебра 7 класс — Школьное издание",
        "subtitle": "Новое издание, 2022",
        "display_name": "Алгебра 7 класс — Школьное издание (Новое издание, 2022)",
        "authors": ["Авторский коллектив"],
        "publisher": "Новое издание",
        "edition": "2022",
        "total_pages": 192,
        "country": "UZ",
    },
    {
        "id": "e8f3a1b2-7c4d-5e6f-8091-2345678abcde",
        "title": "Алгебра 8 класс — Школьное издание",
        "subtitle": "O'qituvchi, 2019",
        "display_name": "Алгебра 8 класс — Школьное издание (O'qituvchi, 2019)",
        "authors": ["Ш.А. Алимов", "А.Р. Халмухамедов", "М.А. Мирзахмедов"],
        "publisher": "O'qituvchi",
        "edition": "4-е издание",
        "total_pages": 240,
        "country": "UZ",
    },
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)

    with engine.begin() as conn:
        print(f"{'DRY-RUN' if args.dry_run else 'UPDATE'} — {len(TEXTBOOKS)} textbooks\n")
        for tb in TEXTBOOKS:
            row = conn.execute(
                text("""
                    SELECT title, subtitle, display_name, authors
                    FROM textbooks WHERE textbook_id = CAST(:id AS UUID)
                """),
                {"id": tb["id"]},
            ).fetchone()
            if not row:
                print(f"  [SKIP] {tb['id']} — not found")
                continue

            tasks = conn.execute(
                text("""
                    SELECT COUNT(*) FROM tasks_master tm
                    JOIN textbook_toc t ON t.id = tm.toc_id
                    WHERE t.textbook_id = CAST(:id AS UUID)
                """),
                {"id": tb["id"]},
            ).scalar() or 0

            changed = row.title != tb["title"] or row.display_name != tb["display_name"]
            flag = "→" if changed else "="
            print(f"  {flag} {tb['title']}")
            print(f"      authors: {', '.join(tb['authors'])}")
            print(f"      tasks:   {tasks}")

            if args.dry_run:
                continue

            conn.execute(
                text("""
                    UPDATE textbooks SET
                        title = :title,
                        subtitle = :subtitle,
                        display_name = :display_name,
                        authors = :authors,
                        publisher = :publisher,
                        edition = :edition,
                        total_pages = :total_pages,
                        country = :country,
                        tasks_extracted = :tasks,
                        updated_at = NOW()
                    WHERE textbook_id = CAST(:id AS UUID)
                """),
                {
                    "id": tb["id"],
                    "title": tb["title"],
                    "subtitle": tb["subtitle"],
                    "display_name": tb["display_name"],
                    "authors": tb["authors"],
                    "publisher": tb["publisher"],
                    "edition": tb["edition"],
                    "total_pages": tb["total_pages"],
                    "country": tb["country"],
                    "tasks": tasks,
                },
            )

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
