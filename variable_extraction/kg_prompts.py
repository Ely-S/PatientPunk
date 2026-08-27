"""Prompt and response schema definitions for KG claim extraction.

The claim models below are the single source of truth: they generate the JSON schema
the model is constrained by, the field list in the instructions, and the validation
`parse_claims` applies to the response. Adding a claim type means adding one class here.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union, get_args, get_origin

import dspy
from pydantic import BaseModel, ConfigDict, Field, field_validator

RELATIONS = ("TREATS", "CO_OCCURS_WITH", "CAUSED_BY", "SUPPORTS", "CONTRADICTS")

# Fields every claim carries. Everything else a claim model declares is payload.
ENVELOPE = ("local_id", "claim_type", "source_span", "confidence")


def _to_float(v: object) -> float | None:
    """A confidence the model wrote as prose ("high") is dropped, not fatal."""
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


class ClaimBase(BaseModel):
    # Unknown keys are KEPT -- they are signal about what the model wants to say --
    # but counted in parse_claims so prompt/schema drift shows up in the run summary.
    model_config = ConfigDict(extra="allow")

    local_id: str = ""
    source_span: str = ""
    confidence: float | None = None

    _coerce_confidence = field_validator("confidence", mode="before")(_to_float)

    @classmethod
    def payload_fields(cls) -> list[str]:
        return [n for n in cls.model_fields if n not in ENVELOPE]

    @classmethod
    def primary_field(cls) -> str:
        """The first REQUIRED payload key -- the free-text claim in the author's words."""
        return next(n for n in cls.payload_fields() if cls.model_fields[n].is_required())


class Attribute(ClaimBase):
    claim_type: Literal["attribute"] = "attribute"
    attribute_text: str
    age: str | None = None
    sex: str | None = None
    ethnicity: str | None = None
    location: str | None = None
    location_country: str | None = None
    location_us_state: str | None = None
    occupation: str | None = None
    functional_state: str | None = None
    family_history: str | None = None
    healthcare_system: str | None = None
    insurance_status: str | None = None
    vaccination_status: str | None = None
    clinical_trial_participation: str | None = None


class Diagnostic(ClaimBase):
    claim_type: Literal["diagnostic"] = "diagnostic"
    condition_text: str
    diagnosis_status: str | None = None
    provider_type: str | None = None
    test_used: str | None = None
    age_at_diagnosis: str | None = None
    misdiagnosis: str | None = None


class Symptom(ClaimBase):
    claim_type: Literal["symptom"] = "symptom"
    symptom_text: str
    severity: str | None = None
    duration: str | None = None
    trajectory: str | None = None
    triggers: str | None = None
    frequency: str | None = None


class TreatmentResponse(ClaimBase):
    claim_type: Literal["treatment_response"] = "treatment_response"
    treatment_text: str
    dose: str | None = None
    duration: str | None = None
    response: str | None = None
    benefits: str | None = None
    side_effects: str | None = None
    sentiment: str | None = None


class Insight(ClaimBase):
    claim_type: Literal["insight"] = "insight"
    belief_text: str
    hypothesis_type: str | None = None
    patient_expressed_confidence: str | None = None


Claim = Annotated[
    Union[Attribute, Diagnostic, Symptom, TreatmentResponse, Insight],  # noqa: UP007
    Field(discriminator="claim_type"),
]

# claim_type -> model, for lookups in the extractor and the compare report.
CLAIM_TYPES: dict[str, type[ClaimBase]] = {
    m.model_fields["claim_type"].default: m
    for m in (Attribute, Diagnostic, Symptom, TreatmentResponse, Insight)
}


class Edge(BaseModel):
    """One relationship between two locally identified claims."""

    from_: str = Field(alias="from")
    to: str
    relation: Literal[RELATIONS]  # type: ignore[valid-type]
    confidence: float | None = None

    _coerce_confidence = field_validator("confidence", mode="before")(_to_float)

    @field_validator("relation", mode="before")
    @classmethod
    def _upper(cls, v: object) -> object:
        return v.strip().upper() if isinstance(v, str) else v


