"""
report_context.py — Shared mechanics for the per-report extraction steps (doses, effects).

One drug's latest report per post with its parent post as context, batched, extracted on a thread pool
with a split-on-malformed-reply retry, written to the step's table (run_report_step). A step supplies a
Step from its setup function and a ReportWriter method; add_step_arguments / step_kwargs are its CLI flags.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from utilities import MODEL_STRONG, LLMParseError, get_git_commit, llm_call, log
from utilities.db import ReportWriter, open_db, post_text

_WS = re.compile(r"\s+")

# What a per-report step sends with each report and how it batches, shared by every step.
DEFAULT_PARENT_CHARS = 1500      # the post being replied to, capped
DEFAULT_SOLO_ABOVE_CHARS = 3000  # reports longer than this go one per call

@dataclass(frozen=True)
class ReportContext:
    report_id: int
    post_id: str
    user_id: str | None
    drug_id: int
    text: str
    replying_to: str


def load_report_contexts(
    conn: sqlite3.Connection,
    drug: str,
    *,
    parent_chars: int | None = DEFAULT_PARENT_CHARS,
    limit: int | None = None,
    max_text_chars: int = 8000,
) -> list[ReportContext]:
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
    contexts: list[ReportContext] = []
    for report_id, post_id, user_id, drug_id, title, body, parent_id, ptitle, pbody, pparent in rows:
        text = _WS.sub(" ", post_text(title, body, parent_id)).strip()[:max_text_chars]
        if not text:
            continue
        parent = ""
        if parent_chars and parent_id is not None and (ptitle or pbody):
            parent = _WS.sub(" ", post_text(ptitle, pbody, pparent)).strip()[:parent_chars]
        contexts.append(ReportContext(report_id, post_id, user_id, drug_id, text, parent))
        if limit and len(contexts) >= limit:
            break
    return contexts


def make_batches(
    contexts: list[ReportContext], batch_size: int, solo_above_chars: int | None
) -> list[list[ReportContext]]:
    """Group short reports ``batch_size`` per call; long reports go one per call."""
    short = [c for c in contexts if solo_above_chars is None or len(c.text) <= solo_above_chars]
    long_ = [c for c in contexts if solo_above_chars is not None and len(c.text) > solo_above_chars]
    batches = [short[i:i + batch_size] for i in range(0, len(short), batch_size)]
    batches.extend([c] for c in long_)
    return batches


def extract_with_split(
    client,
    batch: list[ReportContext],
    system: str,
    model: str,
    payload_fn: Callable[[list[ReportContext]], str],
    parse_fn: Callable[[str, list[int]], tuple[dict[int, Any], int]],
    tokens_per_item: int,
    call: Callable | None = None,
) -> tuple[dict[int, Any], int]:
    """Extract one batch; a malformed reply splits it and retries down to single items (a bad single item is skipped).

    ``parse_fn(raw, expected_item_ids) -> (per_item_id, dropped)``, re-keyed by report_id. ``call`` defaults to
    utilities.llm_call at call time: stub ``report_context.llm_call``, or a step's own module (it passes its ``llm_call`` on its Step)."""
    fn = call or llm_call
    try:
        raw = fn(client, payload_fn(batch), model=model, system=system, max_tokens=tokens_per_item * len(batch))
        per_item, dropped = parse_fn(raw, list(range(len(batch))))
        return {batch[i].report_id: value for i, value in per_item.items()}, dropped
    except LLMParseError as e:
        if len(batch) == 1:
            log.warning(f"Skipping report {batch[0].report_id}: {e}")
            return {}, 0
        log.warning(f"Malformed reply for a batch of {len(batch)}; splitting. {e}")
        mid = len(batch) // 2
        left, dropped_left = extract_with_split(client, batch[:mid], system, model, payload_fn, parse_fn, tokens_per_item, call)
        right, dropped_right = extract_with_split(client, batch[mid:], system, model, payload_fn, parse_fn, tokens_per_item, call)
        return {**left, **right}, dropped_left + dropped_right


