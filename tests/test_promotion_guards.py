"""Заслоны промоушена: чужой идентификатор не должен исчезать молча."""
from src.pipeline.staging import PromotionReport, id_taken_by_other_book

BOOK = "91bdaef1-b905-40f6-b01d-cf0a14be2fab"
OTHER = "184640af-64e7-47af-a974-8b8112e6ffb2"


class TestIdTakenByOtherBook:
    def test_free_id_is_not_taken(self):
        assert id_taken_by_other_book({}, "G5_TB_1_1", BOOK) is False

    def test_same_book_is_not_collision(self):
        # Повторный прогон той же книги: `ON CONFLICT DO NOTHING` — то, что надо.
        owners = {"G5_TB_1_1": {BOOK}}
        assert id_taken_by_other_book(owners, "G5_TB_1_1", BOOK) is False

    def test_other_book_is_collision(self):
        # В проде три учебника 5 класса делят префикс `G5_TB`.
        owners = {"G5_TB_1_1": {OTHER}}
        assert id_taken_by_other_book(owners, "G5_TB_1_1", BOOK) is True

    def test_shared_with_other_book_is_collision(self):
        owners = {"G5_TB_1_1": {BOOK, OTHER}}
        assert id_taken_by_other_book(owners, "G5_TB_1_1", BOOK) is True

    def test_orphan_task_counts_as_foreign(self):
        # Задача есть в tasks_master, но моста в textbook_tasks нет: чья она —
        # неизвестно. 3 094 задачи прода вообще без source_reference.
        owners = {"G5_TB_1_1": {None}}
        assert id_taken_by_other_book(owners, "G5_TB_1_1", BOOK) is True

    def test_uuid_object_compared_by_value(self):
        import uuid

        owners = {"G5_TB_1_1": {BOOK}}
        assert id_taken_by_other_book(owners, "G5_TB_1_1", uuid.UUID(BOOK)) is False


class TestPromotionReport:
    def test_collision_counter_is_reported(self):
        rep = PromotionReport(dry_run=True, blocked_id_taken=3)
        assert rep.as_dict()["blocked_id_taken"] == 3

    def test_blocked_tasks_are_not_counted_as_promoted(self):
        rep = PromotionReport(dry_run=False, candidates=10, promoted=7, blocked_id_taken=3)
        d = rep.as_dict()
        assert d["promoted"] + d["blocked_id_taken"] == d["candidates"]
