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
    python src/run_pipeline.py --db data/posts.db --output-dir outputs
    # Or standalone (run from src/):
    python -m scripts.classify_sentiment --output-dir ../outputs
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database_scripts.db import ReportWriter
    from utilities import PipelineConfig

from prompts.intervention_config import system_prompt, PREFILTER_PROMPT
from utilities import (
    OutputFiles, MODEL_FAST, MODEL_STRONG, llm_call,
    parse_json_array, parse_json_object, log,
)

BATCH_SIZE = 5
PREFILTER_BATCH_SIZE = 5


def is_only_questions(text: str) -> bool:
    """Check if text contains only questions."""
    text = text.strip()
    if not text:
        return True
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    return bool(sentences) and all(s.endswith('?') for s in sentences)


def prefilter_batch(client, items: list[tuple[dict, str]], id_to_text: dict) -> list[bool]:
    """Ask Haiku if each (entry, drug) pair expresses personal experience."""
    msg = PREFILTER_PROMPT + f"\nExpecting {len(items)} answers.\n\n"
    for i, (entry, drug) in enumerate(items):
        ancestor = id_to_text.get(entry.get("parent_id", ""), "")
        msg += f"--- {i+1} --- Drug: {drug}\n"
        if ancestor:
            msg += f"Replying to: {ancestor}\n\n"
        msg += f"Comment: {entry['text'][:600]}\n\n"

    raw = llm_call(client, msg, model=MODEL_FAST, max_tokens=len(items) * 10)
    answers = parse_json_array(raw)
    if len(answers) == len(items):
        return [str(a).strip().lower().startswith("yes") for a in answers]

    # Fallback: misaligned array — classify individually
    log.warning(
        f"Prefilter array length mismatch: expected {len(items)}, got {len(answers)}. "
        "Falling back to individual calls."
    )
    results = []
    for entry, drug in items:
        ancestor = id_to_text.get(entry.get("parent_id", ""), "")
        single_msg = PREFILTER_PROMPT + f"\nExpecting 1 answer.\n\n"
        single_msg += f"--- 1 --- Drug: {drug}\n"
        if ancestor:
            single_msg += f"Replying to: {ancestor}\n\n"
        single_msg += f"Comment: {entry['text'][:600]}\n\n"
        r = llm_call(client, single_msg, model=MODEL_FAST, max_tokens=10)
        results.append(r.strip().lower().startswith("yes"))
    return results


def format_entry(entry: dict, id_to_text: dict) -> str:
    """Format entry for classification prompt."""
    msg = f"Text:\n{entry['text']}"
    ancestor = id_to_text.get(entry.get("parent_id", ""), "")
    if ancestor:
        msg += f"\n\nReplying to:\n{ancestor}"
    return msg


def classify_batch(
    client, items: list[tuple[dict, str]], id_to_text: dict, prompts: dict,
) -> list[dict]:
    """Classify a batch of (entry, drug) pairs. All must share the same drug."""
    drug = items[0][1]
    msg = f"Classify each entry separately. Return a JSON array of {len(items)} objects.\n\n"
    for i, (entry, _) in enumerate(items):
        msg += f"--- Entry {i+1} ---\n{format_entry(entry, id_to_text)}\n\n"
    msg += f'Return ONLY a JSON array of {len(items)} objects, each with only "sentiment" and "signal".'

    raw = llm_call(client, msg, model=MODEL_STRONG, system=prompts[drug], max_tokens=50 * len(items))
    results = parse_json_array(raw)
    if len(results) == len(items):
        return results
    raise ValueError(f"Expected {len(items)} results, got {len(results)}")


