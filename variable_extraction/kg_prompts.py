"""Prompt and response schema definitions for KG claim extraction."""

from __future__ import annotations

import dspy
from pydantic import BaseModel, Field

# claim_type -> (primary free-text key, structured keys)
CLAIM_TYPES: dict[str, tuple[str, tuple[str, ...]]] = {
    "attribute": ("attribute_text", (
        "age", "sex", "ethnicity", "location", "location_country", "location_us_state",
        "occupation", "functional_state", "family_history", "healthcare_system",
        "insurance_status", "vaccination_status", "clinical_trial_participation")),
    "diagnostic": ("condition_text", (
        "diagnosis_status", "provider_type", "test_used", "age_at_diagnosis", "misdiagnosis")),
    "symptom": ("symptom_text", (
        "severity", "duration", "trajectory", "triggers", "frequency")),
    "treatment_response": ("treatment_text", (
        "dose", "duration", "response", "benefits", "side_effects", "sentiment")),
    "insight": ("belief_text", ("hypothesis_type", "patient_expressed_confidence")),
}

RELATIONS = {"TREATS", "CO_OCCURS_WITH", "CAUSED_BY", "SUPPORTS", "CONTRADICTS"}


def build_instructions() -> str:
    """Build the extraction instructions from the claim response contract."""
    blocks = []
    for ctype, (primary, extras) in CLAIM_TYPES.items():
        keys = ", ".join([f"{primary} (REQUIRED)", *extras])
        blocks.append(f'  "{ctype}": {{{keys}}}')
    types_doc = "\n".join(blocks)
    return f"""You extract structured CLAIMS from a patient's own account of their illness.

A claim is one atomic thing the author says about THEMSELVES, anchored to a verbatim
quote from the text. Emit as many claims as the text supports -- do not summarise, do
not merge two statements into one claim, do not invent.

CLAIM TYPES and their payload keys (omit any key you cannot evidence from the text):
{types_doc}

RULES
1. source_span MUST be copied VERBATIM from the post -- an exact substring, not a paraphrase.
2. The REQUIRED *_text key is free text taken from the author's own wording. Structured keys
   are extracted ALONGSIDE it, never instead of it. A claim with only the *_text key is fine
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
   (a GP visit, an ER visit, a waitlist, a referral); those belong in the *_text field or
   provider_type on a diagnostic claim, never in healthcare_system.
   vaccination_status: e.g. "unvaccinated", "2 doses Pfizer".
8. local_id: short unique ids ("c1", "c2", ...) you assign to each claim you emit; edges
   reference these ids.

If the text contains nothing about the author's own health, return no claims and no edges."""


class Claim(BaseModel):
    """One typed claim returned by the extraction prompt."""

    local_id: str = ""
    claim_type: str
    confidence: float | str | None = None
    source_span: str = ""
    payload: dict = Field(default_factory=dict)


class Edge(BaseModel):
    """One relationship between two locally identified claims."""

    from_: str = Field(alias="from")
    to: str
    relation: str
    confidence: float | str | None = None


class ExtractClaims(dspy.Signature):
    """Extract typed, source-grounded claims and relations from a patient post."""

    post_text: str = dspy.InputField(desc="a patient's post, verbatim")
    claims: list[Claim] = dspy.OutputField(
        desc="atomic claims about the author, each anchored to a verbatim source_span")
    edges: list[Edge] = dspy.OutputField(
        desc="relations between emitted claims, by local_id; empty if none apply")
