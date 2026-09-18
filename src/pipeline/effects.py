"""
effects.py — One row per effect the author says the drug had on them, per treatment report.

Runs after the sentiment and dose steps. Reads treatment_reports for one drug (latest report
per post), sends each report to the model with its parent post, the thread title and the
report's already-extracted dose rows as context, and writes report_effects. Every row carries
the sentence it came from; an effect the author ties to a stated dose points at that
report_doses row. Rows are replaced per report on rerun.
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
    ReportContext,
    extract_with_split,
    load_report_contexts,
    make_batches,
    run_batches,
)
from prompts.effects_config import ATTRIBUTIONS, DIRECTIONS, DOMAINS, effects_system_prompt
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
    post_id     TEXT NOT NULL REFERENCES posts(post_id),
    user_id     TEXT REFERENCES users(user_id),
    drug_id     INTEGER NOT NULL REFERENCES treatment(id),
    domain      TEXT NOT NULL,
    symptom     TEXT NOT NULL,
    direction   TEXT NOT NULL CHECK (direction IN ('improved', 'worsened', 'no_change', 'mixed')),
    attribution TEXT NOT NULL CHECK (attribution IN ('target', 'stack', 'unclear', 'other compound')),
    quote       TEXT NOT NULL,
    dose_id     INTEGER REFERENCES report_doses(dose_id)
);
CREATE INDEX IF NOT EXISTS idx_re_report ON report_effects(report_id);
CREATE INDEX IF NOT EXISTS idx_re_drug   ON report_effects(drug_id);
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
            data[key] = raw.strip() if isinstance(raw, str) else None
        data["domain"] = (data["domain"] or "").lower()
        data["symptom"] = data["symptom"] or data["domain"]  # a row with no symptom word still names its domain
        if not data["quote"]:
            data["quote"] = None  # required: fails validation
        data["direction"] = str(data.get("direction") or "").strip().lower().replace(" ", "_")
        data["attribution"] = str(data.get("attribution") or "").strip().lower()
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
    dropped_effects: int   # effect objects the model returned that did not validate (bad direction, unknown domain, no quote)
    quote_drops: int       # effects dropped because their quote is not in the report
    dose_link_drops: int   # dose ids the model returned that were not among the report's listed doses


def normalize_attribution(raw: object, target_names: frozenset[str]) -> str:
    """Map the model's attribution label onto the stored vocabulary.

    The prompt names the drug in the attribution field; the table stores ``target``.
    Anything not in the vocabulary is treated as another named compound.
    """
    label = str(raw or "").strip().lower()
    if label == "target" or label in target_names:
        return "target"
    if label in ATTRIBUTIONS:
        return label
    return "other compound"


def normalized_text(text: str) -> str:
    return _NON_ALNUM.sub("", text.lower())


def load_report_doses(conn: sqlite3.Connection, report_ids: list[int]) -> tuple[dict[int, list[tuple[int, str]]], int | None]:
    """Dose rows per report (id, quote), and the dose run they came from (None when there are none)."""
    if not report_ids:
        return {}, None
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'report_doses'").fetchone():
        return {}, None
    doses: dict[int, list[tuple[int, str]]] = {}
    run_ids: set[int] = set()
    for chunk_start in range(0, len(report_ids), 500):
        chunk = report_ids[chunk_start:chunk_start + 500]
        placeholders = ",".join("?" * len(chunk))
        for report_id, dose_id, run_id, quote in conn.execute(
            f"SELECT report_id, dose_id, run_id, quote FROM report_doses "
            f"WHERE report_id IN ({placeholders}) ORDER BY report_id, ordinal",
            chunk,
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
        doses = doses_by_report.get(context.report_id)
        if doses:
            item["doses"] = [{"id": dose_id, "quote": quote} for dose_id, quote in doses]
        items.append(item)
    return json.dumps({"items": items}, ensure_ascii=False)


def parse_effects_response(
    raw: str,
    expected_ids: list[int],
    target_names: frozenset[str],
    domains: frozenset[str] = frozenset(DOMAINS),
) -> tuple[dict[int, list[EffectValue]], int]:
    """Parse the model's array; returns effects per item id and how many effect objects were dropped."""
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
            data["attribution"] = normalize_attribution(data.get("attribution"), target_names)
            try:
                effect = EffectValue.model_validate(data)
            except ValidationError:
                dropped += 1
                continue
            if effect.domain not in domains:
                dropped += 1
                continue
            key = (effect.domain, effect.direction, effect.attribution, effect.quote)
            if key in seen:
                continue
            seen.add(key)
            effects.append(effect)
        result[int(obj["item_id"])] = effects
    return result, dropped