def run_classification(
    config: PipelineConfig,
    *,
    writer: ReportWriter | None = None,
) -> None:
    """Main classification logic — called by pipeline or standalone.

    If a ReportWriter is provided, results are written to the database
    incrementally after each result. Pairs already in the database are
    skipped unless config.reclassify is set.
    """
    client = config.client
    limit = config.limit

    tagged_path = config.path(OutputFiles.TAGGED_MENTIONS)

    tagged = json.loads(tagged_path.read_text())
    log.info(f"Loaded {len(tagged)} tagged entries.")

    # Load synonyms from treatment table (empty if no DB or canonicalize was skipped)
    if writer is not None:
        from database_scripts.db import load_synonyms
        synonyms_for = load_synonyms(config.db_path)
    else:
        synonyms_for = {}

    id_to_text = {e["id"]: e["text"] for e in tagged}

    # Filter pure questions
    before = len(tagged)
    tagged = [e for e in tagged if not is_only_questions(e["text"])]
    log.info(f"Filtered {before - len(tagged)} pure-question entries → {len(tagged)} remaining.")

    if limit:
        tagged = tagged[:limit]

    # Build work queue, skipping pairs already persisted in the database
    prompts: dict[str, str] = {}
    to_do: list[tuple[dict, str]] = []
    skipped = 0

    for entry in tagged:
        all_drugs = list(dict.fromkeys(
            entry.get("drugs_direct", []) + entry.get("drugs_context", []),
        ))
        for drug in all_drugs:
            if (
                not config.reclassify
                and writer is not None
                and writer.already_classified(entry["id"], drug)
            ):
                skipped += 1
                continue

            to_do.append((entry, drug))
            if drug not in prompts:
                prompts[drug] = system_prompt(drug, synonyms_for.get(drug))

    log.info(f"{skipped} already in DB, {len(to_do)} entry×drug pairs to process...")

    # Prefilter with Haiku (cheap — no persistence needed)
    log.info("Prefiltering...")
    filtered: set[tuple[str, str]] = set()
    for i in range(0, len(to_do), PREFILTER_BATCH_SIZE):
        batch = to_do[i:i + PREFILTER_BATCH_SIZE]
        try:
            results = prefilter_batch(client, batch, id_to_text)
            for (entry, drug), passed in zip(batch, results):
                if not passed:
                    filtered.add((entry["id"], drug))
        except Exception as e:
            raise RuntimeError(f"Prefilter batch error: {e}")
        log.info(f"Prefiltered {min(i + PREFILTER_BATCH_SIZE, len(to_do))}/{len(to_do)}...")

    # Only classify entries that passed prefilter
    to_classify = [(e, d) for e, d in to_do if (e["id"], d) not in filtered]
    log.info(f"{len(filtered)} filtered out, {len(to_classify)} to classify...")

    # Group by drug for batching (shared system prompt per drug)
    by_drug: dict[str, list[tuple[dict, str]]] = defaultdict(list)
    for e, d in to_classify:
        by_drug[d].append((e, d))

    classified = 0
    drug_counter: Counter = Counter()
    done, total = 0, len(to_classify)

    for drug, items in by_drug.items():
        for i in range(0, len(items), BATCH_SIZE):
            batch = items[i:i + BATCH_SIZE]

            try:
                results = classify_batch(
                    client, batch, id_to_text, prompts,
                )
                for (entry, drug), result in zip(batch, results):
                    if result.get("signal") != "n/a":
                        classified += 1
                        drug_counter[drug] += 1
                        if writer is not None:
                            writer.write_one(
                                post_id=entry["id"], drug=drug, author=entry["author"],
                                sentiment=result["sentiment"], signal=result["signal"],
                            )
            except Exception as e:
                log.warning(f"Batch failed for {drug}: {e}, retrying individually...")
                for entry, drug in batch:
                    try:
                        msg = format_entry(entry, id_to_text)
                        msg += '\n\nRespond ONLY with JSON: {"sentiment":"...","signal":"..."}'
                        raw = llm_call(
                            client, msg, model=MODEL_STRONG,
                            system=prompts[drug], max_tokens=50,
                        )
                        result = parse_json_object(raw)
                        if result.get("signal") != "n/a":
                            classified += 1
                            drug_counter[drug] += 1
                            if writer is not None:
                                writer.write_one(
                                    post_id=entry["id"], drug=drug, author=entry["author"],
                                    sentiment=result["sentiment"], signal=result["signal"],
                                )
                    except Exception as e2:
                        log.error(f"ERROR on {entry['id']}:{drug}: {e2}")

            done += len(batch)
            log.info(f"Classified {done}/{total}...")

    # Final stats
    log.info(f"{classified} sentiment records across {len(drug_counter)} drugs.")
    log.info("Top drugs:")
    for drug, count in drug_counter.most_common(10):
        log.info(f"  {drug:<30} {count}")


def main():
    """Standalone entry point (no database)."""
    import argparse
    from utilities import PipelineConfig, get_client

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
