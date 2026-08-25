"""Structured treatment-linked dosage and administration-route values."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

DOSAGE_FIELD = "dosage"
ADMINISTRATION_ROUTE_FIELD = "administration_route"


class AdministrationRoute(StrEnum):
    """Controlled vocabulary for explicitly stated administration routes."""

    ORAL = "oral"
    SUBLINGUAL = "sublingual"
    BUCCAL = "buccal"
    INJECTION = "injection"
    INTRAVENOUS = "intravenous"
    INTRAMUSCULAR = "intramuscular"
    SUBCUTANEOUS = "subcutaneous"
    INTRADERMAL = "intradermal"
    INTRANASAL = "intranasal"
    INHALED = "inhaled"
    TOPICAL = "topical"
    TRANSDERMAL = "transdermal"
    RECTAL = "rectal"
    VAGINAL = "vaginal"
    SUPPOSITORY = "suppository"
    OPHTHALMIC = "ophthalmic"
    OTIC = "otic"
    OTHER = "other"


ADMINISTRATION_ROUTE_VALUES = tuple(route.value for route in AdministrationRoute)


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


_ROUTE_CLEANUP = re.compile(r"[\s_-]+")
_ROUTE_ALIASES: dict[str, AdministrationRoute] = {
    "sublingal": AdministrationRoute.SUBLINGUAL,
    "shot": AdministrationRoute.INJECTION,
    "iv": AdministrationRoute.INTRAVENOUS,
    "iv infusion": AdministrationRoute.INTRAVENOUS,
    "im": AdministrationRoute.INTRAMUSCULAR,
    "sc": AdministrationRoute.SUBCUTANEOUS,
    "sub q": AdministrationRoute.SUBCUTANEOUS,
}


def normalize_administration_route(value: str) -> AdministrationRoute:
    """Map a model-produced route to the controlled vocabulary."""
    cleaned = _ROUTE_CLEANUP.sub(" ", value.strip().lower())
    if cleaned in _ROUTE_ALIASES:
        return _ROUTE_ALIASES[cleaned]
    try:
        return AdministrationRoute(cleaned)
    except ValueError:
        return AdministrationRoute.OTHER


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


def normalize_administration_route_pairs(values: list[str]) -> list[str]:
    """Keep linked route entries and normalize their route values."""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        pair = TreatmentValuePair.from_text(raw)
        if pair is None:
            continue
        rendered = TreatmentValuePair(
            treatment=pair.treatment.lower(),
            value=normalize_administration_route(pair.value).value,
        ).render()
        if rendered not in seen:
            seen.add(rendered)
            normalized.append(rendered)
    return normalized
