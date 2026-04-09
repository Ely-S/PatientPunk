#!/usr/bin/env python3
"""
canonicalize.py — Normalize drug synonyms.

Step 2 of the pipeline. Merges synonyms (e.g. "low dose naltrexone" → "ldn")
and rewrites tagged_mentions.json with canonical names.

The output file is canonical_map.json
    {
        "id": "t3_1scqprg",
        "author": "u_1234567890",
        "text": "I took 100mg of LSD last night and it was amazing!",
        "post_title": "I took 100mg of LSD last night and it was amazing!",
        "parent_id": None,
        "created_utc": 1717334400,
        "drugs_direct": ["lsd"],
        "drugs_context": ["psychedelic"]
    }
Usage:
    python src/run_pipeline.py --db data/posts.db --output-dir outputs
    # Or standalone (run from src/):
    python -m scripts.canonicalize --output-dir ../outputs
"""
import json
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utilities import PipelineConfig

from utilities import (
    OutputFiles, MODEL_FAST, llm_call, parse_json_object, 
    process_in_batches, log
)
from prompts.intervention_config import CANONICALIZE_COMPOUND_PROMPT

BATCH_SIZE = 50


def canonicalize_batch(client, names: list[str], model=MODEL_FAST) -> dict[str, str]:
    """Ask Haiku to group synonyms among a list of drug names."""
    msg = CANONICALIZE_COMPOUND_PROMPT + f"\n\nDrug names to canonicalize:\n{json.dumps(names)}"
    raw = llm_call(client, msg, model=model, max_tokens=len(names) * 30)
    result = parse_json_object(raw)
    # Ensure every input name is mapped
    for name in names:
        if name not in result:
            result[name] = name
    return result


def run_canonicalization(config: "PipelineConfig") -> dict[str, str]:
    """Main canonicalization logic — called by pipeline or standalone.

    Returns the canonical map: {raw_name: canonical_name}.
    """
    client = config.client
    tagged_path = config.path(OutputFiles.TAGGED_MENTIONS)
    canon_path = config.path(OutputFiles.CANONICAL_MAP)

    tagged = json.loads(tagged_path.read_text())
    log.info(f"Loaded {len(tagged)} tagged entries.")

    # Collect all unique drug names
    all_drugs = {d for e in tagged for d in e.get("drugs_direct", []) + e.get("drugs_context", [])}
    log.info(f"Found {len(all_drugs)} unique drug names.")

    all_drugs_sorted = sorted(all_drugs)

    # Process in batches, collecting partial maps
    canon_map = {}
    for i in range(0, len(all_drugs_sorted), BATCH_SIZE):
        batch = all_drugs_sorted[i:i + BATCH_SIZE]
        try:
            canon_map.update(canonicalize_batch(client, batch))
        except Exception as e:
            log.error(f"Haiku error on batch {i}: {e}. Continuing with fallback...")
            for name in batch:
                canon_map[name] = name
        log.info(f"Canonicalized {min(i + BATCH_SIZE, len(all_drugs_sorted))}/{len(all_drugs_sorted)}...")

    # Save canonical map
    canon_path.write_text(json.dumps(canon_map, indent=2, sort_keys=True))
    log.info(f"Wrote {canon_path.name}")

    # Print summary
    groups = defaultdict(list)
    for raw, canonical in canon_map.items():
        if raw != canonical:
            groups[canonical].append(raw)
    if groups:
        log.info(f"Synonym groups found ({len(groups)}):")
        for canonical, synonyms in sorted(groups.items()):
            log.info(f"  {canonical} ← {', '.join(synonyms)}")

    # Rewrite tagged_mentions.json
    def canonicalize_list(drugs: list[str]) -> list[str]:
        return list(dict.fromkeys(canon_map.get(d, d) for d in drugs))

    for entry in tagged:
        entry["drugs_direct"] = canonicalize_list(entry.get("drugs_direct", []))
        entry["drugs_context"] = canonicalize_list(entry.get("drugs_context", []))

    tagged_path.write_text(json.dumps(tagged, indent=2))
    log.info(f"Rewrote {tagged_path.name} with canonical drug names.")

    return canon_map


def main():
    """Standalone entry point."""
    import argparse
    from utilities import PipelineConfig, get_client

    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, help="Directory containing tagged_mentions.json")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    config = PipelineConfig(
        client=get_client(),
        output_dir=output_dir,
        db_path=Path("."),  # Not used by canonicalize
    )
    run_canonicalization(config)


if __name__ == "__main__":
    main()
