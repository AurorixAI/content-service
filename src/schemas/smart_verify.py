"""Pydantic contracts for Smart Verify pipeline (compute + distractors)."""
from __future__ import annotations

from typing import Literal

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


class DistractorItem(BaseModel):
    value: str = Field(..., description="Wrong answer (distractor)")
    error_logic: str = Field(
        ...,
        description="Pedagogical explanation of the student mistake",
    )


class DistractorGenerationResponse(BaseModel):
    # The generator deliberately asks for extra candidates because the
    # deterministic L1-L4 gate may reject some. Only the final validated
    # minimum/target set is persisted (normally 2-3 items).
    distractors: list[DistractorItem] = Field(..., min_length=1, max_length=6)


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
    confidence: str = Field(
        default="medium",
        description="high | medium | low",
    )


class TextAnswerRelationResponse(BaseModel):
    """Whether a unanimous text candidate actually changes the source meaning.

    Three source-blind solves establish a candidate answer.  This compact,
    source-aware comparison is deliberately only an editorial write gate: it
    prevents harmless paraphrases (for example a different grammatical form
    of a unit) from overwriting the original answer.
    """

    relation: Literal[
        "equivalent",
        "candidate_corrects_source",
        "inconclusive",
    ] = Field(
        ...,
        description="equivalent | candidate_corrects_source | inconclusive",
    )
