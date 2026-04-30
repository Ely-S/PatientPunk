#!/usr/bin/env python3
"""
classify_sentiment.py — Classify sentiment toward drugs.

Step 3 of the pipeline. For each entry×drug pair, classifies sentiment
(positive/negative/mixed/neutral) and signal strength. Note that this will take into
account the context of the post/comment and the drug/intervention mentioned.

Results are written incrementally to the database (if a ReportWriter is provided),
so progress is preserved across crashes. On re-run, pairs already in the database
are skipped unless --reclassify is set.

Usage:
    python src/run_sentiment_pipeline.py --db data/posts.db --output-dir outputs
    # Or standalone (run from src/):
    python -m scripts.classify_sentiment --output-dir ../outputs
"""
from __future__ import annotations

import argparse
import itertools
import json
from collections import Counter, defaultdict
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from models import ClassificationResult
from prompts.intervention_config import system_prompt, PREFILTER_PROMPT
from utilities import (
    TAGGED_MENTIONS, CANONICALIZED_MENTIONS, MODEL_FAST, MODEL_STRONG, LLMParseError,
    PipelineConfig, get_client, resolve_aliases, llm_call, parse_json_array, parse_json_object, log,
)
from utilities.db import load_synonyms, open_db, post_text

if TYPE_CHECKING:
    from utilities.db import ReportWriter

BATCH_SIZE = 5
PREFILTER_BATCH_SIZE = 20


def _pf_key(entry: dict, drug: str) -> str:
    """Cache/filter key for a single (entry, drug) pair."""
    return f"{entry['id']}:{drug}"


def _is_yes(s: str) -> bool:
    return str(s).strip().lower().startswith("yes")


def _prefilter_block(i: int, entry: dict, drug: str, id_to_text: dict, max_upstream_chars: int | None = None) -> str:
    """Format a single (entry, drug) item for the prefilter prompt."""
    upstream_comment = id_to_text.get(entry.get("parent_id", ""), "")
    block = f"--- {i+1} --- Drug: {drug}\n"
    if upstream_comment:
        block += f"Replying to: {upstream_comment[:max_upstream_chars]}\n\n"
    block += f"Comment: {entry['text']}\n\n"
    return block


def _prefilter_one(client, entry: dict, drug: str, id_to_text: dict, max_upstream_chars: int | None = None) -> bool:
    """Fallback single-item prefilter call."""
    msg = PREFILTER_PROMPT + "\nExpecting 1 answer.\n\n" + _prefilter_block(0, entry, drug, id_to_text, max_upstream_chars)
    return _is_yes(llm_call(client, msg, model=MODEL_FAST, max_tokens=10))


def prefilter_batch(client, items: list[tuple[dict, str]], id_to_text: dict, max_upstream_chars: int | None = None) -> list[bool]:
    """Ask fast model if each (entry, drug) pair expresses personal experience."""
    blocks = [_prefilter_block(i, e, d, id_to_text, max_upstream_chars) for i, (e, d) in enumerate(items)]
    msg = f"{PREFILTER_PROMPT}\nExpecting {len(items)} answers.\n\n{''.join(blocks)}"
    try:
        answers = parse_json_array(llm_call(client, msg, model=MODEL_FAST, max_tokens=len(items) * 10))
        if len(answers) != len(items):
            raise LLMParseError(f"expected {len(items)} answers, got {len(answers)}")
        return [_is_yes(a) for a in answers]
    except LLMParseError as err:
        log.warning(f"Prefilter batch failed ({err}); falling back to individual calls.")
        return [_prefilter_one(client, e, d, id_to_text, max_upstream_chars) for e, d in items]


def format_entry(entry: dict, id_to_text: dict, max_upstream_chars: int | None = None) -> str:
    """Format entry for classification prompt."""
    msg = f"Text:\n{entry['text']}"
    upstream_comment = id_to_text.get(entry.get("parent_id", ""), "")
    if upstream_comment:
        msg += f"\n\nReplying to:\n{upstream_comment[:max_upstream_chars]}"
    return msg


def classify_batch(
    client, items: list[tuple[dict, str]], id_to_text: dict, prompts: dict,
    max_upstream_chars: int | None = None,
) -> list[dict]:
    """Classify a batch of (entry, drug) pairs. All must share the same drug."""
    drug = items[0][1]
    msg = f"Classify each entry separately. Return a JSON array of {len(items)} objects.\n\n"
    for i, (entry, _) in enumerate(items):
        msg += f"--- Entry {i+1} ---\n{format_entry(entry, id_to_text, max_upstream_chars)}\n\n"
    msg += (
        f'Return ONLY a JSON array of {len(items)} objects, each with '
        f'"sentiment" (positive/negative/mixed/neutral), '
        f'"signal" (strong/moderate/weak/n/a), '
        f'and "side_effects" (array of short lowercase symptom strings, or []).'
    )

    raw = llm_call(client, msg, model=MODEL_STRONG, system=prompts[drug], max_tokens=80 * len(items))
    results = parse_json_array(raw)  # raises LLMParseError on bad JSON
    if len(results) != len(items):
        raise LLMParseError(f"Expected {len(items)} results, got {len(results)}")
    return [ClassificationResult.model_validate(r) for r in results]


