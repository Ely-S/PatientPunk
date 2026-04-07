#!/usr/bin/env python3
"""
classify_sentiment.py — Classify sentiment toward drugs.

Step 3 of the pipeline. For each entry×drug pair, classifies sentiment
(positive/negative/mixed/neutral) and signal strength. Note that this will take into 
account the context of the post/comment and the drug/intervention mentioned.

The output format is:
    {
        "id": "t3_1scqprg",
        "author": "u_1234567890",
        "text": "I took 100mg of LSD last night and it was amazing!",
        "created_utc": 1717334400,
        "sentiment": "positive",
        "signal": "strong",
    },
        {
        "id": "t3_1scqprg",
        "author": "u_1234567890",
        "text": "I took it last night and it was amazing!",
        "created_utc": 1717334400,
        "sentiment": "positive",
        "signal": "strong",
    },

Usage:
    python src/run_pipeline.py --posts-file data/posts.json --output-dir outputs classify
    # Or standalone (run from src/):
    python -m scripts.classify_sentiment --output-dir ../outputs
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utilities import PipelineConfig

from prompts.intervention_config import system_prompt, PREFILTER_PROMPT
from utilities import (
    OutputFiles, MODEL_FAST, MODEL_STRONG, llm_call,
    load_cache, save_cache, parse_json_array, parse_json_object, log
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
    log.debug(f"Prefilter raw response: {raw!r}")
    answers = parse_json_array(raw)
    if len(answers) == len(items):
        return [str(a).strip().lower().startswith("yes") for a in answers]
    
    # Fallback: misaligned array — classify individually
    log.warning(f"Prefilter array length mismatch: expected {len(items)}, got {len(answers)}. Falling back to individual calls.")
    results = []
    for entry, drug in items:
        ancestor = id_to_text.get(entry.get("parent_id", ""), "")
        single_msg = PREFILTER_PROMPT + f"\nExpecting 1 answer.\n\n"
        single_msg += f"--- 1 --- Drug: {drug}\n"
        if ancestor:
            single_msg += f"Replying to: {ancestor}\n\n"
        single_msg += f"Comment: {entry['text'][:600]}\n\n"
        raw = llm_call(client, single_msg, model=MODEL_FAST, max_tokens=10)
        results.append(raw.strip().lower().startswith("yes"))
    return results


def format_entry(entry: dict, id_to_text: dict) -> str:
    """Format entry for classification prompt."""
    msg = f"Text:\n{entry['text']}"
    ancestor = id_to_text.get(entry.get("parent_id", ""), "")
    if ancestor:
        msg += f"\n\nReplying to:\n{ancestor}"
    return msg


def classify_batch(client, items: list[tuple[dict, str]], id_to_text: dict, prompts: dict) -> list[dict]:
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


def run_classification(config: "PipelineConfig"):
    """Main classification logic — called by pipeline or standalone."""
    client = config.client
    limit = config.limit
    regenerate_cache = config.regenerate_cache

    cache_path = config.path(OutputFiles.SENTIMENT_CACHE)
    filtered_path = config.path(OutputFiles.FILTERED_CACHE)
    canon_map_path = config.path(OutputFiles.CANONICAL_MAP)
    tagged_path = config.path(OutputFiles.TAGGED_MENTIONS)

    tagged = json.loads(tagged_path.read_text())
    log.info(f"Loaded {len(tagged)} tagged entries.")

    # Build reverse synonym map: canonical → [synonyms]
    synonyms_for = defaultdict(list)
    if canon_map_path.exists():
        canon_map = json.loads(canon_map_path.read_text())
        for raw, canonical in canon_map.items():
            if raw != canonical:
                synonyms_for[canonical].append(raw)

    id_to_text = {e["id"]: e["text"] for e in tagged}

    # Filter pure questions
    before = len(tagged)
    tagged = [e for e in tagged if not is_only_questions(e["text"])]
    log.info(f"Filtered {before - len(tagged)} pure-question entries → {len(tagged)} remaining.")

    if limit:
        tagged = tagged[:limit]

    cache = {} if regenerate_cache else load_cache(cache_path)
    filtered = {} if regenerate_cache else load_cache(filtered_path)

    # Build prompts per drug (with synonyms)
    # Collect all entry×drug pairs not yet in cache
    prompts = {}
    to_do = []
    for entry in tagged:
        all_drugs = list(dict.fromkeys(entry.get("drugs_direct", []) + entry.get("drugs_context", [])))
        for drug in all_drugs:
            key = f"{entry['id']}:{drug}"
            if key not in cache and key not in filtered:
                to_do.append((entry, drug, key))
                if drug not in prompts:
                    prompts[drug] = system_prompt(drug, synonyms_for.get(drug))

    log.info(f"{len(cache)} classified, {len(filtered)} filtered, {len(to_do)} to process...")

    # Prefilter with Haiku
    log.info("Prefiltering...")
    for i in range(0, len(to_do), PREFILTER_BATCH_SIZE):
        batch = to_do[i:i + PREFILTER_BATCH_SIZE]
        try:
            results = prefilter_batch(client, [(e, d) for e, d, k in batch], id_to_text)
            for (entry, drug, key), passed in zip(batch, results):
                if not passed:
                    filtered[key] = True
        except Exception as e:
            raise RuntimeError(f"Prefilter batch error: {e}")
        if (i // PREFILTER_BATCH_SIZE) % 10 == 0:
            save_cache(filtered, filtered_path)
        log.info(f"Prefiltered {min(i + PREFILTER_BATCH_SIZE, len(to_do))}/{len(to_do)}...")

    # Only classify entries that passed prefilter
    to_classify = [(e, d, k) for e, d, k in to_do if k not in filtered]
    log.info(f"{len(filtered)} filtered out, {len(cache)} classified, {len(to_classify)} to classify...")

    # Group by drug for batching
    by_drug = defaultdict(list)
    for e, d, k in to_classify:
        by_drug[d].append((e, d, k))

    done, total = 0, len(to_classify)
    for drug, items in by_drug.items():
        for i in range(0, len(items), BATCH_SIZE):
            batch = items[i:i + BATCH_SIZE]
            try:
                results = classify_batch(client, [(e, d) for e, d, k in batch], id_to_text, prompts)
                for (entry, drug, key), result in zip(batch, results):
                    if result.get("signal") == "n/a":
                        filtered[key] = True
                        save_cache(filtered, filtered_path)
                    else:
                        cache[key] = {**result, "author": entry["author"], "text": entry["text"],
                                     "created_utc": entry.get("created_utc")}
                        save_cache(cache, cache_path)
            except Exception as e:
                log.warning(f"Batch failed for {drug}: {e}, retrying individually...")
                for entry, drug, key in batch:
                    try:
                        msg = format_entry(entry, id_to_text)
                        msg += '\n\nRespond ONLY with JSON: {"sentiment":"...","signal":"..."}'
                        raw = llm_call(client, msg, model=MODEL_STRONG, system=prompts[drug], max_tokens=50)
                        result = parse_json_object(raw)
                        if result.get("signal") == "n/a":
                            filtered[key] = True
                            save_cache(filtered, filtered_path)
                        else:
                            cache[key] = {**result, "author": entry["author"], "text": entry["text"],
                                         "created_utc": entry.get("created_utc")}
                            save_cache(cache, cache_path)
                    except Exception as e2:
                        log.error(f"ERROR on {key}: {e2}")
            done += len(batch)
            log.info(f"Classified {done}/{total}...")

    # Final stats
    drug_counts = Counter(k.split(":", 1)[1] for k in cache)
    log.info(f"{len(cache)} sentiment records across {len(drug_counts)} drugs.")
    log.info("Top drugs:")
    for drug, count in drug_counts.most_common(10):
        log.info(f"  {drug:<30} {count}")


def main():
    """Standalone entry point."""
    import argparse
    from utilities import PipelineConfig, get_client

    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, help="Directory containing tagged_mentions.json")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--regenerate-cache", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    config = PipelineConfig(
        client=get_client(),
        output_dir=output_dir,
        posts_file=Path("."),  # Not used by classify
        limit=args.limit or 0,
        regenerate_cache=args.regenerate_cache,
    )
    run_classification(config)


if __name__ == "__main__":
    main()
