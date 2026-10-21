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

_SPECIFIC_ROUTES_BY_BROAD_ROUTE: dict[
    AdministrationRoute, frozenset[AdministrationRoute]
] = {
    AdministrationRoute.INJECTION: frozenset({
        AdministrationRoute.INTRAVENOUS,
        AdministrationRoute.INTRAMUSCULAR,
        AdministrationRoute.SUBCUTANEOUS,
        AdministrationRoute.INTRADERMAL,
    }),
    AdministrationRoute.SUPPOSITORY: frozenset({
        AdministrationRoute.RECTAL,
        AdministrationRoute.VAGINAL,
    }),
}


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


def normalize_administration_route(value: str) -> AdministrationRoute | None:
    """Map a recognized model-produced route to the controlled vocabulary."""
    cleaned = _ROUTE_CLEANUP.sub(" ", value.strip().lower())
    if cleaned in _ROUTE_ALIASES:
        return _ROUTE_ALIASES[cleaned]
    try:
        return AdministrationRoute(cleaned)
    except ValueError:
        return None


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
    """Keep linked routes, rejecting invalid and dominated broad values."""
    pairs: list[tuple[str, AdministrationRoute]] = []
    routes_by_treatment: dict[str, set[AdministrationRoute]] = {}
    for raw in values:
        pair = TreatmentValuePair.from_text(raw)
        if pair is None:
            continue
        treatment = pair.treatment.lower()
        route = normalize_administration_route(pair.value)
        if route is None:
            continue
        pairs.append((treatment, route))
        routes_by_treatment.setdefault(treatment, set()).add(route)

    normalized: list[str] = []
    seen: set[str] = set()
    for treatment, route in pairs:
        specific_routes = _SPECIFIC_ROUTES_BY_BROAD_ROUTE.get(route, frozenset())
        if routes_by_treatment[treatment].intersection(specific_routes):
            continue
        rendered = TreatmentValuePair(
            treatment=treatment,
            value=route.value,
        ).render()
        if rendered not in seen:
            seen.add(rendered)
            normalized.append(rendered)
    return normalized
