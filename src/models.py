"""Pydantic models for validating LLM responses."""
from typing import Literal

from pydantic import BaseModel, Field, StrictBool


class SideEffectReport(BaseModel):
    """One side effect and its explicitly reported severity, when stated."""

    effect: str  # the author's words for the side effect, e.g. "insomnia"
    severity: Literal[
        "mild",
        "moderate",
        "severe",
        "life_threatening",
    ] | None = None


class ClassificationResult(BaseModel):
    """Validated sentiment classification from LLM."""
    sentiment: Literal["positive", "negative", "mixed", "neutral"]
    signal: Literal["strong", "moderate", "weak", "n/a"]
    personal_use: StrictBool = False
    side_effects: list[SideEffectReport] = Field(default_factory=list)
