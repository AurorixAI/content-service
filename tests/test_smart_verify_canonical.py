"""Tests for Smart Verify routing helpers."""
from src.pipeline.smart_verify_common import pick_consensus_canonical


def test_pick_consensus_unanimous():
    winner, unanimous, votes = pick_consensus_canonical(
        ["x = -7/3", "x=-7/3", "x = -7/3"],
        "equation_solution",
    )
    assert unanimous
    assert winner is not None
    assert "-7" in winner
    assert len(votes) == 3


def test_pick_consensus_majority():
    winner, unanimous, _ = pick_consensus_canonical(
        ["5", "5", "99"],
        "exact_number",
    )
    assert not unanimous
    assert winner == "5"


def test_pick_consensus_split():
    winner, unanimous, _ = pick_consensus_canonical(
        ["1", "2", "3"],
        "exact_number",
    )
    assert winner is None
    assert not unanimous


def test_pick_consensus_empty():
    winner, unanimous, votes = pick_consensus_canonical([], "exact_number")
    assert winner is None
    assert not unanimous
    assert votes == []
