"""Артефакты стадий, адресуемые по хэшу входа (инвариант И4)."""

import json
import tempfile
from pathlib import Path

import pytest

from src.pipeline.artifacts import ArtifactStore, stage_key


@pytest.fixture
def store(tmp_path):
    return ArtifactStore(tmp_path)


class TestStageKey:
    def test_same_input_same_key(self):
        assert stage_key("extract", {"a": 1}) == stage_key("extract", {"a": 1})

    def test_key_is_order_independent(self):
        """Порядок ключей словаря не должен менять адрес артефакта."""
        assert stage_key("extract", {"a": 1, "b": 2}) == stage_key("extract", {"b": 2, "a": 1})

    def test_different_input_different_key(self):
        assert stage_key("extract", {"a": 1}) != stage_key("extract", {"a": 2})

    def test_stage_is_part_of_the_key(self):
        assert stage_key("extract", {"a": 1}) != stage_key("validate", {"a": 1})

    def test_version_bump_invalidates(self):
        assert stage_key("extract", {"a": 1}, version="1") != stage_key("extract", {"a": 1}, version="2")

    def test_prompt_is_part_of_the_key(self):
        """Правка промпта обязана инвалидировать кэш.

        Иначе «улучшение промпта» тихо вернёт старый результат — самый
        неприятный вид ложного успеха.
        """
        a = stage_key("extract", {"p": 1}, prompt="ВАРИАНТ A")
        b = stage_key("extract", {"p": 1}, prompt="ВАРИАНТ B")
        assert a != b

    def test_no_prompt_equals_empty_prompt(self):
        assert stage_key("s", {}, prompt=None) == stage_key("s", {}, prompt="")


class TestStore:
    def test_miss_then_hit(self, store):
        assert store.get("extract", "deadbeef") is None
        store.put("extract", "deadbeef", {"tasks": [1, 2]})
        got = store.get("extract", "deadbeef")
        assert got is not None and got.value == {"tasks": [1, 2]}

    def test_meta_carries_creation_time(self, store):
        art = store.put("extract", "k1", "v")
        assert art.created_at is not None

    def test_corrupt_artifact_is_ignored_not_raised(self, store):
        store.put("extract", "k2", "v")
        path = store._path("extract", "k2")
        path.write_text("{это не json", encoding="utf-8")
        assert store.get("extract", "k2") is None

    def test_no_tmp_files_left_behind(self, store):
        store.put("extract", "k3", {"big": "value"})
        assert list(store.root.rglob("*.tmp")) == []

    def test_unicode_survives_round_trip(self, store):
        store.put("extract", "k4", {"текст": "формула $\\frac{1}{2}$"})
        assert store.get("extract", "k4").value["текст"] == "формула $\\frac{1}{2}$"


class TestCached:
    def test_computes_once(self, store):
        calls = []
        def compute():
            calls.append(1)
            return {"n": 1}
        v1, hit1 = store.cached("extract", {"page": 5}, compute)
        v2, hit2 = store.cached("extract", {"page": 5}, compute)
        assert (hit1, hit2) == (False, True)
        assert v1 == v2
        assert len(calls) == 1

    def test_prompt_change_recomputes(self, store):
        calls = []
        def compute():
            calls.append(1)
            return len(calls)
        store.cached("extract", {"p": 1}, compute, prompt="A")
        _, hit = store.cached("extract", {"p": 1}, compute, prompt="B")
        assert hit is False
        assert len(calls) == 2

    def test_force_recomputes_and_overwrites(self, store):
        seq = iter([{"v": 1}, {"v": 2}])
        compute = lambda: next(seq)
        store.cached("extract", {"p": 1}, compute)
        v, hit = store.cached("extract", {"p": 1}, compute, force=True)
        assert hit is False and v == {"v": 2}
        # Перегон не создаёт вторую истину — читается новое значение.
        v3, hit3 = store.cached("extract", {"p": 1}, compute)
        assert hit3 is True and v3 == {"v": 2}

    def test_diff_keys_lists_stage_contents(self, store):
        store.cached("extract", {"p": 1}, lambda: 1)
        store.cached("extract", {"p": 2}, lambda: 2)
        store.cached("validate", {"p": 1}, lambda: 3)
        assert len(store.diff_keys("extract")) == 2
        assert len(store.diff_keys("validate")) == 1

    def test_diff_keys_on_missing_stage(self, store):
        assert store.diff_keys("nothing") == []
