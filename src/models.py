"""Pydantic models for validating LLM responses."""
from typing import Literal

from pydantic import BaseModel


class ClassificationResult(BaseModel):
    """Validated sentiment classification from LLM."""
    sentiment: Literal["positive", "negative", "mixed", "neutral"]
    signal: Literal["strong", "moderate", "weak", "n/a"]
    side_effects: list[str] = []
    # Whether the author tied this outcome to THIS drug ("specific") or reported it for a group of
    # treatments that merely includes it ("collective" — "this stack helped"). Recording the basis
    # keeps the outcome AND lets per-drug rates exclude group attributions at query time, instead of
    # forcing a lossy choice in the prompt (judgement 5: group attribution inflates helped ~5%).
    # Defaults to "specific" so a model that omits the field behaves as before.
    attribution: Literal["specific", "collective"] = "specific"
    # Runtime-only flag (never emitted by the model, never written to the DB): True marks a
    # fallback null produced when the LLM output could not be parsed. Lets an audit separate a
    # genuine signal="n/a" neutral from a parse failure — otherwise both vanish at the writer gate.
    parse_failed: bool = False
