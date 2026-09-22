"""
effects.py — One row per effect the author says the drug had on them, per treatment report.

Runs after the sentiment and dose steps. For each latest treatment report of one drug it
sends the report with its parent post and the report's dose rows as context, and writes
report_effects rows (a rerun replaces a report's rows, like report_doses). Every row
carries its sentence; an effect the author ties to a stated dose points at that
report_doses row. The run itself (report loading, batching, the pool, the split retry) is
pipeline/report_context.py; this module keeps the effect object, the payload, the parser,
the write-time checks and the prompt.
"""
from __future__ import annotations

import re
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from pipeline.report_context import (
    DEFAULT_PARENT_CHARS,
    DEFAULT_SOLO_ABOVE_CHARS,
    ReportContext,
    Step,
    StepSummary,
    response_items,
    run_report_step,
    serialize_batch,
)
from prompts.effects_config import ATTRIBUTIONS, DOMAINS, effects_system_prompt
from utilities import MODEL_STRONG, LLMParseError, log
from utilities.db import ReportWriter

TOKENS_PER_ITEM = 500
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# Kept identical to schema.sql so the step also works on databases created before the table existed.
REPORT_EFFECTS_DDL = """
CREATE TABLE IF NOT EXISTS report_effects (
    effect_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id   INTEGER NOT NULL REFERENCES treatment_reports(report_id),
    run_id      INTEGER NOT NULL REFERENCES extraction_runs(run_id),
    ordinal     INTEGER NOT NULL,
    domain      TEXT NOT NULL,
    symptom     TEXT NOT NULL,
    direction   TEXT NOT NULL CHECK (direction IN ('improved', 'worsened', 'no_change', 'mixed')),
    severity    TEXT CHECK (severity IN ('mild', 'moderate', 'severe', 'life_threatening')),
    attribution TEXT NOT NULL CHECK (attribution IN ('target', 'stack', 'unclear', 'other compound')),
    quote       TEXT NOT NULL,
    dose_id     INTEGER REFERENCES report_doses(dose_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_re_report ON report_effects(report_id);
"""
SEVERITIES = ("mild", "moderate", "severe", "life_threatening")


