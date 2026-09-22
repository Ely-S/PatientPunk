"""
effects.py — One row per effect the author says the drug had on them, per treatment report.

Runs after the sentiment and dose steps. For each latest treatment report of one drug it
sends the report with its parent post and the report's dose rows as context, and writes
report_effects rows (runs append; report_effects_latest shows each report's newest run, like
report_doses_latest). Every row carries its sentence; an effect the author ties to a stated
dose points at that report_doses row. The run itself (report loading, batching, the pool, the
split retry) is pipeline/report_context.py; this module keeps the effect object, the payload,
the parser, the write-time checks and the prompt.
"""
from __future__ import annotations

import re
import sqlite3
import threading
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
from utilities.db import REPORT_DOSES_DDL, ReportWriter

TOKENS_PER_ITEM = 500
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# Kept identical to schema.sql (with IF NOT EXISTS, the backfill, and the view recreated) so the step also works
# on databases created before the table existed. Run after utilities.db.REPORT_DOSES_DDL, which creates report_runs.
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
    dose_id     INTEGER REFERENCES report_doses(dose_id)
);
CREATE INDEX IF NOT EXISTS idx_re_report ON report_effects(report_id);
-- Rows written before report_runs existed count as processed by the run that wrote them.
INSERT OR IGNORE INTO report_runs (run_id, report_id) SELECT DISTINCT run_id, report_id FROM report_effects;
DROP VIEW IF EXISTS report_effects_latest;  -- recreated: a database from before report_runs has an older definition
CREATE VIEW report_effects_latest AS
    SELECT e.* FROM report_effects e
    WHERE e.run_id = (
        SELECT MAX(rr.run_id) FROM report_runs rr JOIN extraction_runs r ON r.run_id = rr.run_id
        WHERE rr.report_id = e.report_id AND r.extraction_type = 'report_effects'
    );
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
        if isinstance(dose, float) and dose.is_integer():
            dose = int(dose)
        data["dose"] = dose if isinstance(dose, int) and not isinstance(dose, bool) else None
        return data


@dataclass(frozen=True)
class EffectRunSummary(StepSummary):
    quote_drops: int              # effects dropped because their quote is not in the report
    dose_link_drops: int          # dose ids the model returned that were not among the report's listed doses
    alias_label_drops: int        # effects dropped because the attribution label contains a name of the drug without being one
    other_compound_relabels: int  # attribution labels outside the vocabulary and the drug's names, stored as "other compound"
    rewrites: int                 # values replaced, not rejected: unknown severity -> NULL, unparseable dose -> NULL, empty symptom -> the domain