def apply_effect_checks(
    effects: list[EffectValue], report_text: str, listed_dose_ids: set[int]
) -> tuple[list[EffectValue], int, int]:
    """Mechanical checks at write time.

    An effect is dropped when its quote is not found verbatim in the report (compared on
    lower-case letters and digits only); a ``dose`` that is not one of the report's listed
    dose ids becomes null. Returns the kept effects and the two counts.
    """
    haystack = normalized_text(report_text)
    kept: list[EffectValue] = []
    quote_drops = dose_link_drops = 0
    for effect in effects:
        needle = normalized_text(effect.quote)
        if not needle or needle not in haystack:
            quote_drops += 1
            continue
        if effect.dose is not None and effect.dose not in listed_dose_ids:
            dose_link_drops += 1
            effect = effect.model_copy(update={"dose": None})
        kept.append(effect)
    return kept, quote_drops, dose_link_drops


class EffectWriter(ReportWriter):
    """Writes report_effects rows under one extraction_runs row of type ``report_effects``."""

    def __init__(self, db_path: Path, run_config: dict, commit_hash: str):
        super().__init__(db_path, run_config, commit_hash, extraction_type="report_effects")
        self._conn.executescript(REPORT_EFFECTS_DDL)

    def write_effects(self, report_id: int, post_id: str, user_id: str | None, drug_id: int, effects: list[EffectValue]) -> int:
        """Replace a report's rows in report_effects with ``effects``. Returns the number written."""
        self._conn.execute("DELETE FROM report_effects WHERE report_id = ?", (report_id,))
        self._conn.executemany(
            "INSERT INTO report_effects (report_id, run_id, ordinal, post_id, user_id, drug_id, "
            "domain, symptom, direction, attribution, quote, dose_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (report_id, self.run_id, ordinal, post_id, user_id, drug_id,
                 e.domain, e.symptom, e.direction, e.attribution, e.quote, e.dose)
                for ordinal, e in enumerate(effects, 1)
            ],
        )
        self._pending += 1
        if self._pending >= 50:
            self.flush()
        return len(effects)


def _aliases_from_db(conn: sqlite3.Connection, drug: str) -> list[str]:
    row = conn.execute(
        "SELECT aliases FROM treatment WHERE lower(canonical_name) = lower(?)", (drug,)
    ).fetchone()
    if not row or not row[0]:
        return []
    try:
        return [str(a) for a in json.loads(row[0]) if str(a).strip()]
    except (TypeError, ValueError):
        return []


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
    parent_chars: int | None = 1500,
    thread_chars: int | None = 200,
    solo_above_chars: int | None = 3000,
    limit: int | None = None,
) -> EffectRunSummary:
    """Extract effects for every latest report of ``drug`` in ``db_path`` and write report_effects."""
    domains = tuple(d.strip().lower() for d in domains if d.strip())
    conn = open_db(db_path)
    try:
        contexts = load_report_contexts(
            conn, drug, parent_chars=parent_chars, thread_chars=thread_chars, limit=limit
        )
        if aliases is None:
            aliases = _aliases_from_db(conn, drug)
        doses_by_report, dose_run_id = load_report_doses(conn, [c.report_id for c in contexts])
    finally:
        conn.close()
    system = effects_system_prompt(drug, aliases, excluded_compounds, domains)
    target_names = frozenset(a.strip().lower() for a in [drug, *aliases] if a.strip())
    domain_set = frozenset(domains)
    run_config = {
        "drug": drug,
        "aliases": aliases,
        "excluded_compounds": excluded_compounds or [],
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
    log.info(
        f"{len(contexts)} reports for {drug!r}, {len(doses_by_report)} with dose rows "
        f"(dose run {dose_run_id}); model {model}"
    )
    batches = make_batches(contexts, batch_size, solo_above_chars)
    by_report = {c.report_id: c for c in contexts}
    reports_done = with_effects = rows = failed = dropped_total = quote_drops = link_drops = 0
    with EffectWriter(db_path, run_config, get_git_commit()) as writer:
        log.info(f"Extraction run {writer.run_id}")

        def extract(batch):
            return extract_with_split(
                client, batch, system, model,
                lambda b: request_payload(b, doses_by_report),
                lambda raw, ids: parse_effects_response(raw, ids, target_names, domain_set),
                TOKENS_PER_ITEM,
                call=llm_call,
            )

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
                c = by_report[context.report_id]
                listed = {dose_id for dose_id, _quote in doses_by_report.get(c.report_id, [])}
                kept, q_drops, d_drops = apply_effect_checks(results[context.report_id], c.text, listed)
                quote_drops += q_drops
                link_drops += d_drops
                n = writer.write_effects(c.report_id, c.post_id, c.user_id, c.drug_id, kept)
                reports_done += 1
                rows += n
                with_effects += bool(n)
            if reports_done % 80 < len(batch):
                log.info(f"  {reports_done}/{len(contexts)} reports, {rows} effect rows")
        run_id = writer.run_id
    summary = EffectRunSummary(run_id, reports_done, with_effects, rows, failed, dropped_total, quote_drops, link_drops)
    log.info(
        f"Done: {summary.reports} reports, {summary.reports_with_effects} with effects, "
        f"{summary.effect_rows} effect rows, {summary.failed_reports} failed, "
        f"{summary.dropped_effects} effect objects dropped, {summary.quote_drops} quotes not in report, "
        f"{summary.dose_link_drops} dose links outside the listed doses"
    )
    return summary
