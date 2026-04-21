#!/usr/bin/env python3
"""
canonicalize.py — Normalize drug synonyms.

Step 2 of the pipeline. Merges synonyms (e.g. "low dose naltrexone" → "ldn")
and rewrites tagged_mentions.json with canonical names.
"""
from collections import defaultdict

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utilities import PipelineConfig

from utilities import (
    TAGGED_MENTIONS, MODEL_FAST, LLMParseError,
    llm_call, parse_json_object, log,
)
from utilities.db import upsert_treatments
from prompts.intervention_config import CANONICALIZE_COMPOUND_PROMPT

BATCH_SIZE = 50


def canonicalize_batch(client, names: list[str], model=MODEL_FAST) -> dict[str, str]:
    """Ask Haiku to group synonyms among a list of drug names."""
    msg = CANONICALIZE_COMPOUND_PROMPT + f"\n\nDrug names to canonicalize:\n{json.dumps(names)}"
    raw = llm_call(client, msg, model=model, max_tokens=len(names) * 30)
    result = parse_json_object(raw)
    for name in names:
        if name not in result:
            result[name] = name
    return result


def run_canonicalization(config: "PipelineConfig") -> dict[str, str]:
    """Main canonicalization logic. Returns {raw_name: canonical_name}."""
    client = config.client
    tagged_path = config.path(TAGGED_MENTIONS)
    tagged = json.loads(tagged_path.read_text(encoding="utf-8"))
    all_drugs = sorted({d for e in tagged for d in e.get("drugs_direct", []) + e.get("drugs_context", [])})
    log.info(f"{len(tagged)} entries, {len(all_drugs)} unique drug names.")

    canon_map = {}
    for i in range(0, len(all_drugs), BATCH_SIZE):
        batch = all_drugs[i:i + BATCH_SIZE]
        try:
            canon_map.update(canonicalize_batch(client, batch))
        except LLMParseError as e:
            log.error(f"Batch {i} failed: {e}. Keeping raw names.")
            for name in batch:
                canon_map[name] = name
        log.info(f"Canonicalized {min(i + BATCH_SIZE, len(all_drugs))}/{len(all_drugs)}...")

    # Log synonym groups
    groups: dict[str, list[str]] = {}
    for raw, canonical in canon_map.items():
        if raw != canonical:
            groups.setdefault(canonical, []).append(raw)
    if groups:
        log.info(f"Synonym groups ({len(groups)}):")
        for canonical, synonyms in sorted(groups.items()):
            log.info(f"  {canonical} ← {', '.join(synonyms)}")

    # Rewrite tagged_mentions.json with canonical names
    def canonicalize_list(drugs: list[str]) -> list[str]:
        return list(dict.fromkeys(canon_map.get(d, d) for d in drugs))

    for entry in tagged:
        entry["drugs_direct"] = canonicalize_list(entry.get("drugs_direct", []))
        entry["drugs_context"] = canonicalize_list(entry.get("drugs_context", []))

    tagged_path.write_text(json.dumps(tagged, indent=2))
    log.info(f"Rewrote {tagged_path.name} with canonical names.")

    # Populate treatment table with canonical names + aliases
    # Gather all unique, non-empty drug names from both "drugs_direct" and "drugs_context"
    all_drugs = set()
    for entry in tagged:
        for drug in entry.get("drugs_direct", []) + entry.get("drugs_context", []):
            if drug.strip():
                all_drugs.add(drug)
    aliases_for: dict[str, list[str]] = defaultdict(list)
    for raw, canonical in canon_map.items():
        if raw != canonical:
            aliases_for.setdefault(canonical, []).append(raw)
    count = upsert_treatments(config.db_path, all_drugs, aliases_for)
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
