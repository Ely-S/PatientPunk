# ADR-001: Pydantic v2 over dataclasses for boundary objects

**Status:** Accepted
**Date:** 2026-04-08
**Deciders:** Shaun, Eli

## Context

The library used stdlib dataclasses for all data containers (CorpusRecord,
FieldDefinition, PipelineConfig, PhaseResult, PipelineResult). These work
fine internally but provide no validation at boundary points: JSON files
loaded from disk, CLI arguments, config dicts from external callers.

Eli's review flagged the need for validation on boundary objects and
modern Python conventions.

## Decision

Use Pydantic v2 BaseModel for all objects that cross a trust boundary:

- Config objects constructed from CLI args or external callers
- Models deserialized from JSON artifacts on disk
- Objects returned to external consumers of the library

Lightweight internal structures on hot paths may remain as plain
typed classes or NamedTuples where validation overhead matters.

## Consequences

- Pydantic v2 becomes a required dependency.
- `model_validate()` / `model_dump()` replace manual dict wrangling.
- Frozen models (ConfigDict(frozen=True)) replace `@dataclass(frozen=True)`.
- `model_validator(mode="after")` replaces `__post_init__` for construction-time coercion.
- Test assertions for frozen fields must catch pydantic ValidationError, not AttributeError.
