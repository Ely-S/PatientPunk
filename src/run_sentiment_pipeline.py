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
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from utilities.db import ReportWriter, upsert_treatments
from utilities import PipelineConfig, TAGGED_MENTIONS, CANONICALIZED_MENTIONS, get_client, get_git_commit, log, MODEL_FAST, MODEL_STRONG, LLM_TEMPERATURE
from pipeline.extract import run_extraction
from pipeline.canonicalize import run_canonicalization
from pipeline.classify import run_classification



def _snapshot_run_artifacts(config: PipelineConfig, run_id: int) -> tuple[Path, list[str]]:
    """Copy this run's inputs and decisions into ``runs/run_<run_id>/``.

    The working files keep their fixed names on purpose: the pipeline reads them back to resume
    without re-paying for extraction or the prefilter. But that also means every run overwrites
    the previous one's record, and the DB is no substitute — it holds only what survived the
    writer gate. Once prefilter_results.json is overwritten there is nothing left saying which
    pairs were dropped before classify ever saw them, and a second model cannot re-check work it
    cannot see. So snapshot rather than rename: resume still works, and each run keeps its own
    copy. run_id is the extraction_runs primary key, so a snapshot joins straight back to the row.
    """
    dest = config.path("runs") / f"run_{run_id}"
    dest.mkdir(parents=True, exist_ok=True)
    kept: list[str] = []
    for name in (TAGGED_MENTIONS, CANONICALIZED_MENTIONS, "prefilter_results.json"):
        source = config.path(name)
        if source.exists():
            shutil.copy2(source, dest / name)
            kept.append(name)
    for alias_file in sorted(config.output_dir.glob("aliases_*.json")):
        shutil.copy2(alias_file, dest / alias_file.name)
        kept.append(alias_file.name)
    return dest, kept


def _banner(label: str) -> None:
    log.info(f"\n{'═' * 60}")
    log.info(f"  STEP: {label}")
    log.info(f"{'═' * 60}\n")


def run_pipeline(config: PipelineConfig, *, skip_extract: bool = False, skip_canonicalize: bool = False, skip_prefilter: bool = False) -> None:
    """Run the full pipeline programmatically given a PipelineConfig."""

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
        # These three decide what the model actually SAW, so a run that omits them cannot be
        # re-coded by a second model without silently changing the input: depth sets how many
        # parent hops of context were included, chars where that context was truncated, and
        # temperature whether the reply was the argmax. Without them a later disagreement
        # between models is indistinguishable from a difference in what they were each shown.
        # Unrecoverable after the fact, which is why they are recorded rather than inferred.
        "max_upstream_depth": config.max_upstream_depth,
        "max_upstream_chars": config.max_upstream_chars,
        "temperature": LLM_TEMPERATURE,
    }

    _banner("CLASSIFY")
    # Capture every classification BEFORE the writer gate. The DB only ever sees what survives the
    # gate, so without this sidecar the parse-failure rate is invisible and indistinguishable from
    # a genuine neutral — any analysis reading the DB alone measures the gate, not the model.
    classify_audit: list[dict] = []
    with ReportWriter(config.db_path, run_config=run_config, commit_hash=get_git_commit()) as writer:
        log.info(f"Extraction run {writer.run_id}")
        run_classification(config, writer=writer, skip_prefilter=skip_prefilter,
                           audit_sink=classify_audit)
        run_id = writer.run_id

    run_dir, snapshotted = _snapshot_run_artifacts(config, run_id)
    if classify_audit:
        audit_path = run_dir / "classify_audit.jsonl"
        with audit_path.open("w", encoding="utf-8") as fh:
            for record in classify_audit:
                fh.write(json.dumps({"run_id": run_id, **record}) + "\n")
        statuses = Counter(r["status"] for r in classify_audit)
        log.info(f"Wrote {audit_path} ({len(classify_audit)} classifications: "
                 + ", ".join(f"{n} {s}" for s, n in statuses.most_common()) + ")")
    log.info(f"Run {run_id} artifacts snapshotted to {run_dir} "
             f"({', '.join(snapshotted) if snapshotted else 'nothing to copy'}).")

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
        "--workers", type=int, default=20,
        help="Parallel workers for extract/classify (default: 20, use 1 for sequential). "
             "Higher values may hit provider rate limits; "
             "drop to 3-4 if you see 30s+ stalls between log lines.",
    )
    args = parser.parse_args()

    # --drug-file: a hand-curated alias list, first non-blank line is the
    # canonical target. Validate aggressively so an empty / unreadable file
    # doesn't silently disable targeting and fall back to a full-corpus run.
    drug = args.drug
    drug_aliases = None
    if args.drug_file:
        drug_file_path = Path(args.drug_file)
        try:
            raw_lines = drug_file_path.read_text(encoding="utf-8").splitlines()
        except OSError as e:
            parser.error(f"cannot read --drug-file {drug_file_path}: {e}")
        # Strip whitespace, drop blank lines, de-dup while preserving order.
        seen: set[str] = set()
        drug_aliases = []
        for line in raw_lines:
            s = line.strip()
            if s and s not in seen:
                seen.add(s)
                drug_aliases.append(s)
        if not drug_aliases:
            parser.error(
                f"--drug-file {drug_file_path} contains no non-blank lines; "
                "it must contain at least the canonical drug name on the first line."
            )
        drug = drug_aliases[0]

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