def load_report_doses(conn: sqlite3.Connection, drug: str) -> tuple[dict[int, list[tuple[int, str]]], int | None]:
    """Each report's dose rows from its newest dose run (report_doses_latest), as (dose_id, quote), and the
    newest of those runs."""
    doses: dict[int, list[tuple[int, str]]] = {}
    run_ids: set[int] = set()
    for report_id, dose_id, run_id, quote in conn.execute(
        """
        SELECT d.report_id, d.dose_id, d.run_id, d.quote FROM report_doses_latest d
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
    raw: str,
    expected_ids: list[int],
    target_names: frozenset[str],
    domains: frozenset[str] = frozenset(DOMAINS),
    excluded_names: frozenset[str] = frozenset(),
) -> tuple[dict[int, list[EffectValue]], int, Counter[str]]:
    """Effects per item id, how many effect objects were dropped, and counts of what the parser changed.

    The prompt names the drug in the attribution field; the table stores ``target``. A label that
    names an excluded compound, or contains none of the drug's names, is another compound, so
    ``other compound`` (counted as ``other_compound_relabels``). A label that contains one of the
    drug's names without being one ("7,8-DHF (tropoflavin)", "7,8-DHF alone") could mean target,
    stack or another compound: the effect is dropped and counted as ``alias_label_drops``. An empty
    label drops the effect. A missing or non-array ``effects`` field is a parse error. A value
    EffectValue.coerce replaces rather than rejects (an unknown severity, an unparseable dose, an
    empty symptom) is counted as ``rewrites``.
    """
    result: dict[int, list[EffectValue]] = {}
    dropped = 0
    counts: Counter[str] = Counter()
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
            if label in target_names:
                data["attribution"] = "target"
            elif label in ATTRIBUTIONS:
                data["attribution"] = label
            elif any(name in label for name in excluded_names) or not any(name in label for name in target_names):
                data["attribution"] = "other compound"
                counts["other_compound_relabels"] += 1
            else:
                counts["alias_label_drops"] += 1
                continue
            try:
                effect = EffectValue.model_validate(data)
            except ValidationError:
                dropped += 1
                continue
            counts["rewrites"] += sum((
                data.get("severity") not in (None, "") and effect.severity is None,
                data.get("dose") not in (None, "") and effect.dose is None,
                not (isinstance(data.get("symptom"), str) and data["symptom"].strip()),
            ))
            if effect.domain not in domains:
                dropped += 1
                continue
            key = (effect.domain, effect.symptom, effect.direction, effect.severity, effect.attribution, effect.quote, effect.dose)
            if key not in seen:
                seen.add(key)
                effects.append(effect)
        result[item_id] = effects
    return result, dropped, counts


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
    counts: Counter[str] = Counter()
    counts_lock = threading.Lock()  # parse runs on the pool's threads

    def setup(conn: sqlite3.Connection, aliases: list[str], excluded_compounds: list[str]) -> Step:
        conn.executescript(REPORT_DOSES_DDL + REPORT_EFFECTS_DDL)  # report_runs and the dose view first: load_report_doses reads it
        if "severity" not in {row[1] for row in conn.execute("PRAGMA table_info(report_effects)")}:  # table from before severity
            conn.execute("ALTER TABLE report_effects ADD COLUMN severity TEXT CHECK (severity IN ('mild', 'moderate', 'severe', 'life_threatening'))")
            conn.commit()
        doses_by_report, dose_run_id = load_report_doses(conn, drug)
        target_names = frozenset(a.strip().lower() for a in ["target", drug, *aliases] if a.strip())
        excluded_names = frozenset(n.strip().lower() for n in excluded_compounds if n.strip())
        log.info(f"{len(doses_by_report)} reports with dose rows (dose run {dose_run_id})")

        def parse(raw: str, ids: list[int]) -> tuple[dict[int, list[EffectValue]], int]:
            per_item, dropped, parse_counts = parse_effects_response(raw, ids, target_names, domain_set, excluded_names)
            with counts_lock:
                counts.update(parse_counts)
            return per_item, dropped

        def write(writer: ReportWriter, context: ReportContext, effects: list[EffectValue]) -> int:
            listed = {dose_id for dose_id, _quote in doses_by_report.get(context.report_id, [])}
            kept, quote_drops, dose_link_drops = apply_effect_checks(effects, context.text, listed)
            counts.update(quote_drops=quote_drops, dose_link_drops=dose_link_drops)
            return writer.write_effects(context.report_id, kept)

        return Step(
            system=effects_system_prompt(drug, aliases, excluded_compounds, domains),
            payload_fn=lambda batch: request_payload(batch, doses_by_report),
            parse_fn=parse,
            write_fn=write,
            tokens_per_item=TOKENS_PER_ITEM,
            run_config={"domains": list(domains), "dose_run_id": dose_run_id},
        )

    s = run_report_step(
        client, db_path, drug, extraction_type="report_effects", setup_fn=setup,
        aliases=aliases, excluded_compounds=excluded_compounds, model=model, workers=workers,
        batch_size=batch_size, parent_chars=parent_chars, solo_above_chars=solo_above_chars, limit=limit,
    )
    return EffectRunSummary(
        **asdict(s), quote_drops=counts["quote_drops"], dose_link_drops=counts["dose_link_drops"],
        alias_label_drops=counts["alias_label_drops"], other_compound_relabels=counts["other_compound_relabels"],
        rewrites=counts["rewrites"],
    )
