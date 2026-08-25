"""Structured treatment-linked dosage and administration-route values."""

from __future__ import annotations

import re
from collections.abc import Callable
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

DOSAGE_FIELD = "dosage"
DOSAGE_TREATMENT_FIELD = "dosage_treatment"
DOSAGE_VALUE_FIELD = "dosage_value"

ADMINISTRATION_ROUTE_FIELD = "administration_route"
ADMINISTRATION_ROUTE_TREATMENT_FIELD = "administration_route_treatment"
ADMINISTRATION_ROUTE_VALUE_FIELD = "administration_route_value"

TREATMENT_PAIR_DERIVED_FIELDS = [
    DOSAGE_TREATMENT_FIELD,
    DOSAGE_VALUE_FIELD,
    ADMINISTRATION_ROUTE_TREATMENT_FIELD,
    ADMINISTRATION_ROUTE_VALUE_FIELD,
]


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
    "by mouth": AdministrationRoute.ORAL,
    "pill": AdministrationRoute.ORAL,
    "capsule": AdministrationRoute.ORAL,
    "sublingal": AdministrationRoute.SUBLINGUAL,
    "under tongue": AdministrationRoute.SUBLINGUAL,
    "under the tongue": AdministrationRoute.SUBLINGUAL,
    "shot": AdministrationRoute.INJECTION,
    "injected": AdministrationRoute.INJECTION,
    "iv": AdministrationRoute.INTRAVENOUS,
    "iv infusion": AdministrationRoute.INTRAVENOUS,
    "intravenous infusion": AdministrationRoute.INTRAVENOUS,
    "im": AdministrationRoute.INTRAMUSCULAR,
    "im injection": AdministrationRoute.INTRAMUSCULAR,
    "sc": AdministrationRoute.SUBCUTANEOUS,
    "sq": AdministrationRoute.SUBCUTANEOUS,
    "sub q": AdministrationRoute.SUBCUTANEOUS,
    "subcutaneous injection": AdministrationRoute.SUBCUTANEOUS,
    "nasal": AdministrationRoute.INTRANASAL,
    "nasal spray": AdministrationRoute.INTRANASAL,
    "inhalation": AdministrationRoute.INHALED,
    "inhaler": AdministrationRoute.INHALED,
    "nebulized": AdministrationRoute.INHALED,
    "nebulised": AdministrationRoute.INHALED,
    "skin": AdministrationRoute.TOPICAL,
    "cream": AdministrationRoute.TOPICAL,
    "gel": AdministrationRoute.TOPICAL,
    "patch": AdministrationRoute.TRANSDERMAL,
    "transdermal patch": AdministrationRoute.TRANSDERMAL,
    "rectally": AdministrationRoute.RECTAL,
    "vaginally": AdministrationRoute.VAGINAL,
    "eye drops": AdministrationRoute.OPHTHALMIC,
    "ear drops": AdministrationRoute.OTIC,
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


def normalize_administration_route_pairs(values: list[str]) -> list[str]:
    """Keep linked route entries and normalize their route values."""
    return _normalize_pairs(
        values,
        normalize_value=lambda value: normalize_administration_route(value).value,
    )


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
