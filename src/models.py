"""Pydantic models for validating LLM responses."""
from typing import Literal

from pydantic import BaseModel, StrictBool


class ClassificationResult(BaseModel):
    """Validated sentiment classification from LLM."""
    sentiment: Literal["positive", "negative", "mixed", "neutral"]
    signal: Literal["strong", "moderate", "weak", "n/a"]
    personal_use: StrictBool = False
    side_effects: list[str] = []
