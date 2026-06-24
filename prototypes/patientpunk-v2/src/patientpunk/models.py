"""
patientpunk.models
~~~~~~~~~~~~~~~~~~
Pydantic v2 models for the discovery pipeline.

These represent the data produced by the field discovery step (discover_fields.py)
and consumed by the variable picker app (apps/discover.py).
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ValidatedField(BaseModel):
    """
    A single candidate field that has passed regex validation (Phase 2 output).

    Matches the structure written by discover_fields.py's validate_candidates step.
    """
    field_name: str
    description: str
    patterns: list[str] = Field(default_factory=list)
    hit_rate: float = 0.0          # fraction of tested examples that matched regex
    examples_tested: int = 0
    confidence: str = "medium"     # low | medium | high
    frequency_hint: str = "occasional"  # common | occasional | rare
    research_value: str = ""
    source: str = "llm_discovered"
    llm_only: bool = False
    extractability_note: str = ""
    allowed_values: list[str] | None = None
    trigger_vocabulary: list[str] = Field(default_factory=list)

    # Coverage is filled in from the field_stats section of the report, not
    # from the validated fields file directly -- default to None until enriched.
    coverage: float | None = None


class PipelineRun(BaseModel):
    """Metadata about the discovery pipeline run."""
    started_at: str = ""
    finished_at: str = ""
    duration_seconds: float = 0.0
    corpus_items: int = 0
    discovery_limit: int | None = None
    base_schema: str = ""


class FieldStat(BaseModel):
    """Per-field stats from the discovery report."""
    regex_hits: int = 0
    llm_filled: int = 0
    total_hits: int = 0
    coverage: float = 0.0         # fraction of corpus items hit
    hit_rate_at_discovery: float = 0.0
    pattern_count: int = 0
    source: str = "llm_discovered"


class DiscoveryReport(BaseModel):
    """
    The full discovery report produced by discover_fields.py.

    Loaded from discovered_field_report_{schema_id}.json.
    """
    pipeline_run: PipelineRun = Field(default_factory=PipelineRun)
    discovery_results: dict[str, Any] = Field(default_factory=dict)
    field_stats: dict[str, FieldStat] = Field(default_factory=dict)
    schema_file: str = ""
    records_file: str = ""
