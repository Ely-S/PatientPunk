#!/usr/bin/env python3
"""
classify_sentiment.py

Step 2 of the drug mention database pipeline.

For every entry in tagged_mentions.json, classify sentiment toward each
drug it references (direct or via context). Uses the same prompt and
classification logic as classify_intervention.py.

Filters out entries that are pure questions (no sentiment content).

Output: sentiment_db.json  — flat list of classified entry×drug pairs
Cache:  sentiment_cache.json — keyed "entry_id:drug", avoids reprocessing

Usage:
    python database_creation/classify_sentiment.py
    python database_creation/classify_sentiment.py --limit 100
    python database_creation/classify_sentiment.py --regenerate-cache
"""
import anthropic
import argparse, json, os, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from intervention_config import config_for, system_prompt
from utilities import DATA_DIR

DEFAULT_OUTPUT_DIR    = DATA_DIR / "outputs"
MODEL_FAST            = "claude-haiku-4-5-20251001"
MODEL_STRONG          = "claude-sonnet-4-6"
BATCH_SIZE            = 5
PREFILTER_BATCH_SIZE  = 20


# ── Filtering ─────────────────────────────────────────────────────────────────

def is_only_questions(text: str) -> bool:
    text = text.strip()
    if not text:
        return True
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    return bool(sentences) and all(s.endswith('?') for s in sentences)


# ── Prefilter ─────────────────────────────────────────────────────────────────

def prefilter_batch(client, items: list[tuple[dict, str]], id_to_text: dict) -> list[bool]:
    """Ask Haiku if each (entry, drug) pair expresses personal experience. Returns list of bool."""
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
    raw = resp.content[0].text.strip()
    start, end = raw.find("["), raw.rfind("]") + 1
    answers = json.loads(raw[start:end]) if start >= 0 else []
    if len(answers) == len(items):
        return [str(a).strip().lower().startswith("yes") for a in answers]
    return [True] * len(items)  # fallback: let everything through


# ── Cache ─────────────────────────────────────────────────────────────────────

