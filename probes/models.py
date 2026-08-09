"""Shared data contracts for second-pass probes.

The models in this module deliberately know nothing about a probe's domain.
Probe-specific values live in :class:`Claim.values`; the engine owns only
identity, provenance, and mechanical integrity checks.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Reject undeclared fields so provider output cannot silently drift."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class UnitStatus(StrEnum):
    """Lifecycle state of one bounded provider input."""

    PLANNED = "planned"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class AttemptStatus(StrEnum):
    """State of one provider response or transport attempt."""

    # A response is written as received before JSON or claim validation.
    RECEIVED = "received"
    ACCEPTED = "accepted"
    VALIDATION_FAILED = "validation_failed"
    TRANSPORT_FAILED = "transport_failed"


class CohortMember(StrictModel):
    """One ordered row returned by a probe's read-only cohort query."""

    # This is a join key, not a Reddit username. Raw identity never enters the
    # probe database.
    author_hash: str = Field(min_length=1)
    target: str | None = None


class SourceWindow(StrictModel):
    """Private source text supplied to a provider for one unit.

    ``source_window_id`` is stable for the same source identity and normalized
    text. The text and source IDs are quote-bearing private data and must stay
    in the per-probe database.
    """

    source_window_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class RunConfig(StrictModel):
    """Every request setting that can change a run's answer or cost."""

    provider: str = Field(min_length=1)
    base_url: str | None = None
    model: str = Field(min_length=1)
    temperature: float = Field(ge=0)
    max_tokens: int = Field(gt=0)
    reasoning_effort: str | None = None
    service_tier: str | None = None
    provider_routing: dict[str, Any] = Field(default_factory=dict)
    evidence_config: dict[str, Any] = Field(default_factory=dict)


class ProbeRun(StrictModel):
    """Immutable identity for one private probe database run.

    ``unit_key`` deliberately does not include validator identity; a unit is
    the same requested work even when acceptance rules change. The enclosing
    run identity records those rules through the probe/spec hashes.
    """

    run_id: str = Field(min_length=1)
    probe: str = Field(min_length=1)
    spec_hash: str = Field(min_length=1)
    cohort_hash: str = Field(min_length=1)
    source_fingerprint: str = Field(min_length=1)
    unit_set_hash: str = Field(min_length=1)
    config: RunConfig
    created_at: datetime


class Unit(StrictModel):
    """One bounded LLM input assembled from a cohort member's windows."""

    unit_key: str = Field(min_length=1)
    author_hash: str = Field(min_length=1)
    target: str | None = None
    windows: list[SourceWindow] = Field(min_length=1)
    character_count: int = Field(gt=0)
    status: UnitStatus = UnitStatus.PLANNED

    @model_validator(mode="after")
    def windows_are_unique_and_counted(self) -> "Unit":
        """Keep source windows distinct and account for exact input size."""
        window_ids = [window.source_window_id for window in self.windows]
        if len(window_ids) != len(set(window_ids)):
            raise ValueError("source_window_id must be unique within a unit")
        if self.character_count != sum(len(window.text) for window in self.windows):
            raise ValueError("character_count must equal selected window text")
        return self


class Usage(StrictModel):
    """Provider usage and known cost reported for one attempt."""

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)
    provider_cost: float | None = Field(default=None, ge=0)


class Attempt(StrictModel):
    """Auditable provider result recorded before claim validation.

    ``response_body`` is private raw provider output, including malformed JSON.
    A transport failure may have no response body, but its billing uncertainty
    must be explicit rather than being mistaken for a free request.
    """

    unit_key: str = Field(min_length=1)
    attempt_no: int = Field(gt=0)
    status: AttemptStatus
    response_body: str | None = None
    response_sha256: str | None = Field(default=None, min_length=1)
    cache_key: str | None = None
    usage: Usage | None = None
    cache_hit: bool = False
    billing_uncertain: bool = False
    error: str | None = None
    recorded_at: datetime

    @model_validator(mode="after")
    def attempt_state_is_auditable(self) -> "Attempt":
        """Require enough metadata to account for every response or failure."""
        if self.status != AttemptStatus.TRANSPORT_FAILED:
            if self.response_body is None or self.response_sha256 is None:
                raise ValueError("a provider response requires body and checksum")
        if self.status == AttemptStatus.TRANSPORT_FAILED and not self.error:
            raise ValueError("a transport failure requires an error")
        if (
            self.status == AttemptStatus.TRANSPORT_FAILED
            and self.usage is None
            and not self.billing_uncertain
        ):
            raise ValueError("unknown transport billing must be marked uncertain")
        return self


class EvidenceAnchor(StrictModel):
    """One non-empty quote supporting a field in a probe claim."""

    field_path: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class Claim(StrictModel):
    """Generic source-anchored result emitted by a probe-specific schema.

    ``values`` is intentionally opaque to the engine. The probe validates its
    semantic payload before normalizing it here; the engine only checks source
    membership, duplicate claims, anchors, and placeholders.
    """

    claim_id: str = Field(min_length=1)
    unit_key: str = Field(min_length=1)
    source_window_id: str = Field(min_length=1)
    included: bool
    values: dict[str, Any] = Field(min_length=1)
    evidence: list[EvidenceAnchor] = Field(min_length=1)

    @model_validator(mode="after")
    def evidence_paths_are_unique(self) -> "Claim":
        """Avoid competing evidence anchors for one declared field path."""
        paths = [anchor.field_path for anchor in self.evidence]
        if len(paths) != len(set(paths)):
            raise ValueError("each field_path may have only one evidence anchor")
        return self
