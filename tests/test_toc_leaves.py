"""Отбор листов оглавления: содержательные разделы против служебных.

Регрессия: фильтр `level >= 2` молча выбрасывал содержательные листы первого
уровня. На textzadachi5 так терялась «6. Задачи на повторение» — 15 страниц.
"""

from src.pipeline.orchestrator import content_leaves, _is_synthetic_number


def entry(number, title, level=1, page_start=1, page_end=10, parent_number=""):
    """Форма записи ровно как её отдаёт db_writer.load_toc: parent_number, не parent_id."""
    return {"number": number, "title": title, "level": level,
            "page_start": page_start, "page_end": page_end,
            "parent_number": parent_number}


class TestSyntheticNumber:
    def test_underscore_is_synthetic(self):
        assert _is_synthetic_number("_30")

    def test_real_number_is_not(self):
        assert not _is_synthetic_number("6")
        assert not _is_synthetic_number("5.3")

    def test_empty_is_synthetic_safe(self):
        assert not _is_synthetic_number("")
        assert not _is_synthetic_number(None)


class TestContentLeaves:
    def test_numbered_level1_leaf_is_kept(self):
        # Тот самый случай: «6. Задачи на повторение», 15 страниц задач.
        toc = [entry("6", "Задачи на повторение", level=1, page_start=77, page_end=91)]
        keep, skip = content_leaves(toc)
        assert [t["number"] for t in keep] == ["6"]
        assert skip == []

    def test_unnumbered_back_matter_is_skipped(self):
        toc = [
            entry("_30", "Ответы и советы", level=1, page_start=92, page_end=102),
            entry("_31", "Приложения", level=1, page_start=103, page_end=108),
        ]
        keep, skip = content_leaves(toc)
        assert keep == []
        assert [t["number"] for t in skip] == ["_30", "_31"]

    def test_level2_always_kept_even_if_synthetic(self):
        toc = [entry("_5", "Без номера, но подраздел", level=2)]
        keep, skip = content_leaves(toc)
        assert len(keep) == 1 and skip == []

    def test_real_book_shape(self):
        toc = [
            entry("_1", "Введение", level=1),
            entry("1.1", "Сложение", level=2),
            entry("1.2", "Умножение", level=2),
            entry("6", "Задачи на повторение", level=1),
            entry("_30", "Ответы и советы", level=1),
            entry("_31", "Приложения", level=1),
        ]
        keep, skip = content_leaves(toc)
        assert [t["number"] for t in keep] == ["1.1", "1.2", "6"]
        assert [t["number"] for t in skip] == ["_1", "_30", "_31"]

    def test_empty_input(self):
        assert content_leaves([]) == ([], [])


class TestParentDetection:
    """Родитель определяется по parent_number — это единственное, что отдаёт load_toc."""

    def test_chapter_with_children_is_not_a_leaf(self):
        toc = [
            entry("1", "Натуральные числа", level=1, page_start=4, page_end=25),
            entry("1.1", "Сложение", level=2, page_start=4, page_end=6, parent_number="1"),
            entry("1.2", "Умножение", level=2, page_start=7, page_end=10, parent_number="1"),
        ]
        keep, skip = content_leaves(toc)
        assert [t["number"] for t in keep] == ["1.1", "1.2"]
        assert skip == [], "глава не «пропущена», она просто не лист"

    def test_pages_are_not_processed_twice(self):
        # Регрессия: без определения родителя глава и её подпараграфы шли бы
        # в обработку вместе, и страницы 4–6 распознавались дважды.
        toc = [
            entry("1", "Глава", level=1, page_start=4, page_end=6),
            entry("1.1", "Подпараграф", level=2, page_start=4, page_end=6, parent_number="1"),
        ]
        keep, _ = content_leaves(toc)
        pages = [(t["page_start"], t["page_end"]) for t in keep]
        assert pages == [(4, 6)], "диапазон страниц должен встречаться один раз"

    def test_full_textzadachi5_shape(self):
        toc = [entry("_1", "Введение", level=1)]
        for ch, subs in (("1", 7), ("2", 6), ("3", 2), ("4", 4), ("5", 3)):
            toc.append(entry(ch, f"Глава {ch}", level=1))
            for i in range(1, subs + 1):
                toc.append(entry(f"{ch}.{i}", "Подпараграф", level=2, parent_number=ch))
        toc.append(entry("6", "Задачи на повторение", level=1, page_start=77, page_end=91))
        toc.append(entry("_30", "Ответы и советы", level=1))
        toc.append(entry("_31", "Приложения", level=1))

        keep, skip = content_leaves(toc)
        assert len(keep) == 23, f"22 подпараграфа + §6, получено {len(keep)}"
        assert "6" in [t["number"] for t in keep]
        assert [t["number"] for t in skip] == ["_1", "_30", "_31"]
