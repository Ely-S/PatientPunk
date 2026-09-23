"""
doses.py — One row per dose the author states they took, per treatment report.

Runs after the sentiment pipeline. Reads treatment_reports for one drug (latest report
per post), sends each report to the model with the shared context (the parent post) and
the shared exclusion names, and writes report_doses; runs append, and report_doses_latest
shows each report's newest run. Amounts are stored as stated (a range keeps its low and
high); an explicit route without an amount keeps both null. This requires a fresh
database; existing dose tables are not migrated.

The run itself (report loading, batching, the pool, the split retry) is pipeline/report_context.py;
this module keeps the dose object, the parse function, and the prompt. Rows are
written through utilities.db.ReportWriter.write_doses.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from pipeline.report_context import (
    DEFAULT_PARENT_CHARS,
    DEFAULT_SOLO_ABOVE_CHARS,
    Step,
    StepSummary,
    response_items,
    run_report_step,
    serialize_batch,
)
from prompts.dose_config import OUTCOMES, ROUTE_CATEGORIES, dose_system_prompt
from utilities import MODEL_STRONG, LLMParseError

# Units are stored as the author wrote them. This map is NOT applied at write time; it is
# the helper analyses call when they need comparable amounts (normalize_unit below).
UNIT_SYNONYMS = {
    "mcg": "mcg", "ug": "mcg", "µg": "mcg", "μg": "mcg", "microgram": "mcg", "micrograms": "mcg",
    "mg": "mg", "milligram": "mg", "milligrams": "mg",
    "g": "g", "gram": "g", "grams": "g",
    "ml": "ml", "mls": "ml", "milliliter": "ml", "milliliters": "ml", "millilitre": "ml", "millilitres": "ml", "cc": "ml",
    "l": "l", "liter": "l", "liters": "l", "litre": "l", "litres": "l",
    "iu": "iu", "i.u.": "iu", "international unit": "iu", "international units": "iu",
}


def normalize_unit(unit: str | None) -> str | None:
    """Canonical unit for a stored one ("mL" -> "ml", "milligrams" -> "mg"), or None when unknown or absent."""
    if not unit:
        return None
    return UNIT_SYNONYMS.get(unit.strip().lower())


TOKENS_PER_ITEM = 400

class DoseValue(BaseModel):
    """A stated amount, or an explicit route whose amount was not reported."""

    model_config = ConfigDict(frozen=True)

    low: float | None = Field(default=None, gt=0)
    high: float | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, max_length=40)  # as the author wrote it; None = bare number
    route: Literal["oral mucosal", "swallowed oral", "nasal mucosal", "injection", "other explicit route"] | None = None
    outcome: Literal["positive", "negative", "neutral", "unclear"] | None = None
    quote: str | None = None

    @model_validator(mode="before")
    @classmethod
    def coerce(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        raw_unit = str(data.get("unit") or "").strip()
        data["unit"] = None if raw_unit.lower() in {"", "null", "none", "unspecified", "unknown"} else raw_unit
        if data.get("route") not in ROUTE_CATEGORIES:
            data["route"] = None
        if data.get("outcome") not in OUTCOMES:
            data["outcome"] = None
        quote = data.get("quote")
        data["quote"] = quote.strip() if isinstance(quote, str) and quote.strip() else None
        return data

    @model_validator(mode="after")
    def check_range(self) -> DoseValue:
        if self.low is None or self.high is None:
            if self.low is not None or self.high is not None:
                raise ValueError("low and high must both be present or both be null")
            if self.route is None or not self.quote:
                raise ValueError("an unknown amount requires an explicit route and its quote")
            if self.unit is not None:
                raise ValueError("unit must be null when the amount is unknown")
        elif self.high < self.low:
            raise ValueError("high must be greater than or equal to low")
        return self


def parse_dose_response(raw: str, expected_ids: list[int]) -> tuple[dict[int, list[DoseValue]], int]:
    """Doses per item id, and how many dose objects did not validate."""
    result: dict[int, list[DoseValue]] = {}
    dropped = 0
    for item_id, obj in response_items(raw, expected_ids).items():
        doses: list[DoseValue] = []
        seen: set[tuple] = set()
        raw_doses = obj.get("doses")
        if not isinstance(raw_doses, list):  # missing or malformed: the batch is split and retried, nothing is written
            raise LLMParseError("\"doses\" must be an array")
        for raw_dose in raw_doses:
            try:
                dose = DoseValue.model_validate(raw_dose)
            except ValidationError:
                dropped += 1
                continue
            key = (dose.low, dose.high, dose.unit, dose.route, dose.outcome, dose.quote)
            if key in seen:
                continue
            seen.add(key)
            doses.append(dose)
        result[item_id] = doses
    return result, dropped


def run_dose_extraction(
    client,
    db_path: Path,
    drug: str,
    *,
    aliases: list[str] | None = None,
    excluded_compounds: list[str] | None = None,
    model: str = MODEL_STRONG,
    workers: int = 8,
    batch_size: int = 8,
    parent_chars: int | None = DEFAULT_PARENT_CHARS,
    solo_above_chars: int | None = DEFAULT_SOLO_ABOVE_CHARS,
    limit: int | None = None,
) -> StepSummary:
    """Extract doses for every latest report of ``drug`` in ``db_path`` and write report_doses."""

    def setup(conn, aliases: list[str], excluded_compounds: list[str]) -> Step:
        if any(row[1] in {"low", "high"} and row[3] for row in conn.execute("PRAGMA table_info(report_doses)")):
            raise ValueError(
                "This dose step requires nullable amounts in report_doses. "
                "Use a fresh database; existing dose tables are not migrated."
            )
        return Step(
            system=dose_system_prompt(drug, aliases, excluded_compounds),
            payload_fn=serialize_batch,
            parse_fn=parse_dose_response,
            write_fn=lambda writer, context, doses: writer.write_doses(context.report_id, doses),
            tokens_per_item=TOKENS_PER_ITEM,
        )

    return run_report_step(
        client, db_path, drug, extraction_type="report_doses", setup_fn=setup,
        aliases=aliases, excluded_compounds=excluded_compounds, model=model, workers=workers,
        batch_size=batch_size, parent_chars=parent_chars, solo_above_chars=solo_above_chars, limit=limit,
    )
