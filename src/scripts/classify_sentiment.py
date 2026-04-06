#!/usr/bin/env python3
"""
classify_sentiment.py — Classify sentiment toward drugs.

Step 3 of the pipeline. For each entry×drug pair, classifies sentiment
(positive/negative/mixed/neutral) and signal strength.
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from prompts.intervention_config import system_prompt
from utilities import MODEL_FAST, MODEL_STRONG, load_cache, save_cache, parse_json_array, parse_json_object, log
BATCH_SIZE = 5
PREFILTER_BATCH_SIZE = 20


def is_only_questions(text: str) -> bool:
    """Check if text contains only questions."""
    text = text.strip()
    if not text:
        return True
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    return bool(sentences) and all(s.endswith('?') for s in sentences)


def prefilter_batch(client, items: list[tuple[dict, str]], id_to_text: dict) -> list[bool]:
    """Ask Haiku if each (entry, drug) pair expresses personal experience."""
    msg = (
        f"For each item below, answer ONLY 'yes' or 'no':\n"
        f"Does the AUTHOR express personal experience with the specified drug/intervention?\n"
        f"Also 'yes' if the reply implies it works by saying NOT doing it made things worse.\n"
        f"Return a JSON array of {len(items)} strings, each 'yes' or 'no', in order.\n\n"
    )
    for i, (entry, drug) in enumerate(items):
        ancestor = id_to_text.get(entry.get("parent_id", ""), "")
        msg += f"--- {i+1} --- Drug: {drug}\n"
        if ancestor:
            msg += f"Replying to: {ancestor}\n\n"
        msg += f"Comment: {entry['text'][:600]}\n\n"

    resp = client.messages.create(
        model=MODEL_FAST,
        max_tokens=PREFILTER_BATCH_SIZE * 10,
        messages=[{"role": "user", "content": msg}],
    )
    answers = parse_json_array(resp.content[0].text)
    if len(answers) == len(items):
        return [str(a).strip().lower().startswith("yes") for a in answers]
    return [True] * len(items)  # fallback


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

    resp = client.messages.create(
        model=MODEL_STRONG,
        max_tokens=50 * len(items),
        system=prompts[drug],
        messages=[{"role": "user", "content": msg}],
    )
    results = parse_json_array(resp.content[0].text)
    if len(results) == len(items):
        return results
    raise ValueError(f"Expected {len(items)} results, got {len(results)}")


def run_classification(client, output_dir: Path, limit: int = None, regenerate_cache: bool = False):
    """Main classification logic — called by pipeline or standalone."""
    cache_path = output_dir / "sentiment_cache.json"
    prefilter_cache_path = output_dir / "sentiment_prefilter_cache.json"
    canon_map_path = output_dir / "canonical_map.json"

    tagged = json.loads((output_dir / "tagged_mentions.json").read_text())
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
    prefilter_cache = {} if regenerate_cache else load_cache(prefilter_cache_path)

    # Build prompts per drug (with synonyms)
    prompts = {}
    to_do = []
    for entry in tagged:
        all_drugs = list(dict.fromkeys(entry.get("drugs_direct", []) + entry.get("drugs_context", [])))
        for drug in all_drugs:
            key = f"{entry['id']}:{drug}"
            if key not in cache:
                to_do.append((entry, drug, key))
                if drug not in prompts:
                    prompts[drug] = system_prompt(drug, synonyms_for.get(drug))

    # Prefilter with Haiku
    pf_to_do = [(e, d, k) for e, d, k in to_do if k not in prefilter_cache]
    log.info(f"{len(prefilter_cache)} prefilter-cached, {len(pf_to_do)} to prefilter...")

    for i in range(0, len(pf_to_do), PREFILTER_BATCH_SIZE):
        batch = pf_to_do[i:i + PREFILTER_BATCH_SIZE]
        try:
            results = prefilter_batch(client, [(e, d) for e, d, k in batch], id_to_text)
            for (e, d, k), passed in zip(batch, results):
                prefilter_cache[k] = passed
        except Exception as e:
            log.error(f"Prefilter batch error: {e}")
            for _, _, k in batch:
                prefilter_cache[k] = True
        save_cache(prefilter_cache, prefilter_cache_path)
        log.info(f"Prefiltered {min(i + PREFILTER_BATCH_SIZE, len(pf_to_do))}/{len(pf_to_do)}...")

    passed = sum(1 for v in prefilter_cache.values() if v)
    log.info(f"Prefilter: {passed}/{len(prefilter_cache)} passed → sending to Sonnet")

    # Only classify entries that passed prefilter
    to_do = [(e, d, k) for e, d, k in to_do if prefilter_cache.get(k, True)]
    log.info(f"{len(cache)} cached, {len(to_do)} to classify...")

    # Group by drug for batching
    by_drug = defaultdict(list)
    for e, d, k in to_do:
        by_drug[d].append((e, d, k))

    done, total = 0, len(to_do)
    for drug, items in by_drug.items():
        for i in range(0, len(items), BATCH_SIZE):
            batch = items[i:i + BATCH_SIZE]
            try:
                results = classify_batch(client, [(e, d) for e, d, k in batch], id_to_text, prompts)
                for (entry, drug, key), result in zip(batch, results):
                    if result.get("signal") != "n/a":
                        cache[key] = {**result, "author": entry["author"], "text": entry["text"],
                                     "created_utc": entry.get("created_utc")}
                        save_cache(cache, cache_path)
            except Exception as e:
                log.warning(f"Batch failed for {drug}: {e}, retrying individually...")
                for entry, drug, key in batch:
                    try:
                        msg = format_entry(entry, id_to_text)
                        msg += '\n\nRespond ONLY with JSON: {"sentiment":"...","signal":"..."}'
                        resp = client.messages.create(
                            model=MODEL_STRONG, max_tokens=50,
                            system=prompts[drug],
                            messages=[{"role": "user", "content": msg}],
                        )
                        result = parse_json_object(resp.content[0].text)
                        if result.get("signal") != "n/a":
                            cache[key] = {**result, "author": entry["author"], "text": entry["text"],
                                         "created_utc": entry.get("created_utc")}
                        save_cache(cache, cache_path)
                    except Exception as e2:
                        log.error(f"ERROR on {key}: {e2}")
            done += len(batch)
            log.info(f"Classified {done}/{total}...")

    drug_counts = Counter(k.split(":", 1)[1] for k in cache)
    log.info(f"{len(cache)} sentiment records across {len(drug_counts)} drugs.")
    log.info("Top drugs:")
    for drug, count in drug_counts.most_common(10):
        log.info(f"  {drug:<30} {count}")


def main():
    """Standalone entry point."""
    import argparse
    from utilities import get_client

    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, help="Directory containing tagged_mentions.json")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--regenerate-cache", action="store_true")
    args = parser.parse_args()

    run_classification(get_client(), Path(args.output_dir), args.limit, args.regenerate_cache)


if __name__ == "__main__":
    main()