def _classify_one(
    client, entry: dict, drug: str, id_to_text: dict, prompts: dict,
    max_upstream_chars: int | None = None,
) -> ClassificationResult:
    """Fallback single-item classify call; returns a null result on failure."""
    try:
        msg = format_entry(entry, id_to_text, max_upstream_chars) + (
            '\n\nRespond ONLY with JSON: {"sentiment":"positive/negative/mixed/neutral","signal":"strong/moderate/weak/n/a","side_effects":["..."]}'
        )
        raw = llm_call(client, msg, model=MODEL_STRONG, system=prompts[drug], max_tokens=100)
        return ClassificationResult.model_validate(parse_json_object(raw))
    except (LLMParseError, ValidationError) as e:
        log.warning(f"Skipping {entry['id']}:{drug}: {e}")
        return ClassificationResult(sentiment="neutral", signal="n/a")


def run_classification(
    config: PipelineConfig,
    *,
    writer: ReportWriter | None = None,
    skip_prefilter: bool = False,
) -> None:
    """Main classification logic — called by pipeline or standalone.

    If a ReportWriter is provided, results are written to the database
    incrementally after each result. Pairs already in the database are
    skipped unless config.reclassify is set.
    """
    client = config.client
    limit = config.limit

    canonicalized_path = config.path(CANONICALIZED_MENTIONS)
    tagged_path = canonicalized_path if canonicalized_path.exists() else config.path(TAGGED_MENTIONS)

    tagged = json.loads(tagged_path.read_text(encoding="utf-8"))
    log.info(f"Loaded {len(tagged)} entries from {tagged_path.name}.")

    # Load synonyms and subreddit from DB (empty defaults if no DB)
    if writer is not None:
        synonyms_for = load_synonyms(config.db_path)
        with open_db(config.db_path) as conn:
            row = conn.execute("SELECT DISTINCT source_subreddit FROM users LIMIT 1").fetchone()
        subreddit = row[0] if row else "Long COVID"
    else:
        synonyms_for = {}
        subreddit = "Long COVID"

    target_aliases: set[str] | None = None
    if config.drug:
        target, aliases = resolve_aliases(config)
        target_aliases = set(aliases)
        log.info(f"Restricting classification to: {sorted(target_aliases)}")

    if limit:
        tagged = tagged[:limit]

    # Parent-context lookup: start from entries in `tagged` (text already loaded),
    # then backfill only parent_ids dropped upstream (e.g. question-only parents
    # filtered in extract) with a single DB query.
    id_to_text: dict[str, str] = {e["id"]: e["text"] for e in tagged}
    missing = {
        pid for e in tagged
        if (pid := e.get("parent_id")) and pid not in id_to_text
    }
    if missing:
        placeholders = ",".join("?" * len(missing))
        with open_db(config.db_path) as conn:
            rows = conn.execute(
                f"SELECT post_id, title, parent_id, body_text FROM posts "
                f"WHERE post_id IN ({placeholders})",
                list(missing),
            ).fetchall()
        for post_id, title, parent_id, body_text in rows:
            id_to_text[post_id] = post_text(title, body_text, parent_id)

    # Build work queue, skipping pairs already persisted in the database
    prompts: dict[str, str] = {}
    to_do: list[tuple[dict, str]] = []
    skipped = 0

    for entry in tagged:
        all_drugs = set(entry.get("drugs_direct", [])) | set(entry.get("drugs_context", []))
        for drug in all_drugs:
            if target_aliases is not None and drug not in target_aliases:
                continue
            if (
                not config.reclassify
                and writer is not None
                and writer.already_classified(entry["id"], drug)
            ):
                skipped += 1
                continue

            to_do.append((entry, drug))
            if drug not in prompts:
                prompts[drug] = system_prompt(drug, synonyms_for.get(drug), subreddit)

    log.info(f"{skipped} already in DB, {len(to_do)} entry×drug pairs to process...")

    # Prefilter with fast model — results cached to prefilter_results.json
    prefilter_path = config.path("prefilter_results.json")
    filtered: set[str] = set()
    if skip_prefilter:
        log.info("Skipping prefilter, sending all pairs to classify...")
    else:
        cached_pf: dict[str, bool] = (
            json.loads(prefilter_path.read_text()) if prefilter_path.exists() else {}
        )
        if cached_pf:
            log.info(f"Loaded {len(cached_pf)} cached prefilter results.")

        # Single-pass split: cached → apply to filtered set; uncached → queue for LLM
        uncached: list[tuple[dict, str]] = []
        for e, d in to_do:
            key = _pf_key(e, d)
            cached = cached_pf.get(key)
            if cached is None:
                uncached.append((e, d))
            elif not cached:
                filtered.add(key)

        log.info(f"Prefiltering {len(uncached)} uncached pairs ({len(to_do) - len(uncached)} cached)...")

        if uncached:
            prefilter_batches = [
                uncached[i:i + PREFILTER_BATCH_SIZE]
                for i in range(0, len(uncached), PREFILTER_BATCH_SIZE)
            ]
            done_pf = 0
            with ThreadPoolExecutor(max_workers=config.workers) as pool:
                futures = {
                    pool.submit(prefilter_batch, client, batch, id_to_text, config.max_upstream_chars): batch
                    for batch in prefilter_batches
                }
                for future in as_completed(futures):
                    batch = futures[future]
                    results = future.result()
                    for (entry, drug), passed in zip(batch, results):
                        key = _pf_key(entry, drug)
                        cached_pf[key] = passed
                        if not passed:
                            filtered.add(key)
                    done_pf += len(batch)
                    if done_pf % (PREFILTER_BATCH_SIZE * 10) == 0:
                        prefilter_path.write_text(json.dumps(cached_pf))
                    log.info(f"Prefiltered {done_pf}/{len(uncached)}...")
            prefilter_path.write_text(json.dumps(cached_pf))

    # Only classify entries that passed prefilter
    to_classify = [(e, d) for e, d in to_do if _pf_key(e, d) not in filtered]
    log.info(f"{len(filtered)} filtered out, {len(to_classify)} to classify...")

    # Group by drug for batching (shared system prompt per drug)
    by_drug: dict[str, list[tuple[dict, str]]] = defaultdict(list)
    for e, d in to_classify:
        by_drug[d].append((e, d))

    drug_counter: Counter = Counter()
    done, total = 0, len(to_classify)

    def _classify_one_batch(batch):
        """Classify a single batch, with per-item fallback on failure."""
        drug = batch[0][1]
        try:
            return batch, classify_batch(client, batch, id_to_text, prompts, config.max_upstream_chars)
        except (LLMParseError, ValidationError) as e:
            log.warning(f"Batch failed for {drug} ({e}); retrying individually...")
            return batch, [
                _classify_one(client, entry, d, id_to_text, prompts, config.max_upstream_chars)
                for entry, d in batch
            ]

    # Bounded submission: at most workers * 2 futures in flight at once.
    # As each completes the next batch is submitted (backpressure).
    batch_iter = (batch for items in by_drug.values() for batch in itertools.batched(items, BATCH_SIZE))
    max_inflight = max(config.workers * 2, 1)

    with ThreadPoolExecutor(max_workers=config.workers) as pool:
        pending: dict[Future, list] = {}

        for batch in itertools.islice(batch_iter, max_inflight):
            f = pool.submit(_classify_one_batch, batch)
            pending[f] = batch

        while pending:
            future = next(as_completed(pending))
            pending.pop(future)
            batch, results = future.result()

            for (entry, drug), result in zip(batch, results):
                if result.signal != "n/a":
                    drug_counter[drug] += 1
                    if writer is not None:
                        writer.write_one(
                            post_id=entry["id"], drug=drug, author=entry["author"],
                            sentiment=result.sentiment, signal=result.signal,
                            side_effects=result.side_effects,
                        )
            done += len(batch)
            log.info(f"Classified {done}/{total}...")

            next_batch = next(batch_iter, None)
            if next_batch is not None:
                f = pool.submit(_classify_one_batch, next_batch)
                pending[f] = next_batch

    # Final stats
    log.info(f"{sum(drug_counter.values())} sentiment records across {len(drug_counter)} drugs.")
    log.info("Top drugs:")
    for drug, count in drug_counter.most_common(10):
        log.info(f"  {drug:<30} {count}")


def main():
    """Standalone entry point (no database)."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, help="Directory containing tagged_mentions.json")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--reclassify", action="store_true")
    args = parser.parse_args()

    config = PipelineConfig(
        client=get_client(),
        output_dir=Path(args.output_dir),
        db_path=Path("."),  # Not used by classify
        limit=args.limit or 0,
        reclassify=args.reclassify,
    )
    run_classification(config)


if __name__ == "__main__":
    main()