def aliases_from_db(conn: sqlite3.Connection, drug: str) -> list[str]:
    """Spellings the sentiment run stored for ``drug`` in the treatment table; [] when none."""
    row = conn.execute(
        "SELECT aliases FROM treatment WHERE lower(canonical_name) = lower(?)", (drug,)
    ).fetchone()
    if not row or not row[0]:
        return []
    try:
        return [str(a) for a in json.loads(row[0]) if str(a).strip()]
    except (TypeError, ValueError):
        return []


def run_batches(batches: list, fn: Callable, workers: int) -> Iterator[tuple[Any, Any, Exception | None]]:
    """Run ``fn(batch)`` over ``batches`` on a thread pool; yield ``(batch, result, error)`` as each completes."""
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(fn, batch): batch for batch in batches}
        for future in as_completed(futures):
            batch = futures[future]
            try:
                yield batch, future.result(), None
            except Exception as e:  # noqa: BLE001 — transport failures after retries, truncation at the largest budget
                yield batch, None, e


# ── The run ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class StepInputs:
    """What the shared loader resolved for a run, handed to the step's setup function."""

    contexts: list[ReportContext]
    aliases: list[str]
    excluded_compounds: list[str]


@dataclass(frozen=True)
class Step:
    """What a step contributes to a run; its setup function builds this once the inputs are known."""

    system: str
    payload_fn: Callable[[list[ReportContext]], str]
    parse_fn: Callable[[str, list[int]], tuple[dict[int, Any], int]]
    tokens_per_item: int
    # Per-report checks before the write: (context, values) -> (kept values, counters to sum into the summary).
    check_fn: Callable[[ReportContext, Any], tuple[Any, dict[str, int]]] | None = None
    run_config: dict[str, Any] = field(default_factory=dict)  # step-specific keys recorded on the extraction_runs row
    call: Callable | None = None  # the model call; a step passes its own module's llm_call so tests can stub it there


@dataclass(frozen=True)
class StepSummary:
    run_id: int
    reports: int
    reports_with_rows: int
    rows: int
    failed: int
    dropped: int            # objects the model returned that did not validate
    extra: dict[str, int]   # the step's check_fn counters, summed over the run


