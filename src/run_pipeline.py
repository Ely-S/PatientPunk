#!/usr/bin/env python3
"""
run_pipeline.py — Run the full drug mention database pipeline.

Steps:
  1. extract      — Extract drug mentions from posts → tagged_mentions.json
  2. canonicalize — Normalize synonyms, populate treatment table (with aliases)
  3. classify     — Classify sentiment for each entry×drug → treatment_reports table

Usage:
    python src/run_pipeline.py --db data/posts.db --output-dir outputs
    python src/run_pipeline.py --db data/posts.db --output-dir outputs --skip-canonicalize
    python src/run_pipeline.py --db data/posts.db --output-dir outputs --limit 50
"""
import argparse
import subprocess
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from utilities.db import ReportWriter, upsert_treatments
from utilities import PipelineConfig, TAGGED_MENTIONS, get_client, log, MODEL_FAST, MODEL_STRONG
from pipeline.extract import run_extraction
from pipeline.canonicalize import run_canonicalization
from pipeline.classify import run_classification


def get_git_commit() -> str:
    """Get current git commit hash, or 'unknown' if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _banner(label: str) -> None:
    log.info(f"\n{'═' * 60}")
    log.info(f"  STEP: {label}")
    log.info(f"{'═' * 60}\n")


def run_pipeline(config: PipelineConfig, *, skip_canonicalize: bool = False) -> None:
    """Run the full pipeline programmatically given a PipelineConfig."""
    import json

    _banner("EXTRACT")
    run_extraction(config)

    if not skip_canonicalize:
        _banner("CANONICALIZE")
        run_canonicalization(config)
    else:
        tagged = json.loads(config.path(TAGGED_MENTIONS).read_text())
        all_drugs = {d for e in tagged for d in e.get("drugs_direct", []) + e.get("drugs_context", []) if d.strip()}
        count = upsert_treatments(config.db_path, all_drugs)
        log.info(f"{count} treatments in database (no aliases).")

    run_config = {
        "models": {"fast": MODEL_FAST, "strong": MODEL_STRONG},
        "limit": config.limit,
        "reclassify": config.reclassify,
        "skip_canonicalize": skip_canonicalize,
        "output_dir": str(config.output_dir),
    }

    _banner("CLASSIFY")
    with ReportWriter(config.db_path, run_config=run_config, commit_hash=get_git_commit()) as writer:
        log.info(f"Extraction run {writer.run_id}")
        run_classification(config, writer=writer)

    log.info(f"\n{'═' * 60}")
    log.info("  PIPELINE COMPLETE")
    log.info(f"{'═' * 60}\n")


def main():
    parser = argparse.ArgumentParser(description="Run drug mention database pipeline")
    parser.add_argument("--db", required=True, help="Path to SQLite database (must have posts imported)")
    parser.add_argument("--output-dir", required=True, help="Directory for output files")
    parser.add_argument("--limit", type=int, default=0, help="Limit posts processed")
    parser.add_argument("--reclassify", action="store_true", help="Re-run classification for all pairs, even those already in the database")
    parser.add_argument("--skip-canonicalize", action="store_true", help="Skip canonicalization step")
    parser.add_argument("--max-ancestor-chars", type=int, default=0, help="Truncate ancestor text to N chars (0 = unlimited)")
    parser.add_argument("--max-ancestor-depth", type=int, default=0, help="Max ancestor hops for drug context (0 = unlimited)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    config = PipelineConfig(
        client=get_client(),
        output_dir=output_dir,
        db_path=Path(args.db),
        limit=args.limit,
        reclassify=args.reclassify,
        max_ancestor_chars=args.max_ancestor_chars,
        max_ancestor_depth=args.max_ancestor_depth,
    )

    run_pipeline(config, skip_canonicalize=args.skip_canonicalize)


if __name__ == "__main__":
    main()
