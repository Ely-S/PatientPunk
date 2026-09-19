"""
effects.py — One row per effect the author says the drug had on them, per treatment report.

Runs after the sentiment and dose steps. For each latest treatment report of one drug it
sends the report with its parent post, the thread title and the report's dose rows as
context, and appends report_effects rows (report_effects_latest shows each report's most
recent run, like report_doses_latest). Every row carries its sentence; an effect the author
ties to a stated dose points at that report_doses row. The mechanics (context query,
batching, pool, split retry, alias lookup) come from pipeline/report_context.py.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from pipeline.report_context import (
    DEFAULT_PARENT_CHARS,
    DEFAULT_THREAD_CHARS,
    ReportContext,
    aliases_from_db,
    extract_with_split,
    load_report_contexts,
    make_batches,
    resolve_exclusions,
    run_batches,
)
from prompts.effects_config import ATTRIBUTIONS, DOMAINS, effects_system_prompt
from utilities import MODEL_STRONG, LLMParseError, get_git_commit, llm_call, log, parse_json_array
from utilities.db import ReportWriter, open_db

TOKENS_PER_ITEM = 500
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# Kept identical to schema.sql so the step also works on databases created before the table existed.
REPORT_EFFECTS_DDL = """
CREATE TABLE IF NOT EXISTS report_effects (
    effect_id   INTEGER PRIMARY KEY,
    report_id   INTEGER NOT NULL REFERENCES treatment_reports(report_id),
    run_id      INTEGER NOT NULL REFERENCES extraction_runs(run_id),
    ordinal     INTEGER NOT NULL,
    domain      TEXT NOT NULL,
    symptom     TEXT NOT NULL,
    direction   TEXT NOT NULL CHECK (direction IN ('improved', 'worsened', 'no_change', 'mixed')),
    attribution TEXT NOT NULL CHECK (attribution IN ('target', 'stack', 'unclear', 'other compound')),
    quote       TEXT NOT NULL,
    dose_id     INTEGER REFERENCES report_doses(dose_id)
);
CREATE INDEX IF NOT EXISTS idx_re_report ON report_effects(report_id);
CREATE VIEW IF NOT EXISTS report_effects_latest AS
    SELECT e.* FROM report_effects e
    WHERE e.run_id = (SELECT MAX(run_id) FROM report_effects WHERE report_id = e.report_id);
"""


class EffectValue(BaseModel):
    """One effect the author states, as the model returned it after normalisation."""

    model_config = ConfigDict(frozen=True)

    domain: str
    symptom: str
    direction: Literal["improved", "worsened", "no_change", "mixed"]
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
        dose = data.get("dose")
        if isinstance(dose, str) and dose.strip().isdigit():
            dose = int(dose)
        data["dose"] = dose if isinstance(dose, int) and not isinstance(dose, bool) else None
        return data


@dataclass(frozen=True)
class EffectRunSummary:
    run_id: int
    reports: int
    reports_with_effects: int
    effect_rows: int
    failed_reports: int
    dropped_effects: int   # effect objects that did not validate (bad direction, unknown domain, no quote)
    quote_drops: int       # effects dropped because their quote is not in the report
    dose_link_drops: int   # dose ids the model returned that were not among the report's listed doses


def load_report_doses(conn: sqlite3.Connection, drug: str) -> tuple[dict[int, list[tuple[int, str]]], int | None]:
    """Each report's dose rows from its latest dose run, as (dose_id, quote), and that run's id."""
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
          AND d.run_id = (SELECT MAX(run_id) FROM report_doses WHERE report_id = d.report_id)
        ORDER BY d.report_id, d.ordinal
        """,
        (drug,),
    ):
        doses.setdefault(report_id, []).append((dose_id, quote or ""))
        run_ids.add(run_id)
    return doses, (max(run_ids) if run_ids else None)


def request_payload(batch: list[ReportContext], doses_by_report: dict[int, list[tuple[int, str]]]) -> str:
    items = []
    for i, context in enumerate(batch):
        item: dict[str, object] = {"item_id": i, "report": context.text}
        if context.thread_title:
            item["thread"] = context.thread_title
        if context.replying_to:
            item["replying_to"] = context.replying_to
        if doses_by_report.get(context.report_id):
            item["doses"] = [{"id": dose_id, "quote": quote} for dose_id, quote in doses_by_report[context.report_id]]
        items.append(item)
    return json.dumps({"items": items}, ensure_ascii=False)


