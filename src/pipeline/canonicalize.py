#!/usr/bin/env python3
"""
canonicalize.py — Normalize drug synonyms.

Step 2 of the pipeline. Merges synonyms (e.g. "low dose naltrexone" → "ldn")
and writes canonicalized_mentions.json with canonical names. The original
tagged_mentions.json is left untouched.
"""
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utilities import PipelineConfig

from patientpunk._utils import LLMResponseError
from utilities import (
    TAGGED_MENTIONS, CANONICALIZED_MENTIONS, MODEL_STRONG, LLMParseError,
    resolve_aliases, llm_call, parse_json_object, log,
)
from utilities.db import upsert_treatments
from prompts.intervention_config import CANONICALIZE_COMPOUND_PROMPT

BATCH_SIZE = 3500
TOKENS_PER_NAME = 15
MIN_OUTPUT_TOKENS = 2000
# Four splits reduce a full batch to about 219 names.
MAX_SPLIT_DEPTH = 4


@dataclass(frozen=True, slots=True)
class CanonicalizationBatchResult:
    mapping: dict[str, str]
    failed_names: int = 0
    split_names: int = 0


def canonicalize_batch(
    client,
    names: list[str],
    model=MODEL_STRONG,
) -> CanonicalizationBatchResult:
    """Canonicalize names, splitting unusable batches up to a fixed depth."""

    if not names:
        return CanonicalizationBatchResult(mapping={})

    def _canonicalize(batch: list[str], depth: int) -> CanonicalizationBatchResult:
        prompt = (
            CANONICALIZE_COMPOUND_PROMPT
            + f"\n\nDrug names to canonicalize:\n{json.dumps(batch)}"
        )
        max_tokens = max(MIN_OUTPUT_TOKENS, len(batch) * TOKENS_PER_NAME)

        try:
            raw = llm_call(client, prompt, model=model, max_tokens=max_tokens)
            mapping = {name: name for name in batch} | parse_json_object(raw)
            return CanonicalizationBatchResult(mapping=mapping)
        except (LLMParseError, LLMResponseError) as exc:
            if len(batch) == 1 or depth >= MAX_SPLIT_DEPTH:
                return CanonicalizationBatchResult(
                    mapping={name: name for name in batch},
                    failed_names=len(batch),
                )

            midpoint = len(batch) // 2
            log.warning(
                "%s; splitting %d names and retrying both halves.",
                exc,
                len(batch),
            )
            left = _canonicalize(batch[:midpoint], depth + 1)
            right = _canonicalize(batch[midpoint:], depth + 1)
            return CanonicalizationBatchResult(
                mapping=left.mapping | right.mapping,
                failed_names=left.failed_names + right.failed_names,
                split_names=len(batch),
            )

    return _canonicalize(names, depth=0)


def _canonicalize_entries(tagged: list[dict], canon_map: dict[str, str]) -> None:
    """In-place: replace drug names with canonical forms, dedup preserving order."""
    for entry in tagged:
        for key in ("drugs_direct", "drugs_context"):
            entry[key] = list(dict.fromkeys(canon_map.get(d, d) for d in entry.get(key, [])))


def run_targeted_canonicalization(config: "PipelineConfig") -> dict[str, str]:
    """Skip the LLM synonym pass; use cached aliases to merge everything into target."""
    target, aliases = resolve_aliases(config)
    canon_map = {a: target for a in aliases}

    tagged = json.loads(config.path(TAGGED_MENTIONS).read_text(encoding="utf-8"))
    _canonicalize_entries(tagged, canon_map)

    filtered = [e for e in tagged if target in e.get("drugs_direct", []) or target in e.get("drugs_context", [])]
    config.path(CANONICALIZED_MENTIONS).write_text(json.dumps(filtered, indent=2))
    upsert_treatments(config.db_path, {target}, {target: [a for a in aliases if a != target]})
    log.info(f"Targeted canonicalize: {target!r} ← {len(aliases)} aliases | kept {len(filtered)}/{len(tagged)} entries")
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
    failed_names = 0
    split_names = 0
    batches = [all_drugs[i:i + BATCH_SIZE] for i in range(0, len(all_drugs), BATCH_SIZE)]
    for i, batch in enumerate(batches, 1):
        log.info(f"batch {i}/{len(batches)} ({len(batch)} names): calling LLM...")
        t0 = time.monotonic()
        result = canonicalize_batch(client, batch)
        merges = sum(raw != canonical for raw, canonical in result.mapping.items())
        log.info(
            f"batch {i}/{len(batches)} done: {merges} merges in "
            f"{time.monotonic() - t0:.1f}s"
        )
        canon_map.update(result.mapping)
        failed_names += result.failed_names
        split_names += result.split_names

    if split_names:
        log.warning(
            "CANONICALIZATION USED SPLIT BATCHES: %d of %d names were processed "
            "in smaller groups. Synonyms across split boundaries may remain "
            "unmerged.",
            split_names,
            len(all_drugs),
        )

    if failed_names:
        log.error(
            "CANONICALIZATION INCOMPLETE: %d of %d names (%.1f%%) were kept raw "
            "after their sub-batches failed. Per-drug counts may be incomplete "
            "until this is re-run.",
            failed_names,
            len(all_drugs),
            failed_names / len(all_drugs) * 100,
        )

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
