"""
report_context.py — Shared mechanics for the per-report extraction steps (doses, effects).

run_report_step takes one drug's latest report per post with its parent post as context, batches them, calls
the model on a thread pool with a split-on-malformed-reply retry, and writes each report's rows under a new
extraction_runs row. A step supplies a Step from its setup function; add_step_arguments / step_kwargs are its CLI flags.
Exclusion names come from one place for every step (resolve_exclusions).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from utilities import MODEL_STRONG, LLMParseError, get_git_commit, is_transient_or_truncated, llm_call, log, parse_json_array
from utilities.db import ReportWriter, open_db, post_text

DEFAULT_PARENT_CHARS = 1500      # of the post being replied to, sent as context
DEFAULT_SOLO_ABOVE_CHARS = 3000  # reports longer than this go one per call
_WS = re.compile(r"\s+")


# ── Reports ─────────────────────────────────────────────────────────────────────────────

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


def aliases_from_db(conn: sqlite3.Connection, drug: str) -> list[str]:
    """Spellings the sentiment run stored for ``drug`` in the treatment table; [] when none, ValueError when corrupt."""
    row = conn.execute(
        "SELECT aliases FROM treatment WHERE lower(canonical_name) = lower(?)", (drug,)
    ).fetchone()
    if not row or not row[0]:
        return []
    try:
        return [str(a) for a in json.loads(row[0]) if str(a).strip()]
    except (TypeError, ValueError) as e:
        raise ValueError(f"treatment.aliases for {drug!r} is not a JSON list: {row[0]!r}") from e


def resolve_exclusions(
    conn: sqlite3.Connection, drug: str, explicit: list[str] | None
) -> tuple[list[str], str]:
    """Names of other compounds the prompt must not attribute to ``drug``, and where they came from.

    Explicit names (the --exclude-compound / --exclude-file flags) win. Otherwise the list the
    sentiment run recorded for this drug (``drug_excluded_aliases`` in its run config, written
    by run_sentiment_pipeline --drug-exclude-file) is inherited, so the steps cannot disagree
    about what is not the drug. Returns (names, "flags" | "sentiment_run" | "none").
    """
    if explicit:
        return list(explicit), "flags"
    for (config,) in conn.execute(
        "SELECT config FROM extraction_runs WHERE extraction_type = 'treatment_sentiment' ORDER BY run_id DESC"
    ):
        try:
            cfg = json.loads(config or "{}")
        except ValueError:
            continue
        if str(cfg.get("drug") or "").lower() == drug.lower():
            names = [str(n) for n in cfg.get("drug_excluded_aliases") or [] if str(n).strip()]
            return names, ("sentiment_run" if names else "none")
    return [], "none"


def make_batches(
    contexts: list[ReportContext], batch_size: int, solo_above_chars: int | None
) -> list[list[ReportContext]]:
    """Group short reports ``batch_size`` per call; long reports go one per call."""
    short = [c for c in contexts if solo_above_chars is None or len(c.text) <= solo_above_chars]
    long_ = [c for c in contexts if solo_above_chars is not None and len(c.text) > solo_above_chars]
    batches = [short[i:i + batch_size] for i in range(0, len(short), batch_size)]
    batches.extend([c] for c in long_)
    return batches


# ── The model call ──────────────────────────────────────────────────────────────────────
# A batch is sent as items numbered by position; the reply must answer the same ids in order.

@dataclass(frozen=True)
class Step:
    """What a step contributes to a run; its setup function builds this once aliases and exclusions are known."""

    system: str
    payload_fn: Callable[[list[ReportContext]], str]                  # a batch's request body (see serialize_batch)
    parse_fn: Callable[[str, list[int]], tuple[dict[int, Any], int]]  # (reply, item ids) -> (values per id, dropped: objects that did not validate)
    write_fn: Callable[[ReportWriter, ReportContext, Any], int]       # writes one report's values; returns rows written
    tokens_per_item: int
    run_config: dict[str, Any] = field(default_factory=dict)          # step-specific keys for the extraction_runs row


def request_items(batch: list[ReportContext]) -> list[dict[str, Any]]:
    """One ``{item_id, report, replying_to?}`` object per report, ``item_id`` its position in the batch."""
    items: list[dict[str, Any]] = []
    for i, context in enumerate(batch):
        item: dict[str, Any] = {"item_id": i, "report": context.text}
        if context.replying_to:
            item["replying_to"] = context.replying_to
        items.append(item)
    return items


def serialize_batch(
    batch: list[ReportContext], extra: Callable[[ReportContext], dict[str, Any]] | None = None
) -> str:
    """A batch's request body, ``{"items": request_items(batch)}``; each item also carries ``extra(context)`` when given."""
    items = request_items(batch)
    if extra:
        for item, context in zip(items, batch):
            item.update(extra(context))
    return json.dumps({"items": items}, ensure_ascii=False)


