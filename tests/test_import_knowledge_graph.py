"""Импорт графа знаний: битый граф не должен попасть в БД."""

import importlib.util
import pathlib
import sys

import pytest

_PATH = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "import_knowledge_graph.py"
_spec = importlib.util.spec_from_file_location("import_knowledge_graph", _PATH)
IKG = importlib.util.module_from_spec(_spec)
sys.modules["import_knowledge_graph"] = IKG
_spec.loader.exec_module(IKG)


def node(id_, level, parent=None, name="Узел"):
    return IKG.normalise({"id": id_, "level": level, "parent_id": parent, "name_ru": name})


def good_graph():
    return [
        node("G5_SEC01", "L1"),
        node("G5_T01", "L2", "G5_SEC01"),
        node("G5_S01_01", "L3", "G5_T01"),
        node("G5_S01_01_01", "L4", "G5_S01_01"),
    ]


class TestValidate:
    def test_connected_graph_passes(self):
        assert IKG.validate(good_graph()) == []

    def test_missing_parent_caught(self):
        g = [node("G5_T01", "L2", "НЕТ_ТАКОГО")]
        assert any("отсутствует" in p for p in IKG.validate(g))

    def test_level_gap_caught(self):
        # L4 не может висеть прямо на L2 — это разрыв иерархии.
        g = [node("G5_SEC01", "L1"), node("G5_T01", "L2", "G5_SEC01"),
             node("G5_X", "L4", "G5_T01")]
        assert any("разрыв иерархии" in p for p in IKG.validate(g))

    def test_root_with_parent_caught(self):
        g = [node("A", "L1"), node("B", "L1", "A")]
        assert any("не должно быть родителя" in p for p in IKG.validate(g))

    def test_duplicate_id_caught(self):
        g = [node("A", "L1"), node("A", "L1")]
        assert any("дубль" in p for p in IKG.validate(g))

    def test_bad_level_caught(self):
        assert any("недопустимый уровень" in p for p in IKG.validate([node("A", "L9")]))

    def test_empty_name_caught(self):
        assert any("пустое имя" in p for p in IKG.validate([node("A", "L1", name="")]))

    def test_orphan_below_root_caught(self):
        assert any("нет родителя" in p for p in IKG.validate([node("A", "L2")]))


class TestNormalise:
    def test_importance_clamped(self):
        assert IKG.normalise({"id": "A", "level": "L1", "importance": 99})["importance"] == 10
        assert IKG.normalise({"id": "A", "level": "L1", "importance": -5})["importance"] == 1

    def test_level_uppercased(self):
        assert IKG.normalise({"id": "A", "level": "l4"})["level"] == "L4"

    def test_empty_parent_becomes_none(self):
        assert IKG.normalise({"id": "A", "level": "L1", "parent_id": ""})["parent_id"] is None

    def test_name_fallback(self):
        assert IKG.normalise({"id": "A", "level": "L1", "name": "Имя"})["name_ru"] == "Имя"


class TestSummary:
    def test_counts_by_level(self):
        s = IKG.summarise(good_graph())
        assert s == {"L1": 1, "L2": 1, "L3": 1, "L4": 1}


class TestLoad:
    def test_json_list(self, tmp_path):
        p = tmp_path / "g.json"
        p.write_text('[{"id":"A","level":"L1","name_ru":"Раздел"}]', encoding="utf-8")
        assert IKG.load_rows(p)[0]["id"] == "A"

    def test_json_wrapped(self, tmp_path):
        p = tmp_path / "g.json"
        p.write_text('{"knowledge_hierarchy":[{"id":"A","level":"L1"}]}', encoding="utf-8")
        assert len(IKG.load_rows(p)) == 1

    def test_csv(self, tmp_path):
        p = tmp_path / "g.csv"
        p.write_text("id,level,name_ru\nA,L1,Раздел\n", encoding="utf-8")
        assert IKG.load_rows(p)[0]["level"] == "L1"
