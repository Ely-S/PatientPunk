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
    # Runtime-only (never from the model, never written to the DB): marks a fallback null for an
    # unparseable reply, so an audit can tell one from a genuine signal="n/a" neutral.
    parse_failed: bool = False

    @classmethod
    def from_llm(cls, data) -> "ClassificationResult":
        """Validate model output, ignoring any parse_failed the model invented.

        parse_failed is ours, not the model's: it means "we could not read this reply." A model
        that echoes the schema back — or hallucinates the key — would otherwise set it on a
        perfectly good classification, and the writer gate would drop the row while the audit
        recorded it as a parse failure. Only the except-path may set this flag.

        Anything that isn't a dict (a model answering with `["positive"]` instead of objects) is
        handed to pydantic untouched so it raises ValidationError, which callers already catch and
        retry per item. Reaching for .items() first would turn that into an AttributeError nobody
        handles, and one malformed batch would kill the run.
        """
        if isinstance(data, dict):
            data = {k: v for k, v in data.items() if k != "parse_failed"}
        return cls.model_validate(data)