def response_items(raw: str, expected_ids: list[int]) -> dict[int, dict]:
    """The reply's objects by item id, or LLMParseError unless they answer ``expected_ids`` in order."""
    objects = parse_json_array(raw)
    if not all(isinstance(o, dict) for o in objects):
        raise LLMParseError("Response array must contain objects")
    try:
        ids = [int(o.get("item_id")) for o in objects]
    except (TypeError, ValueError) as e:
        raise LLMParseError(f"Non-integer item_id in response: {e}") from e
    if ids != expected_ids:
        raise LLMParseError(f"Response item ids {ids} do not match request {expected_ids}")
    return dict(zip(ids, objects))


def extract_with_split(
    client, batch: list[ReportContext], step: Step, model: str, call: Callable[..., str]
) -> tuple[dict[int, Any], int]:
    """Values per report_id and the dropped count for one batch; a malformed reply splits it, a malformed single is skipped."""
    try:
        raw = call(client, step.payload_fn(batch), model=model, system=step.system,
                   max_tokens=step.tokens_per_item * len(batch))
        per_item, dropped = step.parse_fn(raw, list(range(len(batch))))
        return {batch[i].report_id: value for i, value in per_item.items()}, dropped
    except LLMParseError as e:
        if len(batch) == 1:
            log.warning(f"Skipping report {batch[0].report_id}: {e}")
            return {}, 0
        log.warning(f"Malformed reply for a batch of {len(batch)}; splitting. {e}")
        mid = len(batch) // 2
        left, dropped_left = extract_with_split(client, batch[:mid], step, model, call)
        right, dropped_right = extract_with_split(client, batch[mid:], step, model, call)
        return {**left, **right}, dropped_left + dropped_right


# ── The run ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class StepSummary:
    run_id: int
    reports: int            # reports the model answered
    reports_with_rows: int
    rows: int
    failed: int             # reports with no usable reply; a failed batch counts every report in it
    dropped: int            # objects the model returned that did not validate


def run_report_step(
    client,
    db_path: Path,
    drug: str,
    *,
    extraction_type: str,
    setup_fn: Callable[[sqlite3.Connection, list[str], list[str]], Step],
    aliases: list[str] | None = None,
    excluded_compounds: list[str] | None = None,
    model: str = MODEL_STRONG,
    workers: int = 8,
    batch_size: int = 8,
    parent_chars: int | None = DEFAULT_PARENT_CHARS,
    solo_above_chars: int | None = DEFAULT_SOLO_ABOVE_CHARS,
    limit: int | None = None,
    call: Callable[..., str] | None = None,
) -> StepSummary:
    """Run one step over every latest report of ``drug`` in ``db_path`` under a new extraction_runs row.
    ``setup_fn(conn, aliases, excluded_compounds) -> Step`` runs on the open connection before the run, so a
    step can read its own tables there; aliases come from the treatment table unless given, exclusion names
    from resolve_exclusions. ``call`` is the model call, ``llm_call`` unless given: tests pass a stub, or
    monkeypatch ``llm_call`` in this module."""
    if call is None:
        call = llm_call
    conn = open_db(db_path)
    try:
        if conn.execute("SELECT 1 FROM treatment WHERE lower(canonical_name) = lower(?)", (drug,)).fetchone() is None:
            raise ValueError(f"{drug!r} is not a canonical treatment name in this database")
        contexts = load_report_contexts(conn, drug, parent_chars=parent_chars, limit=limit)
        if aliases is None:
            aliases = aliases_from_db(conn, drug)
        excluded_compounds, exclusions_source = resolve_exclusions(conn, drug, excluded_compounds)
        step = setup_fn(conn, aliases, excluded_compounds)
    finally:
        conn.close()
    run_config = {
        "drug": drug,
        "aliases": aliases,
        "excluded_compounds": excluded_compounds,
        "exclusions_source": exclusions_source,
        "model": model,
        "prompt_sha256": hashlib.sha256(step.system.encode("utf-8")).hexdigest(),
        "parent_chars": parent_chars,
        "solo_above_chars": solo_above_chars,
        "batch_size": batch_size,
        "limit": limit,
    }
    if clash := run_config.keys() & step.run_config.keys():
        raise ValueError(f"Step.run_config must not override shared keys: {sorted(clash)}")
    run_config |= step.run_config
    log.info(f"{len(contexts)} reports for {drug!r}; model {model}")
    batches = iter(make_batches(contexts, batch_size, solo_above_chars))
    reports = with_rows = rows = failed = dropped = 0
    workers = max(1, workers)
    with (
        ReportWriter(db_path, run_config, get_git_commit(), extraction_type=extraction_type) as writer,
        ThreadPoolExecutor(max_workers=workers) as pool,
    ):
        log.info(f"Extraction run {writer.run_id}")
        # At most workers * 2 batches in flight, the next submitted as one completes (like the sentiment
        # classifier), so an error ends the run after the calls already made, not after the whole queue.
        in_flight: dict[Future, list[ReportContext]] = {}

        def submit_next() -> None:
            for batch in batches:
                in_flight[pool.submit(extract_with_split, client, batch, step, model, call)] = batch
                return

        try:
            for _ in range(workers * 2):
                submit_next()
            while in_flight:
                future = next(as_completed(in_flight))
                batch = in_flight.pop(future)
                try:
                    results, dropped_in_batch = future.result()
                except Exception as e:  # noqa: BLE001
                    if not is_transient_or_truncated(e):  # a configuration error or a bug: stop, it is not a failed batch
                        raise
                    log.warning(f"Batch of {len(batch)} failed: {type(e).__name__}: {e}")
                    failed += len(batch)
                else:
                    dropped += dropped_in_batch
                    for context in batch:
                        if context.report_id not in results:
                            failed += 1
                            continue
                        n = step.write_fn(writer, context, results[context.report_id])
                        reports += 1
                        rows += n
                        with_rows += bool(n)
                    if reports % 80 < len(batch):  # about every 80 reports
                        log.info(f"  {reports}/{len(contexts)} reports, {rows} rows")
                submit_next()
        except BaseException:
            pool.shutdown(wait=False, cancel_futures=True)  # queued batches never call the model; in-flight ones finish
            raise
        summary = StepSummary(writer.run_id, reports, with_rows, rows, failed, dropped)
    log.info(
        f"Done: {summary.reports} reports, {summary.reports_with_rows} with rows, {summary.rows} rows, "
        f"{summary.failed} failed, {summary.dropped} objects dropped"
    )
    return summary


