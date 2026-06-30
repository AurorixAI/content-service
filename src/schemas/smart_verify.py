"""Pydantic contracts for Smart Verify pipeline (compute + distractors)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SmartVerifyResponse(BaseModel):
    """LLM output from code_execution compute step."""

    sympy_compatible_string: str = Field(
        ...,
        description="SymPy expression, e.g. Eq(2*x - 4, 10) or simplified expression",
    )
    absolute_correct_answer: str = Field(
        ...,
        description="Final answer computed via Python/SymPy (school notation)",
    )
    step_by_step_solution: str = Field(
        ...,
        description="Step-by-step solution for student / distractor prompts",
    )


class DistractorItem(BaseModel):
    value: str = Field(..., description="Wrong answer (distractor)")
    error_logic: str = Field(
        ...,
        description="Pedagogical explanation of the student mistake",
    )


class DistractorGenerationResponse(BaseModel):
    distractors: list[DistractorItem] = Field(..., min_length=1, max_length=4)


class PedagogyItemReview(BaseModel):
    index: int = Field(..., ge=0, le=5)
    status: str = Field(
        ...,
        description="ok | rewrite | reject_value",
    )
    error_logic: str = Field(
        default="",
        description="Improved mistake description when status=rewrite",
    )
    issue: str = Field(default="", description="Why reject_value")


class PedagogyReviewResponse(BaseModel):
    items: list[PedagogyItemReview] = Field(..., min_length=1, max_length=4)
    overall: str = Field(..., description="pass | needs_regen")


class TextVerifyResponse(BaseModel):
    """LLM output for text-route verify (no code_execution)."""

    absolute_correct_answer: str = Field(
        ...,
        description="Final answer in school notation",
    )
    step_by_step_solution: str = Field(
        ...,
        description="Brief reasoning for student / distractor prompts",
    )
    confidence: str = Field(
        default="medium",
        description="high | medium | low",
    )
