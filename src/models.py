"""Pydantic models for validating LLM responses."""
from typing import Literal

from pydantic import BaseModel


class ClassificationResult(BaseModel):
    """Validated sentiment classification from LLM."""
    sentiment: Literal["positive", "negative", "mixed", "neutral"]
    signal: Literal["strong", "moderate", "weak", "n/a"]
    side_effects: list[str] = []
