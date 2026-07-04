"""Pydantic schemas for A1 comment coding."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SCHEMA_VERSION = "comment_coding_v0.1"


class StrictBaseModel(BaseModel):
    """Base model with strict extra-field handling for eval stability."""

    model_config = ConfigDict(extra="forbid")


class Confidence(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class SkipReason(str, Enum):
    removed_deleted = "removed_deleted"
    too_short = "too_short"
    no_target_author_claim = "no_target_author_claim"
    non_patient_or_other_person_only = "non_patient_or_other_person_only"
    not_english = "not_english"
    moderation_or_meta = "moderation_or_meta"
    unclear_or_insufficient = "unclear_or_insufficient"
    other = "other"


class ClaimType(str, Enum):
    symptom = "symptom"
    diagnosis = "diagnosis"
    medication_or_treatment = "medication_or_treatment"
    test_or_measurement = "test_or_measurement"
    timeline_or_course = "timeline_or_course"
    functional_impact = "functional_impact"
    trigger_or_exacerbating_factor = "trigger_or_exacerbating_factor"
    recovery_or_improvement = "recovery_or_improvement"
    healthcare_access = "healthcare_access"
    other_health_experience = "other_health_experience"


class Experiencer(str, Enum):
    self = "self"
    other_person = "other_person"
    general = "general"
    unclear = "unclear"


class Assertion(str, Enum):
    present = "present"
    absent = "absent"
    uncertain = "uncertain"
    question = "question"
    hypothetical = "hypothetical"


class EvidenceSpan(StrictBaseModel):
    quote: str = Field(
        min_length=1,
        description="Short direct quote from TARGET_COMMENT supporting this claim.",
    )
    source: Literal["target_comment"] = Field(
        description="Evidence must come from TARGET_COMMENT, not context comments."
    )


class TargetClaim(StrictBaseModel):
    claim_type: ClaimType
    raw_text: str = Field(
        min_length=1,
        description="Plain-language claim as stated or adopted by the target author.",
    )
    normalized_label: str | None = Field(
        description="Canonical label when obvious, otherwise null."
    )
    experiencer: Experiencer
    assertion: Assertion
    confidence: Confidence
    evidence: list[EvidenceSpan] = Field(min_length=1)


class CommentCodingResult(StrictBaseModel):
    schema_version: Literal["comment_coding_v0.1"] = Field(
        description="Must be comment_coding_v0.1."
    )
    prompt_version: Literal["comment_coder_v0.1"] = Field(
        description="Must be comment_coder_v0.1."
    )
    comment_id: str = Field(min_length=1)
    source_line: int = Field(ge=1)
    is_codeable: bool = Field(
        description="True only when TARGET_COMMENT contains at least one target-author health claim."
    )
    skip_reason: SkipReason | None = Field(
        description="Reason for skipping when is_codeable is false, otherwise null."
    )
    target_author_claims: list[TargetClaim] = Field(
        description="Claims stated or explicitly adopted by the TARGET_COMMENT author."
    )
    used_context: bool = Field(
        description="True when context changed interpretation of the target comment."
    )
    context_comment_ids_used: list[str] = Field(
        description="Context comment IDs actually needed to interpret the target."
    )
    attribution_confidence: Confidence = Field(
        description="Confidence that extracted claims belong to TARGET_COMMENT author."
    )
    ambiguity_notes: str | None = Field(
        description="Brief uncertainty note, or null when no note is needed."
    )

    @model_validator(mode="after")
    def _validate_codeable_shape(self) -> "CommentCodingResult":
        if self.is_codeable:
            if self.skip_reason is not None:
                raise ValueError("skip_reason must be null when is_codeable is true")
            if not self.target_author_claims:
                raise ValueError("codeable comments must include at least one claim")
        else:
            if self.skip_reason is None:
                raise ValueError("skip_reason is required when is_codeable is false")
            if self.target_author_claims:
                raise ValueError("skipped comments must not include target_author_claims")

        if not self.used_context and self.context_comment_ids_used:
            raise ValueError("context_comment_ids_used must be empty when used_context is false")
        if self.used_context and not self.context_comment_ids_used:
            raise ValueError("used_context requires at least one context comment id")
        return self

