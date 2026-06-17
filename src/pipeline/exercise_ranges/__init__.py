"""Unified exercise-range registry for all textbooks."""

from src.pipeline.exercise_ranges.registry import (
    exercise_range,
    expected_count,
    get_ranges,
    has_ranges,
    page_end_override,
    parse_exercise_num,
    parse_paragraph_key,
    task_id_prefix,
)

__all__ = [
    "exercise_range",
    "expected_count",
    "get_ranges",
    "has_ranges",
    "page_end_override",
    "parse_exercise_num",
    "parse_paragraph_key",
    "task_id_prefix",
]