def run_report_step(
    client,
    db_path: Path,
    drug: str,
    *,
    extraction_type: str,
    setup_fn: Callable[[sqlite3.Connection, StepInputs], Step],
    write_fn: Callable[[ReportWriter, int, Any], int],
    aliases: list[str] | None = None,
    excluded_compounds: list[str] | None = None,
    model: str = MODEL_STRONG,
    workers: int = 8,
    batch_size: int = 8,
    parent_chars: int | None = DEFAULT_PARENT_CHARS,
    solo_above_chars: int | None = DEFAULT_SOLO_ABOVE_CHARS,
    limit: int | None = None,
) -> StepSummary:
    """Run one per-report step over every latest report of ``drug`` in ``db_path``; returns its StepSummary.

    Validates the drug, loads reports and aliases (treatment table unless given), then calls
    ``setup_fn(conn, inputs) -> Step`` on the open connection. Per report, under a new extraction_runs row:
    ``check_fn(context, values) -> (kept, counters)`` when set, then ``write_fn(writer, report_id, kept)``."""
    conn = open_db(db_path)
    try:
        if conn.execute("SELECT 1 FROM treatment WHERE lower(canonical_name) = lower(?)", (drug,)).fetchone() is None:
            raise ValueError(f"{drug!r} is not a canonical treatment name in this database")
        contexts = load_report_contexts(conn, drug, parent_chars=parent_chars, limit=limit)
        if aliases is None:
            aliases = aliases_from_db(conn, drug)
        inputs = StepInputs(contexts, aliases, list(excluded_compounds or []))
        step = setup_fn(conn, inputs)
    finally:
        conn.close()
    run_config = {
        "drug": drug,
        "aliases": aliases,
        "excluded_compounds": inputs.excluded_compounds,
        "model": model,
        "prompt_sha256": hashlib.sha256(step.system.encode("utf-8")).hexdigest(),
        "parent_chars": parent_chars,
        "solo_above_chars": solo_above_chars,
        "batch_size": batch_size,
        "limit": limit,
        **step.run_config,
    }
    log.info(f"{len(contexts)} reports for {drug!r}; model {model}")
    batches = make_batches(contexts, batch_size, solo_above_chars)
    reports_done = with_rows = rows = failed = dropped_total = 0
    extra: Counter[str] = Counter()
    with ReportWriter(db_path, run_config, get_git_commit(), extraction_type=extraction_type) as writer:
        log.info(f"Extraction run {writer.run_id}")
        extract = lambda batch: extract_with_split(  # noqa: E731
            client, batch, step.system, model, step.payload_fn, step.parse_fn, step.tokens_per_item, call=step.call
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
                values = results[context.report_id]
                if step.check_fn is not None:
                    values, counters = step.check_fn(context, values)
                    extra.update(counters)
                n = write_fn(writer, context.report_id, values)
                reports_done += 1
                rows += n
                with_rows += bool(n)
            if reports_done % 80 < len(batch):
                log.info(f"  {reports_done}/{len(contexts)} reports, {rows} rows")
        run_id = writer.run_id
    summary = StepSummary(run_id, reports_done, with_rows, rows, failed, dropped_total, dict(extra))
    log.info(
        f"Done: {summary.reports} reports, {summary.reports_with_rows} with rows, {summary.rows} rows, "
        f"{summary.failed} failed, {summary.dropped} objects dropped"
        + "".join(f", {v} {k.replace('_', ' ')}" for k, v in summary.extra.items())
    )
    return summary


# ── The CLI ─────────────────────────────────────────────────────────────────────────────

def read_list_file(path: str | Path) -> list[str]:
    """Non-blank lines of a text file (drug spellings, exclusion names); [] when none."""
    return [line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def add_step_arguments(parser: argparse.ArgumentParser, noun: str) -> None:
    """The flags every per-report step takes; ``noun`` is what the step extracts ("doses"), for the help texts."""
    parser.add_argument("--db", required=True, help="SQLite database with treatment_reports for the drug")
    parser.add_argument("--drug", required=True, help="Canonical treatment name as stored in the treatment table")
    parser.add_argument("--drug-file", type=str, default=None,
                        help="Text file of spellings for the drug, one per line (default: aliases from the treatment table)")
    parser.add_argument("--exclude-compound", action="append", default=[],
                        help=f"Name of a different compound whose {noun} must not be attributed to the drug (repeatable)")
    parser.add_argument("--exclude-file", type=str, default=None,
                        help="Text file of such compound names, one per line (added to --exclude-compound)")
    parser.add_argument("--model", type=str, default=MODEL_STRONG, help=f"Model for the extraction (default: {MODEL_STRONG})")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--parent-chars", type=int, default=DEFAULT_PARENT_CHARS,
                        help="Characters of the parent post sent as context; 0 sends none")
    parser.add_argument("--solo-above-chars", type=int, default=DEFAULT_SOLO_ABOVE_CHARS,
                        help="Reports longer than this go one per call; 0 disables")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N reports (0 = all)")


def _required_lines(parser: argparse.ArgumentParser, path: str, flag: str) -> list[str]:
    lines = read_list_file(path)
    if not lines:
        parser.error(f"{flag} {path} contains no non-blank lines")
    return lines


def step_kwargs(parser: argparse.ArgumentParser, args: argparse.Namespace) -> dict[str, Any]:
    """Keyword arguments for a step's run function, from the flags add_step_arguments added."""
    aliases = _required_lines(parser, args.drug_file, "--drug-file") if args.drug_file else None
    excluded = list(args.exclude_compound) + (_required_lines(parser, args.exclude_file, "--exclude-file") if args.exclude_file else [])
    return {
        "aliases": aliases,
        "excluded_compounds": excluded or None,
        "model": args.model,
        "workers": args.workers,
        "batch_size": args.batch_size,
        "parent_chars": args.parent_chars or None,
        "solo_above_chars": args.solo_above_chars or None,
        "limit": args.limit or None,
    }
