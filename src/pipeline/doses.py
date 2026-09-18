"""
doses.py — One row per dose the author states they took, per treatment report.

Runs after the sentiment pipeline. Reads treatment_reports for one drug (latest report
per post), sends each report to the model with its parent post as context, and writes
report_doses. Amounts are stored as stated (a range keeps its low and high); every row
carries the sentence it came from.

Standalone by design. Pieces that mirror the sentiment pipeline are kept as
self-contained units so a later refactor is a move, not a rewrite (see the PR's plan):
  * run_batches() + extract_batch()'s split <-> the pool loop and per-batch fallback in
    classify.run_classification (and the halving in extract.py / canonicalize.py)
  * load_dose_contexts() + request_payload() <-> extract.load_posts_from_db + classify.format_entry
Rows are written through utilities.db.ReportWriter.write_doses.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from prompts.dose_config import OUTCOMES, ROUTE_CATEGORIES, dose_system_prompt
from utilities import MODEL_STRONG, LLMParseError, get_git_commit, llm_call, log, parse_json_array
from utilities.db import ReportWriter, open_db, post_text

DoseUnit = Literal["mcg", "mg", "g"]
_UNIT_SYNONYMS = {
    "mcg": "mcg", "ug": "mcg", "µg": "mcg", "μg": "mcg", "microgram": "mcg", "micrograms": "mcg",
    "mg": "mg", "milligram": "mg", "milligrams": "mg",
    "g": "g", "gram": "g", "grams": "g",
}
TOKENS_PER_ITEM = 400
_WS = re.compile(r"\s+")

class DoseValue(BaseModel):
    """One stated per-administration amount, as the author wrote it."""

    model_config = ConfigDict(frozen=True)

    low: float = Field(gt=0)
    high: float = Field(gt=0)
    unit: DoseUnit | None  # None: the author gave a number with no unit (kept as stated)
    route: Literal["oral mucosal", "swallowed oral", "nasal mucosal", "injection", "other explicit route"] | None = None
    outcome: Literal["positive", "negative", "neutral", "unclear"] | None = None
    quote: str | None = None

    @model_validator(mode="before")
    @classmethod
    def coerce(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        raw_unit = str(data.get("unit") or "").strip().lower()
        unit, _, per = raw_unit.partition("/")  # "mg/day" is a dose; "mg/kg" is not
        unit = unit.strip()
        if unit in {"", "null", "none", "unspecified", "unknown"}:
            data["unit"] = None  # bare number, kept as stated
        elif per.strip() in {"kg", "kilo", "kilogram", "lb", "lbs"}:
            data["unit"] = raw_unit  # fails the Literal check: per-weight doses are dropped
        else:
            data["unit"] = _UNIT_SYNONYMS.get(unit, unit)
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
class DoseContext:
    report_id: int
    post_id: str
    user_id: str | None
    drug_id: int
    text: str
    replying_to: str


@dataclass(frozen=True)
class DoseRunSummary:
    run_id: int
    reports: int
    reports_with_doses: int
    dose_rows: int
    failed_reports: int
    dropped_doses: int  # dose objects the model returned that did not validate


def load_dose_contexts(
    conn: sqlite3.Connection,
    drug: str,
    *,
    parent_chars: int | None = 1500,
    limit: int | None = None,
    max_text_chars: int = 8000,
) -> list[DoseContext]:
    """Latest treatment report per post for ``drug``, with the parent post as context."""
    rows = conn.execute(
        """
        SELECT tr.report_id, tr.post_id, tr.user_id, tr.drug_id,
               p.title, p.body_text, p.parent_id,
               pp.title AS parent_title, pp.body_text AS parent_body, pp.parent_id AS parent_parent
        FROM treatment_reports tr
        JOIN treatment t ON t.id = tr.drug_id
        JOIN posts p ON p.post_id = tr.post_id
        LEFT JOIN posts pp ON pp.post_id = p.parent_id
        WHERE lower(t.canonical_name) = lower(?)
          AND tr.report_id = (
              SELECT MAX(tr2.report_id) FROM treatment_reports tr2
              WHERE tr2.post_id = tr.post_id AND tr2.drug_id = tr.drug_id
          )
        ORDER BY tr.report_id
        """,
        (drug,),
    ).fetchall()
    contexts: list[DoseContext] = []
    for report_id, post_id, user_id, drug_id, title, body, parent_id, ptitle, pbody, pparent in rows:
        text = _WS.sub(" ", post_text(title, body, parent_id)).strip()[:max_text_chars]
        if not text:
            continue
        parent = ""
        if parent_chars and parent_id is not None and (ptitle or pbody):
            parent = _WS.sub(" ", post_text(ptitle, pbody, pparent)).strip()[:parent_chars]
        contexts.append(DoseContext(report_id, post_id, user_id, drug_id, text, parent))
        if limit and len(contexts) >= limit:
            break
    return contexts


def make_batches(
    contexts: list[DoseContext], batch_size: int, solo_above_chars: int | None
) -> list[list[DoseContext]]:
    """Group short reports ``batch_size`` per call; long reports go one per call."""
    short = [c for c in contexts if solo_above_chars is None or len(c.text) <= solo_above_chars]
    long_ = [c for c in contexts if solo_above_chars is not None and len(c.text) > solo_above_chars]
    batches = [short[i:i + batch_size] for i in range(0, len(short), batch_size)]
    batches.extend([c] for c in long_)
    return batches


def request_payload(batch: list[DoseContext]) -> str:
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


def extract_batch(
    client, batch: list[DoseContext], system: str, model: str
) -> tuple[dict[int, list[DoseValue]], int]:
    """Extract one batch; on a malformed reply, split the batch and retry down to single items."""
    payload = request_payload(batch)
    try:
        raw = llm_call(client, payload, model=model, system=system, max_tokens=TOKENS_PER_ITEM * len(batch))
        per_item, dropped = parse_dose_response(raw, list(range(len(batch))))
        return {batch[i].report_id: doses for i, doses in per_item.items()}, dropped
    except LLMParseError as e:
        if len(batch) == 1:
            log.warning(f"Skipping report {batch[0].report_id}: {e}")
            return {}, 0
        log.warning(f"Malformed reply for a batch of {len(batch)}; splitting. {e}")
        mid = len(batch) // 2
        left, dropped_left = extract_batch(client, batch[:mid], system, model)
        right, dropped_right = extract_batch(client, batch[mid:], system, model)
        return {**left, **right}, dropped_left + dropped_right


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


def run_batches(batches, fn, workers: int):
    """Run ``fn(batch)`` over ``batches`` on a thread pool; yield ``(batch, result, error)`` as each completes.

    Mirrors the pool loop in classify.run_classification (candidate for a shared helper).
    """
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(fn, batch): batch for batch in batches}
        for future in as_completed(futures):
            batch = futures[future]
            try:
                yield batch, future.result(), None
            except Exception as e:  # noqa: BLE001 — transport failures after retries, truncation at the largest budget
                yield batch, None, e


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
    parent_chars: int | None = 1500,
    solo_above_chars: int | None = 3000,
    limit: int | None = None,
) -> DoseRunSummary:
    """Extract doses for every latest report of ``drug`` in ``db_path`` and write report_doses."""
    conn = open_db(db_path)
    try:
        contexts = load_dose_contexts(conn, drug, parent_chars=parent_chars, limit=limit)
        if aliases is None:
            aliases = _aliases_from_db(conn, drug)
    finally:
        conn.close()
    system = dose_system_prompt(drug, aliases, excluded_compounds)
    run_config = {
        "drug": drug,
        "aliases": aliases,
        "excluded_compounds": excluded_compounds or [],
        "model": model,
        "prompt_sha256": hashlib.sha256(system.encode("utf-8")).hexdigest(),
        "parent_chars": parent_chars,
        "solo_above_chars": solo_above_chars,
        "batch_size": batch_size,
        "limit": limit,
    }
    log.info(f"{len(contexts)} reports for {drug!r}; model {model}")
    batches = make_batches(contexts, batch_size, solo_above_chars)
    by_report = {c.report_id: c for c in contexts}
    reports_done = with_doses = rows = failed = dropped_total = 0
    with ReportWriter(db_path, run_config, get_git_commit(), extraction_type="report_doses") as writer:
        log.info(f"Extraction run {writer.run_id}")
        extract = lambda batch: extract_batch(client, batch, system, model)  # noqa: E731
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
                n = writer.write_doses(c.report_id, c.post_id, c.user_id, c.drug_id, results[context.report_id])
                reports_done += 1
                rows += n
                with_doses += bool(n)
            if reports_done % 80 < len(batch):
                log.info(f"  {reports_done}/{len(contexts)} reports, {rows} dose rows")
        run_id = writer.run_id
    summary = DoseRunSummary(run_id, reports_done, with_doses, rows, failed, dropped_total)
    log.info(
        f"Done: {summary.reports} reports, {summary.reports_with_doses} with doses, "
        f"{summary.dose_rows} dose rows, {summary.failed_reports} failed, {summary.dropped_doses} dose objects dropped"
    )
    return summary
