"""Structured treatment-linked extraction values."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

DOSAGE_FIELD = "dosage"
DOSAGE_TREATMENT_FIELD = "dosage_treatment"
DOSAGE_VALUE_FIELD = "dosage_value"

TREATMENT_PAIR_DERIVED_FIELDS = [
    DOSAGE_TREATMENT_FIELD,
    DOSAGE_VALUE_FIELD,
]


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


def _normalize_pairs(
    values: list[str],
    *,
    normalize_value: Callable[[str], str],
) -> list[str]:
    """Normalize and deduplicate treatment-linked values from a new extraction."""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        pair = TreatmentValuePair.from_text(raw)
        if pair is None:
            continue
        rendered = TreatmentValuePair(
            treatment=pair.treatment.lower(),
            value=normalize_value(pair.value),
        ).render()
        if rendered not in seen:
            seen.add(rendered)
            normalized.append(rendered)
    return normalized


def normalize_dosage_pairs(values: list[str]) -> list[str]:
    """Keep only dosage entries that identify both treatment and dose."""
    return _normalize_pairs(values, normalize_value=str.lower)


def decompose_treatment_pairs(
    cell: str,
    *,
    treatment_field: str,
    value_field: str,
    sep: str = " | ",
    normalize_value: Callable[[str], str] | None = None,
) -> dict[str, str]:
    """Split a multi-value pair cell into aligned treatment and value columns.

    Bare legacy values remain available in the value column with a blank
    treatment. New extraction records reject those values before export.
    """
    treatments: list[str] = []
    values: list[str] = []
    for entry in (cell or "").split(sep):
        entry = entry.strip()
        if not entry:
            continue
        pair = TreatmentValuePair.from_text(entry)
        if pair is None:
            treatment = ""
            value = entry
        else:
            treatment = pair.treatment
            value = pair.value
        if normalize_value is not None:
            value = normalize_value(value)
        treatments.append(treatment)
        values.append(value)
    return {
        treatment_field: sep.join(treatments),
        value_field: sep.join(values),
    }