def load_cache(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_cache(cache: dict, path: Path):
    path.write_text(encoding="utf-8", data=json.dumps(cache, indent=2))


# ── Classification ────────────────────────────────────────────────────────────

def format_entry(entry: dict, drug: str, id_to_text: dict) -> str:
    msg = f"Text:\n{entry['text']}"
    ancestor = id_to_text.get(entry.get("parent_id", ""), "")
    if ancestor:
        msg += f"\n\nReplying to:\n{ancestor}"
    return msg


def classify_batch(client, items: list[tuple[dict, str]], id_to_text: dict,
                   prompts: dict[str, str]) -> list[dict]:
    """Classify a batch of (entry, drug) pairs. All entries must share the same drug."""
    drug = items[0][1]
    prompt = prompts[drug]

    msg = f"Classify each entry separately. Return a JSON array of {len(items)} objects.\n\n"
    for i, (entry, _) in enumerate(items):
        msg += f"--- Entry {i+1} ---\n{format_entry(entry, drug, id_to_text)}\n\n"
    msg += f'Return ONLY a JSON array of {len(items)} objects, each with only "sentiment" and "signal".'

    resp = client.messages.create(
        model=MODEL_STRONG,
        max_tokens=50 * len(items),
        system=prompt,
        messages=[{"role": "user", "content": msg}],
    )
    raw = resp.content[0].text.strip()
    if "```" in raw:
        raw = raw.split("```")[1].lstrip("json")
    start, end = raw.find("["), raw.rfind("]") + 1
    results = json.loads(raw[start:end]) if start >= 0 else []
    if len(results) == len(items):
        return results
    raise ValueError(f"Expected {len(items)} results, got {len(results)}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--limit", type=int, help="Only process first N entries")
    parser.add_argument("--regenerate-cache", action="store_true")
    parser.add_argument("--debug-ldn", action="store_true",
                        help="Debug mode: only process entries related to LDN/naltrexone")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_path = output_dir / "sentiment_cache.json"

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ERROR: ANTHROPIC_API_KEY not set.")
    client = anthropic.Anthropic(api_key=api_key)

    tagged = json.loads((output_dir / "tagged_mentions.json").read_text(encoding="utf-8"))
    print(f"Loaded {len(tagged)} tagged entries.")

    # Build id -> text lookup from tagged_mentions itself
    id_to_text = {e["id"]: e["text"] for e in tagged}

    # Filter pure questions
    before = len(tagged)
    tagged = [e for e in tagged if not is_only_questions(e["text"])]
    print(f"Filtered {before - len(tagged)} pure-question entries -> {len(tagged)} remaining.")

    if args.debug_ldn:
        LDN_TERMS = {"ldn", "naltrexone", "low dose naltrexone", "low-dose naltrexone"}
        before_ldn = len(tagged)
        tagged = [
            e for e in tagged
            if LDN_TERMS & set(e.get("drugs_direct", []) + e.get("drugs_context", []))
        ]
        print(f"[debug-ldn] Filtered to {len(tagged)} entries (from {before_ldn}) with LDN/naltrexone.")

    if args.limit:
        tagged = tagged[:args.limit]

    cache = {} if args.regenerate_cache else load_cache(cache_path)

    # Build prompts cache per drug (avoid regenerating for each entry)
    prompts: dict[str, str] = {}

    # Collect all (entry, drug) pairs to classify
    LDN_TERMS = {"ldn", "naltrexone", "low dose naltrexone", "low-dose naltrexone"}
    to_do = []
    for entry in tagged:
        all_drugs = list(dict.fromkeys(entry.get("drugs_direct", []) +
                                       entry.get("drugs_context", [])))
        # In debug-ldn mode, collapse all LDN synonyms to "ldn"
        if args.debug_ldn:
            all_drugs = ["ldn"] if any(d in LDN_TERMS for d in all_drugs) else []

        for drug in all_drugs:
            key = f"{entry['id']}:{drug}"
            if key not in cache:
                to_do.append((entry, drug, key))
                if drug not in prompts:
                    prompts[drug] = system_prompt(config_for(drug))

    prefilter_cache_path = output_dir / "sentiment_prefilter_cache.json"
    prefilter_cache = {} if args.regenerate_cache else load_cache(prefilter_cache_path)

    # Prefilter with Haiku
    pf_to_do = [(entry, drug, key) for entry, drug, key in to_do
                if key not in prefilter_cache]
    print(f"{len(prefilter_cache)} prefilter-cached, {len(pf_to_do)} to prefilter...")

    for i in range(0, len(pf_to_do), PREFILTER_BATCH_SIZE):
        batch = pf_to_do[i:i + PREFILTER_BATCH_SIZE]
        pairs = [(entry, drug) for entry, drug, key in batch]
        try:
            results = prefilter_batch(client, pairs, id_to_text)
            for (entry, drug, key), passed in zip(batch, results):
                prefilter_cache[key] = passed
        except Exception as e:
            print(f"  Prefilter batch error: {e}")
            for entry, drug, key in batch:
                prefilter_cache[key] = True  # fallback: let through
        save_cache(prefilter_cache, prefilter_cache_path)
        done_pf = min(i + PREFILTER_BATCH_SIZE, len(pf_to_do))
        print(f"  Prefiltered {done_pf}/{len(pf_to_do)}...", end="\r", flush=True)
    if pf_to_do:
        print()

    passed = sum(1 for v in prefilter_cache.values() if v)
    print(f"Prefilter: {passed}/{len(prefilter_cache)} passed -> sending to Sonnet")

    # Only classify entries that passed prefilter
    to_do = [(entry, drug, key) for entry, drug, key in to_do
             if prefilter_cache.get(key, True)]

    print(f"{len(cache)} cached, {len(to_do)} to classify...")

    # Group to_do by drug so batches share the same system prompt
    from collections import defaultdict
    by_drug = defaultdict(list)
    for entry, drug, key in to_do:
        by_drug[drug].append((entry, drug, key))

    done = 0
    total = len(to_do)
    for drug, items in by_drug.items():
        for i in range(0, len(items), BATCH_SIZE):
            batch = items[i:i + BATCH_SIZE]
            pairs = [(entry, drug) for entry, drug, key in batch]
            try:
                results = classify_batch(client, pairs, id_to_text, prompts)
                for (entry, drug, key), result in zip(batch, results):
                    if result.get("signal") != "n/a":
                        cache[key] = {**result, "author": entry["author"], "text": entry["text"], "created_utc": entry.get("created_utc")}
                        save_cache(cache, cache_path)
            except Exception as e:
                print(f"\n  Batch failed for {drug}: {e}, retrying individually...")
                for entry, drug, key in batch:
                    try:
                        msg = format_entry(entry, drug, id_to_text)
                        msg += '\n\nRespond ONLY with JSON: {"sentiment":"...","signal":"..."}'
                        resp = client.messages.create(
                            model=MODEL_STRONG, max_tokens=50,
                            system=prompts[drug],
                            messages=[{"role": "user", "content": msg}],
                        )
                        raw = resp.content[0].text.strip()
                        s, e2 = raw.find("{"), raw.rfind("}") + 1
                        result = json.loads(raw[s:e2])
                        if result.get("signal") != "n/a":
                            cache[key] = {**result, "author": entry["author"], "text": entry["text"], "created_utc": entry.get("created_utc")}
                        save_cache(cache, cache_path)
                    except Exception as e3:
                        print(f"  ERROR on {key}: {e3}")
            done += len(batch)
            print(f"  Classified {done}/{total}...", end="\r", flush=True)

    print()

    from collections import Counter
    drug_counts = Counter(drug for key in cache for drug in [key.split(":", 1)[1]])
    print(f"\n{len(cache)} sentiment records across {len(drug_counts)} drugs.")
    print("Top drugs:")
    for drug, count in drug_counts.most_common(10):
        print(f"  {drug:<30} {count}")
    print(f"\nResults in {cache_path.name}")


if __name__ == "__main__":
    main()
