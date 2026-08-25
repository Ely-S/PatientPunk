"""Structured treatment-linked extraction values."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

DOSAGE_FIELD = "dosage"


class TreatmentValuePair(BaseModel):
    """Validated boundary object for a ``treatment: value`` LLM entry."""

    model_config = ConfigDict(frozen=True)

    treatment: str
    value: str

    @field_validator("treatment", "value")
    @classmethod
    def _strip_nonempty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("treatment and value must be non-empty")
        return stripped

    @classmethod
    def from_text(cls, text: str) -> TreatmentValuePair | None:
        """Parse one ``treatment: value`` entry, returning None when unlinked."""
        if not isinstance(text, str):
            return None
        treatment, delimiter, value = text.partition(":")
        if not delimiter:
            return None
        try:
            return cls.model_validate({"treatment": treatment, "value": value})
        except ValidationError:
            return None

    def render(self) -> str:
        """Return the stable serialized representation used in JSON and CSV."""
        return f"{self.treatment}: {self.value}"


def normalize_dosage_pairs(values: list[str]) -> list[str]:
    """Keep normalized dosage entries that identify treatment and dose."""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        pair = TreatmentValuePair.from_text(raw)
        if pair is None:
            continue
        rendered = TreatmentValuePair(
            treatment=pair.treatment.lower(),
            value=pair.value.lower(),
        ).render()
        if rendered not in seen:
            seen.add(rendered)
            normalized.append(rendered)
    return normalized
