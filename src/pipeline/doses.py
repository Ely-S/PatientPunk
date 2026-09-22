"""
doses.py — One row per dose the author states they took, per treatment report.

Runs after the sentiment pipeline. Reads treatment_reports for one drug (latest report
per post), sends each report to the model with its parent post as context, and writes
report_doses. Amounts are stored as stated (a range keeps its low and high); every row
carries the sentence it came from.

The mechanics shared with the other per-report steps (the report context query, batching,
the thread-pool loop, the split-on-malformed-reply retry, the alias lookup, the run loop)
live in pipeline/report_context.py; this module keeps only what is dose-specific: the dose
object, the payload and parse functions, and the prompt. Rows are written through
utilities.db.ReportWriter.write_doses.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from pipeline.report_context import (
    DEFAULT_PARENT_CHARS,
    DEFAULT_SOLO_ABOVE_CHARS,
    ReportContext,
    Step,
    StepInputs,
    run_report_step,
)
from prompts.dose_config import OUTCOMES, ROUTE_CATEGORIES, dose_system_prompt
from utilities import MODEL_STRONG, LLMParseError, llm_call, parse_json_array
from utilities.db import ReportWriter

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
    """One stated per-administration amount, as the author wrote it."""

    model_config = ConfigDict(frozen=True)

    low: float = Field(gt=0)
    high: float = Field(gt=0)
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
        if self.high < self.low:
            raise ValueError("high must be greater than or equal to low")
        return self


@dataclass(frozen=True)
class DoseRunSummary:
    run_id: int
    reports: int
    reports_with_doses: int
    dose_rows: int
    failed_reports: int
    dropped_doses: int  # dose objects the model returned that did not validate


def request_payload(batch: list[ReportContext]) -> str:
    items = []
    for i, context in enumerate(batch):
        item: dict[str, object] = {"item_id": i, "report": context.text}
        if context.replying_to:
            item["replying_to"] = context.replying_to
        items.append(item)
    return json.dumps({"items": items}, ensure_ascii=False)


def parse_dose_response(raw: str, expected_ids: list[int]) -> tuple[dict[int, list[DoseValue]], int]:
    """Parse the model's array; returns doses per item id and how many dose objects were dropped."""
    objects = parse_json_array(raw)
    if not all(isinstance(o, dict) for o in objects):
        raise LLMParseError("Response array must contain objects")
    try:
        ids = [int(o.get("item_id")) for o in objects]
    except (TypeError, ValueError) as e:
        raise LLMParseError(f"Non-integer item_id in response: {e}") from e
    if ids != expected_ids:
        raise LLMParseError(f"Response item ids {ids} do not match request {expected_ids}")
    result: dict[int, list[DoseValue]] = {}
    dropped = 0
    for obj in objects:
        doses: list[DoseValue] = []
        seen: set[tuple] = set()
        raw_doses = obj.get("doses") or []
        if not isinstance(raw_doses, list):
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
        result[int(obj["item_id"])] = doses
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
) -> DoseRunSummary:
    """Extract doses for every latest report of ``drug`` in ``db_path`` and write report_doses."""

    def setup(conn: sqlite3.Connection, inputs: StepInputs) -> Step:
        system = dose_system_prompt(drug, inputs.aliases, inputs.excluded_compounds)
        return Step(system, request_payload, parse_dose_response, TOKENS_PER_ITEM, call=llm_call)

    s = run_report_step(
        client, db_path, drug, extraction_type="report_doses", setup_fn=setup, write_fn=ReportWriter.write_doses,
        aliases=aliases, excluded_compounds=excluded_compounds, model=model, workers=workers,
        batch_size=batch_size, parent_chars=parent_chars, solo_above_chars=solo_above_chars, limit=limit,
    )
    return DoseRunSummary(s.run_id, s.reports, s.reports_with_rows, s.rows, s.failed, s.dropped)
