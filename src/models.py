"""Pydantic models for validating LLM responses."""
from typing import Literal

from pydantic import BaseModel


class ClassificationResult(BaseModel):
    """Validated sentiment classification from LLM."""
    sentiment: Literal["positive", "negative", "mixed", "neutral"]
    signal: Literal["strong", "moderate", "weak", "n/a"]
    side_effects: list[str] = []
    # Runtime-only flag (never emitted by the model, never written to the DB):
    # True marks a fallback null produced when the LLM output could not be parsed.
    # Lets the audit sink separate a genuine `signal="n/a"` neutral from a parse
    # failure — the two are otherwise conflated and both vanish at the writer gate.
    parse_failed: bool = False
