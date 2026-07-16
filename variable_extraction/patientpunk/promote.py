"""
patientpunk.promote
~~~~~~~~~~~~~~~~~~~~
Promote auto-discovered fields into a curated extension schema.

Field discovery (Phase 3) deliberately writes its results to a throwaway
``discovered_{timestamp}.json`` in temp/ and never merges them into the curated
schema (see patientpunk.discover).  That keeps the curated schema clean,
but it also makes discovered variables a dead end: the next run cannot
deliberately re-extract them, Phase 2's LLM gap-fill never targets them, and
they are not documented in the codebook.

``promote`` is the explicit, opt-in bridge.  It copies selected discovered
fields into a schema's ``extension_fields`` so subsequent runs treat them as
first-class fields (Phase 1 regex + Phase 2 LLM fill) on any data.  Each
promoted field is stamped with ``_promoted_at`` -- which is also the marker that
re-enables Phase 1 regex compilation for it (raw ``llm_discovered`` fields are
skipped by Phase 1 for safety; see patientpunk.biomedical).

Pure functions, no API calls -- unit-testable.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ._utils import find_discovery_reports, load_json


class PromoteResult(BaseModel):
    """Outcome of a promote operation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    output_path: Path | None  # None on dry_run
    added: list[str]
    skipped_existing: list[str]
    filtered_low_coverage: list[str]
    filtered_not_selected: list[str]
    merged_schema: dict

    def summary(self) -> str:
        parts = [f"{len(self.added)} added"]
        if self.skipped_existing:
            parts.append(f"{len(self.skipped_existing)} skipped (already present)")
        if self.filtered_low_coverage:
            parts.append(f"{len(self.filtered_low_coverage)} filtered (low coverage)")
        if self.filtered_not_selected:
            parts.append(f"{len(self.filtered_not_selected)} filtered (not selected)")
        return ", ".join(parts)


def find_latest_discovery(temp_dir: Path, base_schema_id: str) -> tuple[Path, dict] | None:
    """Newest discovery report (by mtime) matching *base_schema_id*, or None."""
    reports = find_discovery_reports(temp_dir, base_schema_id)
    if not reports:
        return None
    return max(reports, key=lambda rp: rp[0].stat().st_mtime)


def resolve_discovered_schema(report: dict, temp_dir: Path) -> Path | None:
    """Resolve the ``schema_file`` referenced by a discovery report.

    Falls back to matching the basename inside *temp_dir* when the recorded path
    is relative or no longer exists at its original location.
    """
    schema_file = report.get("schema_file")
    if not isinstance(schema_file, str) or not schema_file.strip():
        return None
    path = Path(schema_file)
    if path.exists():
        return path
    candidate = temp_dir / path.name
    return candidate if candidate.exists() else None


def _coverage(field_stats: dict | None, name: str) -> float | None:
    if not field_stats:
        return None
    entry = field_stats.get(name)
    if isinstance(entry, dict):
        cov = entry.get("coverage")
        if isinstance(cov, (int, float)):
            return float(cov)
    return None


def promote_discovered_fields(
    target_schema_path: Path,
    discovered_schema: dict,
    field_stats: dict | None = None,
    *,
    min_coverage: float | None = None,
    include: set[str] | None = None,
    exclude: set[str] | None = None,
    overwrite_existing: bool = False,
    output_path: Path | None = None,
    dry_run: bool = False,
) -> PromoteResult:
    """Merge ``discovered_schema['extension_fields']`` into the target schema.

    Each promoted field dict is copied verbatim (preserving all discovery
    metadata -- ``_discovered_at``, ``hit_rate_at_discovery``, ``frequency_hint``,
    ``research_value``, ``llm_only``, ``allowed_values``, ``patterns`` ...) plus
    ``_promoted_at`` / ``_promoted_from`` markers.

    Filters are applied in order: ``include`` allowlist -> ``exclude`` ->
    ``min_coverage`` (vs ``field_stats[name]['coverage']``; a field with no stat
    entry is kept with a warning rather than silently dropped).  Name collisions
    with the target schema are skipped (with a warning) unless
    ``overwrite_existing``.

    Writes the merged schema to ``output_path`` (or back to
    ``target_schema_path`` when ``output_path is None``) unless ``dry_run``.
    """
    target = load_json(target_schema_path)
    if not isinstance(target, dict):
        raise ValueError(f"Target schema is not a JSON object: {target_schema_path}")

    target_ext = dict(target.get("extension_fields") or {})
    base_field_names = set(target.get("include_base_fields") or [])
    discovered_ext = discovered_schema.get("extension_fields") or {}
    from_id = discovered_schema.get("schema_id", "unknown")
    stamped = datetime.now(timezone.utc).isoformat()

    added: list[str] = []
    skipped_existing: list[str] = []
    filtered_low_coverage: list[str] = []
    filtered_not_selected: list[str] = []
    warnings: list[str] = []

    for name, fdata in discovered_ext.items():
        if not isinstance(fdata, dict):
            continue
        # 1. include allowlist
        if include is not None and name not in include:
            filtered_not_selected.append(name)
            continue
        # 2. exclude
        if exclude and name in exclude:
            filtered_not_selected.append(name)
            continue
        # 3. minimum coverage
        if min_coverage is not None:
            cov = _coverage(field_stats, name)
            if cov is None:
                warnings.append(f"  ! no coverage stat for {name!r}; keeping it")
            elif cov < min_coverage:
                filtered_low_coverage.append(name)
                continue
        # 4. collision with the curated schema
        if name in target_ext and not overwrite_existing:
            skipped_existing.append(name)
            warnings.append(
                f"  ! {name!r} already in target schema; skipped (use --overwrite-existing)"
            )
            continue
        if name in base_field_names:
            warnings.append(f"  ! {name!r} also appears in include_base_fields")

        promoted = dict(fdata)  # verbatim copy preserves discovery metadata
        promoted["_promoted_at"] = stamped
        promoted["_promoted_from"] = from_id
        target_ext[name] = promoted
        added.append(name)

    merged = dict(target)
    merged["extension_fields"] = target_ext

    for warning in warnings:
        print(warning)

    out_path: Path | None = None
    if not dry_run:
        out_path = output_path or target_schema_path
        out_path.write_text(
            json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    return PromoteResult(
        output_path=out_path,
        added=added,
        skipped_existing=skipped_existing,
        filtered_low_coverage=filtered_low_coverage,
        filtered_not_selected=filtered_not_selected,
        merged_schema=merged,
    )
