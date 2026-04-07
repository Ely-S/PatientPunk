"""
patientpunk.schema
~~~~~~~~~~~~~~~~~~
Typed wrappers around PatientPunk schema JSON files.

A *Schema* combines a base schema manifest with an optional extension schema
(e.g. ``covidlonghaulers_schema.json``) into a single object with a clean
Python API.  Every script previously loaded schemas by hand; this centralises
that logic.

Example
-------
>>> schema = Schema.from_file(Path("schemas/covidlonghaulers_schema.json"))
>>> print(schema.schema_id)
covidlonghaulers_v1
>>> for name, field in schema.extension_fields.items():
...     print(name, field.confidence)
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FieldDefinition:
    """Metadata for a single extraction field."""

    name: str
    description: str
    confidence: str                # "high" | "medium" | "low"
    source: str                    # "base" | "base_optional" | "extension" | "llm_discovered"
    patterns: list[str] = field(default_factory=list)
    icd10: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)   # any other schema keys

    def __repr__(self) -> str:
        return (
            f"FieldDefinition(name={self.name!r}, source={self.source!r}, "
            f"confidence={self.confidence!r}, patterns={len(self.patterns)})"
        )


# ---------------------------------------------------------------------------
# Schema class
# ---------------------------------------------------------------------------

class Schema:
    """
    A PatientPunk extraction schema.

    Combines the base schema manifest with an extension schema to produce a
    unified view of all available fields.

    Attributes
    ----------
    schema_id : str
        Unique identifier (e.g. ``"covidlonghaulers_v1"``).
    target_subreddit : str | None
        The subreddit this schema targets, if specified.
    base_fields : dict[str, FieldDefinition]
        Fields defined in the base schema (always present).
    extension_fields : dict[str, FieldDefinition]
        Fields added by the extension schema.
    all_fields : dict[str, FieldDefinition]
        Merged view: base + extension, extension takes precedence on collision.
    """

    # Default location of base_schema.json relative to this file.
    _DEFAULT_BASE = Path(__file__).parent.parent / "schemas" / "base_schema.json"

    def __init__(
        self,
        schema_id: str,
        target_subreddit: str | None,
        base_fields: dict[str, FieldDefinition],
        extension_fields: dict[str, FieldDefinition],
        raw: dict,
    ) -> None:
        self.schema_id = schema_id
        self.target_subreddit = target_subreddit
        self.base_fields = base_fields
        self.extension_fields = extension_fields
        self.all_fields: dict[str, FieldDefinition] = {**base_fields, **extension_fields}
        self._raw = raw

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_file(
        cls,
        extension_path: Path,
        base_path: Path | None = None,
    ) -> "Schema":
        """
        Load a Schema from an extension schema JSON file.

        Parameters
        ----------
        extension_path:
            Path to the extension schema (e.g. ``schemas/covidlonghaulers_schema.json``).
        base_path:
            Path to ``base_schema.json``.  Defaults to the sibling ``schemas/``
            directory relative to this module.
        """
        if base_path is None:
            base_path = cls._DEFAULT_BASE

        with open(extension_path, encoding="utf-8") as f:
            ext_raw: dict = json.load(f)

        base_raw: dict = {}
        if base_path.exists():
            with open(base_path, encoding="utf-8") as f:
                base_raw = json.load(f)
        else:
            warnings.warn(
                f"Base schema not found at {base_path}. "
                f"Only extension fields will be available.",
                stacklevel=2,
            )

        schema_id = ext_raw.get("schema_id", extension_path.stem)
        target_subreddit = ext_raw.get("_target_subreddit")

        base_fields = cls._parse_fields(base_raw, source_prefix="base")
        extension_fields = cls._parse_fields(ext_raw, source_prefix="extension")

        # Mark base_optional fields activated by the extension
        activated = set(ext_raw.get("include_base_fields", []))
        for name in list(base_fields):
            fd = base_fields[name]
            if fd.source == "base_optional" and name not in activated:
                # Remove base_optional fields not activated by this extension
                del base_fields[name]

        return cls(
            schema_id=schema_id,
            target_subreddit=target_subreddit,
            base_fields=base_fields,
            extension_fields=extension_fields,
            raw=ext_raw,
        )

    @classmethod
    def _parse_fields(
        cls,
        raw: dict,
        source_prefix: str,
    ) -> dict[str, FieldDefinition]:
        """Parse ``fields`` / ``extension_fields`` / ``base_optional_fields`` from a raw dict."""
        result: dict[str, FieldDefinition] = {}

        # Base schema uses "fields" and "base_optional_fields"
        for section, source in [
            ("fields", source_prefix),
            ("base_optional_fields", "base_optional"),
            ("extension_fields", source_prefix),
        ]:
            for name, meta in raw.get(section, {}).items():
                if not isinstance(meta, dict):
                    continue
                # Skip internal/metadata-only entries
                if name.startswith("_"):
                    continue
                result[name] = FieldDefinition(
                    name=name,
                    description=meta.get("description", ""),
                    confidence=meta.get("confidence", "medium"),
                    source=source,
                    patterns=list(meta.get("patterns", [])),
                    icd10=meta.get("icd10"),
                    extra={
                        k: v for k, v in meta.items()
                        if k not in {"description", "confidence", "patterns", "icd10"}
                    },
                )

        return result

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def field_names(self, source: str | None = None) -> list[str]:
        """
        Return field names, optionally filtered by *source*.

        Parameters
        ----------
        source:
            One of ``"base"``, ``"base_optional"``, ``"extension"``,
            ``"llm_discovered"``, or ``None`` for all.
        """
        if source is None:
            return list(self.all_fields)
        return [n for n, f in self.all_fields.items() if f.source == source]

    def to_dict(self) -> dict:
        """Return the raw extension schema dict."""
        return dict(self._raw)

    def __repr__(self) -> str:
        return (
            f"Schema(id={self.schema_id!r}, "
            f"base={len(self.base_fields)}, "
            f"extension={len(self.extension_fields)})"
        )