def _literal_values(annotation: object) -> tuple[str, ...]:
    """The allowed members of a Literal field, looking through `| None` and friends."""
    if get_origin(annotation) is Literal:
        return tuple(str(a) for a in get_args(annotation))
    for arg in get_args(annotation):
        if values := _literal_values(arg):
            return values
    return ()


def _field_doc(name: str, model: type[ClaimBase]) -> str:
    field = model.model_fields[name]
    if field.is_required():
        return f"{name} (REQUIRED)"
    values = _literal_values(field.annotation)
    return f"{name} (one of: {' | '.join(values)})" if values else name


def build_instructions() -> str:
    """Build the extraction instructions from the claim models."""
    types_doc = "\n".join(
        f'  "{ctype}": {{'
        + ", ".join(_field_doc(n, model) for n in model.payload_fields())
        + "}"
        for ctype, model in CLAIM_TYPES.items()
    )
    return f"""You extract structured CLAIMS from a patient's own account of their illness.

A claim is one atomic thing the author says about THEMSELVES, anchored to a verbatim
quote from the text. Emit as many claims as the text supports -- do not summarise, do
not merge two statements into one claim, do not invent.

CLAIM TYPES and their keys (omit any key you cannot evidence from the text):
{types_doc}

RULES
1. source_span MUST be copied VERBATIM from the post -- an exact substring, not a paraphrase.
2. The REQUIRED key is free text taken from the author's own wording. The other keys are
   extracted ALONGSIDE it, never instead of it. A claim with only the REQUIRED key is fine
   and is better than a dropped claim. Never write a placeholder ("not specified", "unknown",
   "none mentioned") into a key you cannot evidence -- omit the key entirely instead.
3. FACTS vs BELIEFS. What happened to the author (diagnoses, symptoms, treatments and their
   outcomes) are facts -> attribute/diagnostic/symptom/treatment_response. What the author
   thinks, theorises, suspects, or hopes is a BELIEF -> "insight", never a fact-bearing claim.
   Example: "my POTS is caused by MCAS" is an insight, not a diagnostic claim.
4. Only claims about the AUTHOR. Skip anything about their spouse, child, friend, or a study
   population.
5. confidence: 0.0-1.0, how clearly the text supports the claim.
6. edges link two claims YOU emitted, by local_id: TREATS (treatment -> symptom/condition),
   CO_OCCURS_WITH, CAUSED_BY (cause -> effect), SUPPORTS, CONTRADICTS. Omit if none apply.
7. Demographic attribute keys (ethnicity, location_country, location_us_state,
   healthcare_system, insurance_status, vaccination_status, clinical_trial_participation)
   must come from an EXPLICIT statement, never inferred from spelling, idiom, or context.
   healthcare_system is the TYPE of system/payer only -- "NHS", "private insurance",
   "Medicare", "uninsured". It is NOT which clinic, provider, or care step the author used
   (a GP visit, an ER visit, a waitlist, a referral); those belong in the REQUIRED text field
   or provider_type on a diagnostic claim, never in healthcare_system.
   vaccination_status: e.g. "unvaccinated", "2 doses Pfizer".
8. local_id: short unique ids ("c1", "c2", ...) you assign to each claim you emit; edges
   reference these ids.

If the text contains nothing about the author's own health, return no claims and no edges."""


class ExtractClaims(dspy.Signature):
    """Extract typed, source-grounded claims and relations from a patient post."""

    post_text: str = dspy.InputField(desc="a patient's post, verbatim")
    claims: list[Claim] = dspy.OutputField(
        desc="atomic claims about the author, each anchored to a verbatim source_span")
    edges: list[Edge] = dspy.OutputField(
        desc="relations between emitted claims, by local_id; empty if none apply")
