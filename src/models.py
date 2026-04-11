"""Pydantic models for validating LLM responses."""
from typing import Literal

from pydantic import BaseModel, model_validator

SENTIMENTS = {"positive", "negative", "mixed", "neutral"}
SIGNALS = {"strong", "moderate", "weak", "n/a"}


class ClassificationResult(BaseModel):
    """Validated sentiment classification from LLM."""
    sentiment: Literal["positive", "negative", "mixed", "neutral"]
    signal: Literal["strong", "moderate", "weak", "n/a"]

    @model_validator(mode="before")
    @classmethod
    def fix_swapped_fields(cls, data):
        if isinstance(data, dict):
            s, g = data.get("sentiment"), data.get("signal")
            if s in SIGNALS and g in SENTIMENTS:
                data["sentiment"], data["signal"] = g, s
        return data
