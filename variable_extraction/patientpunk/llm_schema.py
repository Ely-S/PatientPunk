"""Validation and normalisation for decoded LLM extraction replies.

``parse_json_response`` answers "is this JSON?"; this module answers "is this the
shape we asked for?". Everything past ``parse_extraction`` can assume every field
value is ``list[str] | None`` and that ``suggested_fields`` is a list.

Shaped by what providers actually send. Across 987 cached deepseek-v4-flash
replies the field values arrived as null (31768x), list (1788x), bare str (50x)
and bare int (14x) -- so scalar coercion is the norm, not an edge case, and the
ints were reaching the output as raw ints because the old inline normaliser had
a branch for str but none for int. Five replies sent ``"suggested_fields": null``
where Claude sends ``[]``; that null is what aborted a 1000-record run.

The distinction that matters is *empty* vs *malformed*, because ~47% of records
legitimately extract nothing (short posts) and must not be retried:

- ``fields`` missing entirely -> malformed. Return None; the caller retries.
- ``fields`` present but null/empty -> a legitimately empty extraction.
- ``fields`` present but not an object -> malformed.
- unknown field names -> dropped and counted, never silently passed through.
"""

from __future__ import annotations

from typing import Any

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

__all__ = ["LLMExtraction", "SuggestedField", "parse_extraction"]

# Scalars a field value may arrive as instead of list[str]. bool is excluded on
# purpose: True is not a plausible clinical value and silently becoming "True"
# would be worse than dropping it.
_SCALARS = (str, int, float)


def _coerce_value(val: Any) -> list[str] | None:
    """Normalise one field value to ``list[str] | None``.

    Empty and all-falsy lists collapse to None, matching the pre-existing
    ``[v for v in val if v] or None`` semantics exactly -- coverage percentages
    are computed off this, so a change here would silently move the numbers.
    """
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, _SCALARS):
        text = str(val).strip()
        return [text] if text else None
    if isinstance(val, list):
        out = [
            str(v).strip()
            for v in val
            if v is not None and not isinstance(v, (bool, dict, list)) and str(v).strip()
        ]
        return out or None
    # dict, or anything else: not salvageable as a value.
    return None


class SuggestedField(BaseModel):
    """A field the model proposes adding. Extra keys are kept for discovery.

    The key is ``field_name``, not ``name``: that is what both prompts ask the
    model for (``build_system_prompt`` / ``build_gap_system_prompt``) and what
    ``aggregate_suggestions`` reads back out. ``name`` is accepted as an alias
    only so replies already sitting in the LLM cache still validate.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    field_name: str = Field(validation_alias=AliasChoices("field_name", "name"))
    description: str = ""


class LLMExtraction(BaseModel):
    """The contract: ``{"fields": {...}, "suggested_fields": [...]}``."""

    model_config = ConfigDict(extra="ignore")

    # No default: a reply with no "fields" key at all is malformed, not empty.
    fields: dict[str, list[str] | None]
    suggested_fields: list[SuggestedField] = Field(default_factory=list)

    @field_validator("fields", mode="before")
    @classmethod
    def _normalise_fields(cls, v: Any) -> Any:
        if v is None:
            return {}
        if not isinstance(v, dict):
            raise ValueError("fields must be an object")
        return {str(k): _coerce_value(val) for k, val in v.items()}

    @field_validator("suggested_fields", mode="before")
    @classmethod
    def _normalise_suggestions(cls, v: Any) -> Any:
        if v is None:
            return []
        if isinstance(v, dict):  # a lone suggestion sent unwrapped
            return [v]
        if not isinstance(v, list):
            return []
        # Drop members that cannot be a suggestion rather than failing the record.
        return [
            s for s in v
            if isinstance(s, dict) and (s.get("field_name") or s.get("name"))
        ]


def parse_extraction(
    obj: Any,
    *,
    allowed_fields: set[str] | None = None,
) -> tuple[LLMExtraction, list[str]] | None:
    """Validate a decoded reply.

    Returns ``(extraction, dropped_field_names)``, or None when the reply is
    malformed and worth retrying. Never raises: bad model output is data, not an
    exception, and one bad record must not be able to abort a run.

    ``allowed_fields`` filters hallucinated field names out of ``fields``; the
    dropped names are returned so the caller can report them instead of losing
    them quietly.
    """
    if not isinstance(obj, dict):
        return None
    try:
        model = LLMExtraction.model_validate(obj)
    except ValidationError:
        return None

    dropped: list[str] = []
    if allowed_fields is not None:
        unknown = [k for k in model.fields if k not in allowed_fields]
        if unknown:
            dropped = sorted(unknown)
            model.fields = {k: v for k, v in model.fields.items() if k in allowed_fields}
    return model, dropped