class EffectValue(BaseModel):
    """One effect the author states, as the model returned it after normalisation."""

    model_config = ConfigDict(frozen=True)

    domain: str
    symptom: str
    direction: Literal["improved", "worsened", "no_change", "mixed"]
    severity: Literal["mild", "moderate", "severe", "life_threatening"] | None = None  # only when the author states it
    attribution: Literal["target", "stack", "unclear", "other compound"]
    quote: str
    dose: int | None = None

    @model_validator(mode="before")
    @classmethod
    def coerce(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        for key in ("domain", "symptom", "quote"):
            raw = data.get(key)
            data[key] = raw.strip() if isinstance(raw, str) and raw.strip() else None
        data["domain"] = (data["domain"] or "").lower()
        data["symptom"] = data["symptom"] or data["domain"]  # a row with no symptom word still names its domain
        data["direction"] = str(data.get("direction") or "").strip().lower().replace(" ", "_")
        severity = str(data.get("severity") or "").strip().lower().replace(" ", "_").replace("-", "_")
        data["severity"] = severity if severity in SEVERITIES else None  # anything else is "not stated"
        dose = data.get("dose")
        if isinstance(dose, str) and dose.strip().isdigit():
            dose = int(dose)
        data["dose"] = dose if isinstance(dose, int) and not isinstance(dose, bool) else None
        return data


@dataclass(frozen=True)
class EffectRunSummary(StepSummary):
    quote_drops: int       # effects dropped because their quote is not in the report
    dose_link_drops: int   # dose ids the model returned that were not among the report's listed doses


def load_report_doses(conn: sqlite3.Connection, drug: str) -> tuple[dict[int, list[tuple[int, str]]], int | None]:
    """Each report's dose rows, as (dose_id, quote), and the dose run they came from (a rerun replaces
    a report's rows, so a report has one run's rows)."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'report_doses'").fetchone():
        return {}, None
    doses: dict[int, list[tuple[int, str]]] = {}
    run_ids: set[int] = set()
    for report_id, dose_id, run_id, quote in conn.execute(
        """
        SELECT d.report_id, d.dose_id, d.run_id, d.quote FROM report_doses d
        JOIN treatment_reports tr ON tr.report_id = d.report_id
        JOIN treatment t ON t.id = tr.drug_id
        WHERE lower(t.canonical_name) = lower(?)
        ORDER BY d.report_id, d.ordinal
        """,
        (drug,),
    ):
        doses.setdefault(report_id, []).append((dose_id, quote or ""))
        run_ids.add(run_id)
    return doses, (max(run_ids) if run_ids else None)


def request_payload(batch: list[ReportContext], doses_by_report: dict[int, list[tuple[int, str]]]) -> str:
    """The shared request body, each item also carrying the report's dose rows as ``doses: [{id, quote}]`` when it has any."""

    def doses_for(context: ReportContext) -> dict[str, Any]:
        listed = doses_by_report.get(context.report_id)
        return {"doses": [{"id": dose_id, "quote": quote} for dose_id, quote in listed]} if listed else {}

    return serialize_batch(batch, doses_for)


def parse_effects_response(
    raw: str, expected_ids: list[int], target_names: frozenset[str], domains: frozenset[str] = frozenset(DOMAINS)
) -> tuple[dict[int, list[EffectValue]], int]:
    """Effects per item id, and how many effect objects were dropped.

    The prompt names the drug in the attribution field; the table stores ``target``. A label
    outside the vocabulary is the name of another compound, so ``other compound``; an empty
    one drops the effect. A missing or non-array ``effects`` field is a parse error.
    """
    result: dict[int, list[EffectValue]] = {}
    dropped = 0
    for item_id, obj in response_items(raw, expected_ids).items():
        effects: list[EffectValue] = []
        seen: set[tuple] = set()
        raw_effects = obj.get("effects")
        if not isinstance(raw_effects, list):  # missing or malformed: the whole batch is retried, nothing is written
            raise LLMParseError("\"effects\" must be an array")
        for raw_effect in raw_effects:
            if not isinstance(raw_effect, dict):
                dropped += 1
                continue
            data = dict(raw_effect)
            label = str(data.get("attribution") or "").strip().lower()
            if not label:  # no attribution is not a claim about another compound
                dropped += 1
                continue
            data["attribution"] = "target" if label in target_names else label if label in ATTRIBUTIONS else "other compound"
            try:
                effect = EffectValue.model_validate(data)
            except ValidationError:
                dropped += 1
                continue
            if effect.domain not in domains:
                dropped += 1
                continue
            key = (effect.domain, effect.symptom, effect.direction, effect.severity, effect.attribution, effect.quote, effect.dose)
            if key not in seen:
                seen.add(key)
                effects.append(effect)
        result[item_id] = effects
    return result, dropped


def apply_effect_checks(
    effects: list[EffectValue], report_text: str, listed_dose_ids: set[int]
) -> tuple[list[EffectValue], int, int]:
    """Write-time checks: drop an effect whose quote is not in the report (compared on
    lower-case letters and digits); null a ``dose`` that is not one of the report's listed
    dose ids. Returns the kept effects and the two counts."""
    haystack = _NON_ALNUM.sub("", report_text.lower())
    kept: list[EffectValue] = []
    quote_drops = dose_link_drops = 0
    for effect in effects:
        needle = _NON_ALNUM.sub("", effect.quote.lower())
        if not needle or needle not in haystack:
            quote_drops += 1
            continue
        if effect.dose is not None and effect.dose not in listed_dose_ids:
            dose_link_drops += 1
            effect = effect.model_copy(update={"dose": None})
        kept.append(effect)
    return kept, quote_drops, dose_link_drops


def run_effects_extraction(
    client,
    db_path: Path,
    drug: str,
    *,
    aliases: list[str] | None = None,
    excluded_compounds: list[str] | None = None,
    domains: tuple[str, ...] | list[str] = DOMAINS,
    model: str = MODEL_STRONG,
    workers: int = 8,
    batch_size: int = 8,
    parent_chars: int | None = DEFAULT_PARENT_CHARS,
    solo_above_chars: int | None = DEFAULT_SOLO_ABOVE_CHARS,
    limit: int | None = None,
) -> EffectRunSummary:
    """Extract effects for every latest report of ``drug`` in ``db_path`` and write report_effects rows."""
    domains = tuple(d.strip().lower() for d in domains if d.strip())
    domain_set = frozenset(domains)
    drops: Counter[str] = Counter()

    def setup(conn: sqlite3.Connection, aliases: list[str], excluded_compounds: list[str]) -> Step:
        conn.executescript(REPORT_EFFECTS_DDL)
        if "severity" not in {row[1] for row in conn.execute("PRAGMA table_info(report_effects)")}:  # table from before severity
            conn.execute("ALTER TABLE report_effects ADD COLUMN severity TEXT CHECK (severity IN ('mild', 'moderate', 'severe', 'life_threatening'))")
            conn.commit()
        doses_by_report, dose_run_id = load_report_doses(conn, drug)
        target_names = frozenset(a.strip().lower() for a in ["target", drug, *aliases] if a.strip())
        log.info(f"{len(doses_by_report)} reports with dose rows (dose run {dose_run_id})")

        def write(writer: ReportWriter, context: ReportContext, effects: list[EffectValue]) -> int:
            listed = {dose_id for dose_id, _quote in doses_by_report.get(context.report_id, [])}
            kept, quote_drops, dose_link_drops = apply_effect_checks(effects, context.text, listed)
            drops.update(quote_drops=quote_drops, dose_link_drops=dose_link_drops)
            return writer.write_effects(context.report_id, kept)

        return Step(
            system=effects_system_prompt(drug, aliases, excluded_compounds, domains),
            payload_fn=lambda batch: request_payload(batch, doses_by_report),
            parse_fn=lambda raw, ids: parse_effects_response(raw, ids, target_names, domain_set),
            write_fn=write,
            tokens_per_item=TOKENS_PER_ITEM,
            run_config={"domains": list(domains), "dose_run_id": dose_run_id},
        )

    s = run_report_step(
        client, db_path, drug, extraction_type="report_effects", setup_fn=setup,
        aliases=aliases, excluded_compounds=excluded_compounds, model=model, workers=workers,
        batch_size=batch_size, parent_chars=parent_chars, solo_above_chars=solo_above_chars, limit=limit,
    )
    return EffectRunSummary(**asdict(s), quote_drops=drops["quote_drops"], dose_link_drops=drops["dose_link_drops"])