def parse_effects_response(
    raw: str, expected_ids: list[int], target_names: frozenset[str], domains: frozenset[str] = frozenset(DOMAINS)
) -> tuple[dict[int, list[EffectValue]], int]:
    """Parse the model's array; returns effects per item id and how many effect objects were dropped.

    The prompt names the drug in the attribution field; the table stores ``target``. Any
    label outside the vocabulary is treated as another named compound.
    """
    objects = parse_json_array(raw)
    if not all(isinstance(o, dict) for o in objects):
        raise LLMParseError("Response array must contain objects")
    try:
        ids = [int(o.get("item_id")) for o in objects]
    except (TypeError, ValueError) as e:
        raise LLMParseError(f"Non-integer item_id in response: {e}") from e
    if ids != expected_ids:
        raise LLMParseError(f"Response item ids {ids} do not match request {expected_ids}")
    result: dict[int, list[EffectValue]] = {}
    dropped = 0
    for obj in objects:
        effects: list[EffectValue] = []
        seen: set[tuple] = set()
        raw_effects = obj.get("effects") or []
        if not isinstance(raw_effects, list):
            raise LLMParseError("\"effects\" must be an array")
        for raw_effect in raw_effects:
            if not isinstance(raw_effect, dict):
                dropped += 1
                continue
            data = dict(raw_effect)
            label = str(data.get("attribution") or "").strip().lower()
            data["attribution"] = "target" if label in target_names else label if label in ATTRIBUTIONS else "other compound"
            try:
                effect = EffectValue.model_validate(data)
            except ValidationError:
                dropped += 1
                continue
            if effect.domain not in domains:
                dropped += 1
                continue
            key = (effect.domain, effect.direction, effect.attribution, effect.quote)
            if key not in seen:
                seen.add(key)
                effects.append(effect)
        result[int(obj["item_id"])] = effects
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


def extract_batch(client, batch, system, model, doses_by_report, target_names, domains):
    """Extract one batch; on a malformed reply, split the batch and retry down to single items."""
    return extract_with_split(
        client, batch, system, model,
        lambda b: request_payload(b, doses_by_report),
        lambda raw, ids: parse_effects_response(raw, ids, target_names, domains),
        TOKENS_PER_ITEM, call=llm_call,
    )


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
    thread_chars: int | None = DEFAULT_THREAD_CHARS,
    solo_above_chars: int | None = 3000,
    limit: int | None = None,
) -> EffectRunSummary:
    """Extract effects for every latest report of ``drug`` in ``db_path`` and append report_effects rows."""
    domains = tuple(d.strip().lower() for d in domains if d.strip())
    conn = open_db(db_path)
    try:
        if conn.execute("SELECT 1 FROM treatment WHERE lower(canonical_name) = lower(?)", (drug,)).fetchone() is None:
            raise ValueError(f"{drug!r} is not a canonical treatment name in this database")
        conn.executescript(REPORT_EFFECTS_DDL)
        contexts = load_report_contexts(conn, drug, parent_chars=parent_chars, thread_chars=thread_chars, limit=limit)
        if aliases is None:
            aliases = aliases_from_db(conn, drug)
        excluded_compounds, exclusions_source = resolve_exclusions(conn, drug, excluded_compounds)
        doses_by_report, dose_run_id = load_report_doses(conn, drug)
    finally:
        conn.close()
    system = effects_system_prompt(drug, aliases, excluded_compounds, domains)
    target_names = frozenset(a.strip().lower() for a in ["target", drug, *aliases] if a.strip())
    run_config = {
        "drug": drug,
        "aliases": aliases,
        "excluded_compounds": excluded_compounds,
        "exclusions_source": exclusions_source,
        "domains": list(domains),
        "model": model,
        "prompt_sha256": hashlib.sha256(system.encode("utf-8")).hexdigest(),
        "parent_chars": parent_chars,
        "thread_chars": thread_chars,
        "solo_above_chars": solo_above_chars,
        "batch_size": batch_size,
        "limit": limit,
        "dose_run_id": dose_run_id,
    }
    log.info(f"{len(contexts)} reports for {drug!r}, {len(doses_by_report)} with dose rows (dose run {dose_run_id}); model {model}")
    batches = make_batches(contexts, batch_size, solo_above_chars)
    reports_done = with_effects = rows = failed = dropped_total = quote_drops = link_drops = 0
    with ReportWriter(db_path, run_config, get_git_commit(), extraction_type="report_effects") as writer:
        log.info(f"Extraction run {writer.run_id}")
        extract = lambda batch: extract_batch(client, batch, system, model, doses_by_report, target_names, frozenset(domains))  # noqa: E731
        for batch, outcome, error in run_batches(batches, extract, workers):
            if error is not None:
                log.warning(f"Batch of {len(batch)} failed: {type(error).__name__}: {error}")
                failed += len(batch)
                continue
            results, dropped = outcome
            dropped_total += dropped
            for context in batch:
                if context.report_id not in results:
                    failed += 1
                    continue
                listed = {dose_id for dose_id, _quote in doses_by_report.get(context.report_id, [])}
                kept, q_drops, d_drops = apply_effect_checks(results[context.report_id], context.text, listed)
                quote_drops += q_drops
                link_drops += d_drops
                n = writer.write_effects(context.report_id, kept)
                reports_done += 1
                rows += n
                with_effects += bool(n)
            if reports_done % 80 < len(batch):
                log.info(f"  {reports_done}/{len(contexts)} reports, {rows} effect rows")
        run_id = writer.run_id
    summary = EffectRunSummary(run_id, reports_done, with_effects, rows, failed, dropped_total, quote_drops, link_drops)
    log.info(
        f"Done: {summary.reports} reports, {summary.reports_with_effects} with effects, {summary.effect_rows} effect rows, "
        f"{summary.failed_reports} failed, {summary.dropped_effects} effect objects dropped, "
        f"{summary.quote_drops} quotes not in report, {summary.dose_link_drops} dose links outside the listed doses"
    )
    return summary
