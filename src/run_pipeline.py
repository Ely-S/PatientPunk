#!/usr/bin/env python3
"""
run_pipeline.py — Run the full drug mention database pipeline.

Steps:
  1. extract   — Extract drug mentions from posts → tagged_mentions.json
  2. canonicalize — Normalize synonyms for drug names → canonical_map.json, update tagged_mentions.json
  3. classify  — Classify sentiment for each entry×drug → sentiment_cache.json

Usage:
    python src/run_pipeline.py --posts-file data/posts.json --output-dir outputs --output-db data/posts.db
    python src/run_pipeline.py --posts-file data/posts.json --output-dir outputs --output-db data/posts.db --skip-canonicalize
    python src/run_pipeline.py --posts-file data/posts.json --output-dir outputs --output-db data/posts.db --limit 50
"""
import argparse
import json
import random
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from utilities import PipelineConfig, get_client, log, MODEL_FAST, MODEL_STRONG
from scripts.extract_mentions import run_extraction
from scripts.canonicalize import run_canonicalization
from scripts.classify_sentiment import run_classification


def get_git_commit() -> str:
    """Get current git commit hash, or 'unknown' if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


SENTIMENT_SCORES = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
SIGNAL_SCORES = {"strong": 1.0, "moderate": 0.66, "weak": 0.33}


def log_extraction_run(db_path: Path, config: PipelineConfig, skip_canonicalize: bool) -> int:
    """Log this pipeline run to the database. Returns the run_id."""
    run_id = random.randint(1, 2**31 - 1)
    run_config = {
        "models": {"fast": MODEL_FAST, "strong": MODEL_STRONG},
        "limit": config.limit,
        "regenerate_cache": config.regenerate_cache,
        "skip_canonicalize": skip_canonicalize,
        "posts_file": str(config.posts_file),
        "output_dir": str(config.output_dir),
    }

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO extraction_runs (run_id, run_at, commit_hash, extraction_type, config) "
            "VALUES (?, ?, ?, ?, ?)",
            (run_id, int(time.time()), get_git_commit(), "treatment_sentiment", json.dumps(run_config)),
        )
    log.info(f"Logged run {run_id} to {db_path}")
    return run_id


def import_treatment_reports(db_path: Path, sentiment_cache: dict, run_id: int) -> int:
    """Import sentiment results into treatment_reports table. Returns count inserted."""
    if not sentiment_cache:
        log.warning("No sentiment data to import")
        return 0

    with sqlite3.connect(db_path) as conn:
        # Build drug_name -> drug_id lookup
        drug_ids = {row[0].lower(): row[1] for row in conn.execute("SELECT canonical_name, id FROM treatment")}

        rows = []
        for key, entry in sentiment_cache.items():
            post_id, drug_name = key.rsplit(":", 1)
            drug_id = drug_ids.get(drug_name.lower())
            if not drug_id:
                log.warning(f"Drug not found in treatment table: {drug_name}")
                continue

            rows.append((
                run_id,
                post_id,
                entry.get("author"),
                drug_id,
                SENTIMENT_SCORES.get(entry.get("sentiment"), 0.0),
                SIGNAL_SCORES.get(entry.get("signal"), 0.5),
                json.dumps({"sentiment": entry.get("sentiment"), "signal": entry.get("signal")}),
            ))

        conn.executemany(
            "INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength, sentiment_raw) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

    log.info(f"Imported {len(rows)} treatment reports")
    return len(rows)

STEPS = [
    ("extract", run_extraction),
    ("canonicalize", run_canonicalization),
    ("classify", run_classification),
]


def main():
    parser = argparse.ArgumentParser(description="Run drug mention database pipeline")
    parser.add_argument("--posts-file", required=True, help="Path to subreddit_posts.json")
    parser.add_argument("--output-dir", required=True, help="Directory for output files")
    parser.add_argument("--output-db", required=True, help="Path to SQLite database for logging runs")
    parser.add_argument("--limit", type=int, default=100, help="Limit posts processed")
    parser.add_argument("--regenerate-cache", action="store_true", help="Ignore existing caches")
    parser.add_argument("--skip-canonicalize", action="store_true", help="Skip canonicalization step")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    config = PipelineConfig(
        client=get_client(),
        output_dir=output_dir,
        posts_file=Path(args.posts_file),
        limit=args.limit,
        regenerate_cache=args.regenerate_cache,
    )

    sentiment_cache = {}
    for step_name, step_fn in STEPS:
        if step_name == "canonicalize" and args.skip_canonicalize:
            continue
        log.info(f"\n{'═' * 60}")
        log.info(f"  STEP: {step_name.upper()}")
        log.info(f"{'═' * 60}\n")
        result = step_fn(config)
        if step_name == "classify":
            sentiment_cache = result

    # Log the run and import results to database
    db_path = Path(args.output_db)
    run_id = log_extraction_run(db_path, config, args.skip_canonicalize)
    import_treatment_reports(db_path, sentiment_cache, run_id)

    log.info(f"\n{'═' * 60}")
    log.info("  PIPELINE COMPLETE")
    log.info(f"{'═' * 60}\n")


if __name__ == "__main__":
    main()
