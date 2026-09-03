"""Pydantic models for validating LLM responses."""
from typing import Literal

from pydantic import BaseModel, Field


class SideEffectReport(BaseModel):
    """One side effect and its explicitly reported severity, when stated."""

    side_effect: str
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
    side_effects: list[SideEffectReport] = Field(default_factory=list)
