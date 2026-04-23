#!/usr/bin/env python3
"""
run_sentiment_pipeline.py — Run the full drug sentiment database pipeline.

Steps:
  1. extract      — Extract drug mentions from posts → tagged_mentions.json
  2. canonicalize — Normalize synonyms, populate treatment table (with aliases)
  3. classify     — Classify sentiment for each entry×drug → treatment_reports table

Usage:
    python src/run_sentiment_pipeline.py --db data/posts.db --output-dir outputs
    python src/run_sentiment_pipeline.py --db data/posts.db --output-dir outputs --skip-canonicalize
    python src/run_sentiment_pipeline.py --db data/posts.db --output-dir outputs --limit 50
"""
import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from utilities.db import ReportWriter, upsert_treatments
from utilities import PipelineConfig, TAGGED_MENTIONS, get_client, get_git_commit, log, MODEL_FAST, MODEL_STRONG
from pipeline.extract import run_extraction
from pipeline.canonicalize import run_canonicalization
from pipeline.classify import run_classification



def _banner(label: str) -> None:
    log.info(f"\n{'═' * 60}")
    log.info(f"  STEP: {label}")
    log.info(f"{'═' * 60}\n")


def run_pipeline(config: PipelineConfig, *, skip_extract: bool = False, skip_canonicalize: bool = False, skip_prefilter: bool = False) -> None:
    """Run the full pipeline programmatically given a PipelineConfig."""
    import json

    if not skip_extract:
        _banner("EXTRACT")
        run_extraction(config)
    else:
        log.info("Skipping extraction (using existing tagged_mentions.json)")

    if not skip_canonicalize:
        _banner("CANONICALIZE")
        run_canonicalization(config)
    else:
        tagged = json.loads(config.path(TAGGED_MENTIONS).read_text(encoding="utf-8"))
        all_drugs = {d for e in tagged for d in e.get("drugs_direct", []) + e.get("drugs_context", []) if d.strip()}
        count = upsert_treatments(config.db_path, all_drugs)
        log.info(f"{count} treatments in database (no aliases).")

    run_config = {
        "models": {"fast": MODEL_FAST, "strong": MODEL_STRONG},
        "limit": config.limit,
        "reclassify": config.reclassify,
        "skip_canonicalize": skip_canonicalize,
        "output_dir": str(config.output_dir),
        "drug": config.drug,
    }

    _banner("CLASSIFY")
    with ReportWriter(config.db_path, run_config=run_config, commit_hash=get_git_commit()) as writer:
        log.info(f"Extraction run {writer.run_id}")
        run_classification(config, writer=writer, skip_prefilter=skip_prefilter)

    log.info(f"\n{'═' * 60}")
    log.info("  PIPELINE COMPLETE")
    log.info(f"{'═' * 60}\n")


def main():
    parser = argparse.ArgumentParser(description="Run drug mention database pipeline")
    parser.add_argument("--db", required=True, help="Path to SQLite database (must have posts imported)")
    parser.add_argument("--output-dir", required=True, help="Directory for output files")
    parser.add_argument("--limit", type=int, default=0, help="Limit posts processed")
    parser.add_argument("--reclassify", action="store_true", help="Re-run classification for all pairs, even those already in the database")
    parser.add_argument("--skip-extract", action="store_true", help="Skip extraction step (use existing tagged_mentions.json)")
    parser.add_argument("--skip-canonicalize", action="store_true", help="Skip canonicalization step")
    parser.add_argument("--skip-prefilter", action="store_true", help="Skip the fast-model prefilter; send all pairs to the strong model")
    parser.add_argument("--max-upstream-chars", type=int, default=None, help="Truncate upstream comment text to N chars (default: unlimited)")
    parser.add_argument("--max-upstream-depth", type=int, default=None, help="Max upstream hops for drug context (default: unlimited)")
    drug_group = parser.add_mutually_exclusive_group()
    drug_group.add_argument("--drug", type=str, default=None, help="Restrict canonicalize + classify to a single target drug and its synonyms. Extract still runs on full corpus.")
    drug_group.add_argument("--drug-file", type=str, default=None, help="Text file of drug + aliases, one per line, first line canonical. Skips the LLM alias lookup.")
    parser.add_argument(
        "--workers", type=int, default=3,
        help="Parallel workers for extract/classify (default: 3, use 1 for sequential). "
             "Higher values may hit provider rate limits; "
             "drop to 3-4 if you see 30s+ stalls between log lines.",
    )
    args = parser.parse_args()

    drug_aliases = [l.strip() for l in Path(args.drug_file).read_text().splitlines() if l.strip()] if args.drug_file else None
    drug = drug_aliases[0] if drug_aliases else args.drug

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    config = PipelineConfig(
        client=get_client(),
        output_dir=output_dir,
        db_path=Path(args.db),
        limit=args.limit,
        reclassify=args.reclassify,
        max_upstream_chars=args.max_upstream_chars,
        max_upstream_depth=args.max_upstream_depth,
        workers=args.workers,
        drug=drug,
        drug_aliases=drug_aliases,
    )

    run_pipeline(config, skip_extract=args.skip_extract, skip_canonicalize=args.skip_canonicalize, skip_prefilter=args.skip_prefilter)


if __name__ == "__main__":
    main()
