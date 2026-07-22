"""Pydantic models for validating LLM responses."""
from typing import Literal

from pydantic import BaseModel


class ClassificationResult(BaseModel):
    """Validated sentiment classification from LLM."""
    sentiment: Literal["positive", "negative", "mixed", "neutral"]
    signal: Literal["strong", "moderate", "weak", "n/a"]
    side_effects: list[str] = []
    # "specific" = the author tied this outcome to THIS drug; "collective" = reported for a group
    # that merely includes it ("this stack helped"). Defaults to specific, i.e. prior behaviour.
    attribution: Literal["specific", "collective"] = "specific"
    # Set when the LLM reply could not be parsed. Not a model field, not stored in the DB.
    parse_failed: bool = False

    @classmethod
    def from_llm(cls, data) -> "ClassificationResult":
        """Validate model output, ignoring any parse_failed the model invented.

        parse_failed is ours -- it means "we could not read this reply" -- so only the
        except-path may set it. A non-dict passes through to pydantic so it raises
        ValidationError, which callers already catch and retry per item.
        """
        if isinstance(data, dict):
            data = {k: v for k, v in data.items() if k != "parse_failed"}
        return cls.model_validate(data)