# ── The CLI ─────────────────────────────────────────────────────────────────────────────

def add_step_arguments(parser: argparse.ArgumentParser) -> None:
    """The flags every per-report step takes; step_kwargs turns them into run keywords."""
    parser.add_argument("--db", required=True, help="SQLite database with treatment_reports for the drug")
    parser.add_argument("--drug", required=True, help="Canonical treatment name as stored in the treatment table")
    parser.add_argument("--drug-file", type=str, default=None,
                        help="Text file of spellings for the drug, one per line (default: aliases from the treatment table)")
    parser.add_argument("--exclude-compound", action="append", default=[],
                        help="Name of a different compound whose information must not be attributed to the drug (repeatable)")
    parser.add_argument("--exclude-file", type=str, default=None,
                        help="Text file of such compound names, one per line (added to --exclude-compound). "
                             "With neither flag, the exclusions recorded by the sentiment run are used")
    parser.add_argument("--model", type=str, default=MODEL_STRONG, help=f"Model for the extraction (default: {MODEL_STRONG})")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--parent-chars", type=int, default=DEFAULT_PARENT_CHARS,
                        help="Characters of the parent post sent as context; 0 sends none")
    parser.add_argument("--solo-above-chars", type=int, default=DEFAULT_SOLO_ABOVE_CHARS,
                        help="Reports longer than this go one per call; 0 disables")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N reports (0 = all)")


def read_list_file(parser: argparse.ArgumentParser, args: argparse.Namespace, dest: str) -> list[str] | None:
    """Non-blank lines of the file the ``--dest`` flag names; None when not given, a parser error when empty."""
    path = getattr(args, dest)
    if not path:
        return None
    lines = [line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        parser.error(f"--{dest.replace('_', '-')} {path} contains no non-blank lines")
    return lines


def step_kwargs(parser: argparse.ArgumentParser, args: argparse.Namespace) -> dict[str, Any]:
    """Keyword arguments for a step's run function, from the flags add_step_arguments added."""
    excluded = args.exclude_compound + (read_list_file(parser, args, "exclude_file") or [])
    return {
        "aliases": read_list_file(parser, args, "drug_file"),
        "excluded_compounds": excluded or None,
        "model": args.model,
        "workers": args.workers,
        "batch_size": args.batch_size,
        "parent_chars": args.parent_chars or None,
        "solo_above_chars": args.solo_above_chars or None,
        "limit": args.limit or None,
    }
