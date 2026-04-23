#!/usr/bin/env python3
"""
canonicalize.py — Normalize drug synonyms.

Step 2 of the pipeline. Merges synonyms (e.g. "low dose naltrexone" → "ldn")
and writes canonicalized_mentions.json with canonical names. The original
tagged_mentions.json is left untouched.
"""
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utilities import PipelineConfig

from utilities import (
    TAGGED_MENTIONS, CANONICALIZED_MENTIONS, MODEL_STRONG, LLMParseError,
    llm_call, parse_json_object, log,
)
from utilities.db import upsert_treatments
from prompts.intervention_config import CANONICALIZE_COMPOUND_PROMPT

BATCH_SIZE = 3500

# Hardcoded alias sets for --drug mode. Keys are canonical names,
# values are alternate names seen in the corpus.
HARDCODED_ALIASES: dict[str, list[str]] = {
    "ldn": [
        "low dose naltrexone",
        "low-dose naltrexone",
        "naltrexone",
        "dextro-naltrexone",
        "low dose nalproxone",
        "moderate-dose ldn",
        "ultra low dose ldn",
    ],
}


def canonicalize_batch(client, names: list[str], model=MODEL_STRONG) -> dict[str, str]:
    """Ask the strong model to group synonyms among a list of drug names."""
    msg = CANONICALIZE_COMPOUND_PROMPT + f"\n\nDrug names to canonicalize:\n{json.dumps(names)}"
    # Output is merges-only (~20 tokens per merge); budget ~15 tokens/name
    # to safely accommodate batches with high merge rates without truncating.
    max_toks = max(2000, len(names) * 15)
    raw = llm_call(client, msg, model=model, max_tokens=max_toks)
    return {n: n for n in names} | parse_json_object(raw)


def _canonicalize_entries(tagged: list[dict], canon_map: dict[str, str]) -> None:
    """In-place: replace drug names with canonical forms, dedup preserving order."""
    for entry in tagged:
        for key in ("drugs_direct", "drugs_context"):
            entry[key] = list(dict.fromkeys(canon_map.get(d, d) for d in entry.get(key, [])))


def run_targeted_canonicalization(config: "PipelineConfig") -> dict[str, str]:
    """Skip the LLM; use HARDCODED_ALIASES[target] to merge synonyms into target."""
    import sys
    target = config.drug.strip().lower()
    if target not in HARDCODED_ALIASES:
        raise ValueError(f"--drug {target!r} has no hardcoded alias set. Known: {sorted(HARDCODED_ALIASES)}")

    aliases = [a.lower() for a in HARDCODED_ALIASES[target]]
    canon_map = {a: target for a in [*aliases, target]}

    tagged = json.loads(config.path(TAGGED_MENTIONS).read_text(encoding="utf-8"))
    _canonicalize_entries(tagged, canon_map)

    filtered = [e for e in tagged if target in e.get("drugs_direct", []) or target in e.get("drugs_context", [])]
    config.path(CANONICALIZED_MENTIONS).write_text(json.dumps(filtered, indent=2))
    upsert_treatments(config.db_path, {target}, {target: aliases})
    log.info(f"Targeted canonicalize: {target!r} ← {aliases} | kept {len(filtered)}/{len(tagged)} entries")
    return canon_map


def run_canonicalization(config: "PipelineConfig") -> dict[str, str]:
    """Main canonicalization logic. Returns {raw_name: canonical_name}."""
    if config.drug:
        return run_targeted_canonicalization(config)

    client = config.client
    tagged_path = config.path(TAGGED_MENTIONS)
    tagged = json.loads(tagged_path.read_text(encoding="utf-8"))
    all_drugs = sorted({d for e in tagged for d in e.get("drugs_direct", []) + e.get("drugs_context", [])})
    log.info(f"{len(tagged)} entries, {len(all_drugs)} unique drug names.")

    # Single pass: one LLM call per batch, no rotation/multi-pass. Trusting
    # the strong model to find synonyms within a single large batch.
    canon_map: dict[str, str] = {}
    batches = [all_drugs[i:i + BATCH_SIZE] for i in range(0, len(all_drugs), BATCH_SIZE)]
    for i, batch in enumerate(batches, 1):
        log.info(f"batch {i}/{len(batches)} ({len(batch)} names): calling LLM...")
        t0 = time.monotonic()
        try:
            batch_result = canonicalize_batch(client, batch)
            merges = sum(1 for k, v in batch_result.items() if k != v)
            log.info(f"batch {i}/{len(batches)} done: "
                     f"{merges} merges in {time.monotonic() - t0:.1f}s")
            canon_map.update(batch_result)
        except LLMParseError as e:
            log.error(f"batch {i}/{len(batches)} failed after "
                      f"{time.monotonic() - t0:.1f}s: {e}. Keeping raw names.")
            for n in batch:
                canon_map[n] = n

    # Group synonyms for logging and alias table
    aliases_for: dict[str, list[str]] = {}
    for raw, canonical in canon_map.items():
        if raw != canonical:
            aliases_for.setdefault(canonical, []).append(raw)
    if aliases_for:
        log.info(f"Synonym groups ({len(aliases_for)}):")
        for canonical, synonyms in sorted(aliases_for.items()):
            log.info(f"  {canonical} ← {', '.join(synonyms)}")

    _canonicalize_entries(tagged, canon_map)
    canonicalized_path = config.path(CANONICALIZED_MENTIONS)
    canonicalized_path.write_text(json.dumps(tagged, indent=2))
    log.info(f"Wrote {canonicalized_path.name} with canonical names.")

    all_canonical = {v for v in canon_map.values() if v.strip()}
    count = upsert_treatments(config.db_path, all_canonical, aliases_for)
    log.info(f"{count} treatments in database.")

    return canon_map


def main():
    """Standalone entry point."""
    import argparse
    from utilities import PipelineConfig, get_client

    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    config = PipelineConfig(
        client=get_client(), output_dir=Path(args.output_dir), db_path=Path("."),
    )
    run_canonicalization(config)


if __name__ == "__main__":
    main()
