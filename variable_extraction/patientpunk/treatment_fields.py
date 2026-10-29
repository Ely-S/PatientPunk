"""Structured treatment-linked extraction values."""

from __future__ import annotations

from pydantic import BaseModel, ValidationError, field_validator

DOSAGE_FIELD = "dosage"


class TreatmentValuePair(BaseModel):
    """A treatment and one detail about it, written as ``treatment: value``.

    The extraction model reports dosages this way, for example ``naltrexone: 5mg`` or
    ``vitamin d: 1000iu``. Both parts are trimmed and must be non-empty.
    """

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
    """Lowercased ``treatment: dose`` entries, each once, in the order first seen."""
    pairs = (TreatmentValuePair.from_text(raw) for raw in values)
    # dict.fromkeys drops repeats like a set but keeps order, so output is stable across runs.
    return list(dict.fromkeys(
        TreatmentValuePair(treatment=pair.treatment.lower(), value=pair.value.lower()).render()
        for pair in pairs if pair is not None
    ))
