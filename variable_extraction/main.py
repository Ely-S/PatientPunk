#!/usr/bin/env python3
"""
PatientPunk -- demographic extraction pipeline entry point.

Subcommands
-----------
run
    Run the full extraction pipeline (or a subset of phases).

demographics
    LLM-only extraction of age, sex/gender, and location.  No regex.
    Outputs a standalone demographics.csv.

inspect
    Inspect a schema file: print field counts, field names, and pattern counts
    without running any extraction.

corpus
    Print corpus statistics (record counts, source breakdown) for a given
    input directory without running any extraction.

export
    Re-run only the export phases (Phase 4: CSV, Phase 5: codebook) from
    existing intermediate files.

Usage examples
--------------
Full pipeline run (LLM extraction, no discovery)::

    python main.py run --schema schemas/covidlonghaulers_schema.json

With field discovery (auto-merge all candidates)::

    python main.py run --schema schemas/covidlonghaulers_schema.json --discover auto

With field discovery (stop for human review)::

    python main.py run --schema schemas/covidlonghaulers_schema.json --discover review

Cheap test run (10 records)::

    python main.py run --schema schemas/covidlonghaulers_schema.json --limit 10

Inspect a schema::

    python main.py inspect --schema schemas/covidlonghaulers_schema.json

Corpus statistics::

    python main.py corpus --input-dir ../data

Re-export CSV and codebook from existing temp files::

    python main.py export --schema schemas/covidlonghaulers_schema.json \\
        --codebook-format markdown
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make sure the package is importable when run from this directory.
sys.path.insert(0, str(Path(__file__).parent))

from patientpunk import Pipeline, PipelineConfig, DemographicCoder, DemographicsExtractor
from patientpunk.corpus import CorpusLoader
from patientpunk.schema import Schema


# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).parent
_DEFAULT_INPUT_DIR = _HERE.parent / "data"
_DEFAULT_SCHEMA_DIR = _HERE / "schemas"


# ---------------------------------------------------------------------------
# Subcommand: run
# ---------------------------------------------------------------------------

def _add_run_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    run_parser = sub.add_parser(
        "run",
        help="Run the full extraction pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Run all (or a subset of) pipeline phases:

  Phase 1  extract_biomedical  Regex extraction (free, seconds)
  Phase 2  llm_extract         LLM extraction   (Claude Haiku)
  Phase 3  discover_fields     Field discovery   (Haiku + Sonnet) -- off by default
  Phase 4  records_to_csv      Flatten to CSV
  Phase 5  make_codebook       Generate data dictionary

Default runs Phases 1-2-4-5. Use --discover auto|review to enable Phase 3.
Use --no-llm to skip Phase 2, or --start-at N to resume from a specific phase.
        """,
    )
    # Required
    run_parser.add_argument("--schema", type=Path, required=True,
                   help="Extension schema JSON (e.g. schemas/covidlonghaulers_schema.json)")

    # Paths
    run_parser.add_argument("--input-dir", type=Path, default=_DEFAULT_INPUT_DIR,
                   help=f"Corpus / output directory (default: {_DEFAULT_INPUT_DIR})")
    run_parser.add_argument("--temp-dir", type=Path, default=None,
                   help="Intermediate file directory (default: {input-dir}/temp/)")

    # Phase control
    run_parser.add_argument("--start-at", type=int, default=1, choices=[1, 2, 3, 4, 5],
                   help="Start from this phase (1-5).  Phases before this are skipped.")
    run_parser.add_argument("--no-llm", action="store_true",
                   help="Skip phase 2 (LLM gap-filling).")
    run_parser.add_argument("--discover", choices=["auto", "review"], default=None,
                   help="Run Phase 3 field discovery. 'auto' runs all stages and "
                        "merges candidates. 'review' stops after candidate generation "
                        "so you can select fields in the Marimo variable picker "
                        "(apps/discover.py). Default: skip discovery entirely.")
    run_parser.add_argument("--no-clean", action="store_true",
                   help="Do not wipe temp/ before starting.  Useful when resuming.")

    # Shared
    run_parser.add_argument("--workers", type=int, default=10,
                   help="Concurrent API workers (default: 10).")
    run_parser.add_argument("--limit", type=int, default=None,
                   help="Process at most N records (cost control / testing).")
    run_parser.add_argument("--resume", action="store_true",
                   help="Resume interrupted LLM / discovery runs.")

    # Phase 2
    run_parser.add_argument("--skip-threshold", type=float, default=0.7,
                   help="Skip LLM for records where regex hit >= this fraction (default: 0.7).")
    run_parser.add_argument("--no-focus-gaps", action="store_true",
                   help="Disable LLM focused-gap mode.")

    # Phase 3
    run_parser.add_argument("--candidates", type=Path, default=None,
                   help="Saved phase1_candidates.json -- skips Stage 1 of discover_fields.")
    run_parser.add_argument("--sample", type=int, default=None,
                   help="Randomly sample N corpus items for discovery Stage 1.")
    run_parser.add_argument("--no-fill", action="store_true",
                   help="Skip discovery Stage 4 gap-filling.")

    # Phase 4
    run_parser.add_argument("--sep", default=" | ",
                   help="Multi-value separator for CSV (default: ' | ').")
    run_parser.add_argument("--provenance", action="store_true",
                   help="Include {field}__provenance and {field}__confidence columns in CSV.")

    # Phase 5
    run_parser.add_argument("--codebook-format", choices=["csv", "markdown"], default="csv",
                   help="Codebook output format (default: csv).")
    run_parser.add_argument("--no-discovered", action="store_true",
                   help="Exclude llm_discovered fields from the codebook.")


def _cmd_run(args: argparse.Namespace) -> None:
    schema_path = args.schema if args.schema.is_absolute() else _HERE / args.schema
    if not schema_path.exists():
        sys.exit(f"Schema not found: {schema_path}")

    config = PipelineConfig(
        schema_path=schema_path,
        input_dir=args.input_dir,
        temp_dir=args.temp_dir,
        start_at=args.start_at,
        run_llm=not args.no_llm,
        discovery_mode=args.discover,
        clean=not args.no_clean,
        workers=args.workers,
        limit=args.limit,
        resume=args.resume,
        llm_skip_threshold=args.skip_threshold,
        llm_focus_gaps=not args.no_focus_gaps,
        candidates_file=args.candidates,
        discovery_sample=args.sample,
        discovery_fill_gaps=not args.no_fill,
        csv_sep=args.sep,
        csv_provenance=args.provenance,
        codebook_format=args.codebook_format,
        codebook_include_discovered=not args.no_discovered,
    )

    result = Pipeline(config).run()
    sys.exit(0 if result.ok else 1)


# ---------------------------------------------------------------------------
# Subcommand: demographics
# ---------------------------------------------------------------------------

def _add_demographics_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    demo_parser = sub.add_parser(
        "demographics",
        help="LLM-only demographic coding (deductive, inductive, or both).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
LLM-only demographic coding using Claude Haiku.

Supports two complementary qualitative coding approaches:

  deductive   Extract predefined fields: age, sex_gender, location_country,
              location_state.  Top-down -- apply the codebook to the data.

  inductive   Discover NEW demographic categories from the data: occupation,
              ethnicity, disability status, insurance type, education level,
              etc.  Bottom-up -- let themes emerge.

  both        Do deductive + inductive in a single LLM pass (default).

Works across both corpus sources:
  subreddit_posts.json   -- one record per post
  users/*.json           -- full posting history per user (recommended)

Outputs (depending on mode):
  demographics_deductive.csv   -- predefined fields
  demographics_inductive.json  -- per-record discovered categories
  demographics_codebook.json   -- aggregated category frequencies
        """,
    )
    demo_parser.add_argument(
        "--input-dir", type=Path,
        default=_DEFAULT_INPUT_DIR,
        help=f"Directory containing subreddit_posts.json and/or users/ (default: {_DEFAULT_INPUT_DIR})",
    )
    demo_parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="Output directory (default: same as --input-dir)",
    )
    demo_parser.add_argument(
        "--mode", choices=["deductive", "inductive", "both"], default="both",
        help="Coding mode (default: both).",
    )
    demo_parser.add_argument(
        "--workers", type=int, default=10,
        help="Concurrent Haiku API requests (default: 10).",
    )
    source_group = demo_parser.add_mutually_exclusive_group()
    source_group.add_argument(
        "--posts-only", action="store_true",
        help="Only process subreddit_posts.json, skip users/.",
    )
    source_group.add_argument(
        "--users-only", action="store_true",
        help="Only process users/*.json histories, skip subreddit_posts.json.",
    )
    demo_parser.add_argument(
        "--max-chars", type=int, default=8000,
        help="Max characters of text sent per record to the LLM (default: 8000).",
    )


def _cmd_demographics(args: argparse.Namespace) -> None:
    coder = DemographicCoder(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        mode=args.mode,
        workers=args.workers,
        include_posts=not args.users_only,
        include_users=not args.posts_only,
        max_chars=args.max_chars,
    )
    result = coder.run(raise_on_error=False)
    sys.exit(result.returncode)


# ---------------------------------------------------------------------------
# Subcommand: inspect
# ---------------------------------------------------------------------------

def _add_inspect_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    inspect_parser = sub.add_parser(
        "inspect",
        help="Inspect a schema file.",
        description="Print field metadata for a schema without running extraction.",
    )
    inspect_parser.add_argument("--schema", type=Path, required=True,
                   help="Extension schema JSON to inspect.")
    inspect_parser.add_argument("--base-schema", type=Path, default=None,
                   help="Base schema JSON (auto-detected if omitted).")
    inspect_parser.add_argument("--source", default=None,
                   choices=["base", "base_optional", "extension", "llm_discovered"],
                   help="Filter fields by source.")
    inspect_parser.add_argument("--verbose", "-v", action="store_true",
                   help="Print patterns for each field.")


def _cmd_inspect(args: argparse.Namespace) -> None:
    schema_path = args.schema if args.schema.is_absolute() else _HERE / args.schema
    if not schema_path.exists():
        sys.exit(f"Schema not found: {schema_path}")

    kwargs: dict = {}
    if args.base_schema:
        kwargs["base_path"] = args.base_schema

    schema = Schema.from_file(schema_path, **kwargs)

    print(f"\nSchema: {schema.schema_id}")
    if schema.target_subreddit:
        print(f"Target subreddit: {schema.target_subreddit}")
    print(f"Base fields      : {len(schema.base_fields)}")
    print(f"Extension fields : {len(schema.extension_fields)}")
    print(f"Total fields     : {len(schema.all_fields)}")

    field_names = schema.field_names(source=args.source)
    src_label = f" (source={args.source!r})" if args.source else ""
    print(f"\nFields{src_label}:\n")

    for name in field_names:
        field_def = schema.all_fields[name]
        icd_label = f"  ICD-10: {field_def.icd10}" if field_def.icd10 else ""
        print(f"  {name:<40} [{field_def.confidence:<6}] [{field_def.source}]{icd_label}")
        if args.verbose and field_def.patterns:
            for pattern in field_def.patterns:
                print(f"    pattern: {pattern}")

    print()


# ---------------------------------------------------------------------------
# Subcommand: corpus
# ---------------------------------------------------------------------------

def _add_corpus_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    corpus_parser = sub.add_parser(
        "corpus",
        help="Print corpus statistics.",
        description="Show record counts and source breakdown for an input directory.",
    )
    corpus_parser.add_argument("--input-dir", type=Path, default=_DEFAULT_INPUT_DIR,
                   help=f"Corpus directory (default: {_DEFAULT_INPUT_DIR})")


def _cmd_corpus(args: argparse.Namespace) -> None:
    loader = CorpusLoader(args.input_dir)
    print(f"\nCorpus: {args.input_dir}")
    print(f"  Subreddit posts : {loader.post_count}")
    print(f"  User histories  : {loader.user_count}")
    print(f"  Total records   : {loader.record_count}")
    print()


# ---------------------------------------------------------------------------
# Subcommand: export
# ---------------------------------------------------------------------------

def _add_export_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    export_parser = sub.add_parser(
        "export",
        help="Re-run export phases only (Phase 4 + 5).",
        description="Flatten existing intermediate JSON records to CSV and regenerate the codebook.",
    )
    export_parser.add_argument("--schema", type=Path, required=True,
                   help="Extension schema JSON.")
    export_parser.add_argument("--input-dir", type=Path, default=_DEFAULT_INPUT_DIR,
                   help=f"Directory containing temp/ and where outputs are written (default: {_DEFAULT_INPUT_DIR})")
    export_parser.add_argument("--temp-dir", type=Path, default=None,
                   help="Intermediate file directory (default: {input-dir}/temp/).")
    export_parser.add_argument("--sep", default=" | ",
                   help="Multi-value separator for CSV (default: ' | ').")
    export_parser.add_argument("--provenance", action="store_true",
                   help="Include provenance / confidence columns in CSV.")
    export_parser.add_argument("--codebook-format", choices=["csv", "markdown"], default="csv",
                   help="Codebook output format (default: csv).")
    export_parser.add_argument("--no-discovered", action="store_true",
                   help="Exclude llm_discovered fields from the codebook.")


def _cmd_export(args: argparse.Namespace) -> None:
    schema_path = args.schema if args.schema.is_absolute() else _HERE / args.schema
    if not schema_path.exists():
        sys.exit(f"Schema not found: {schema_path}")

    config = PipelineConfig(
        schema_path=schema_path,
        input_dir=args.input_dir,
        temp_dir=args.temp_dir,
        start_at=4,             # skip phases 1-3
        run_llm=False,
        discovery_mode=None,
        clean=False,
        csv_sep=args.sep,
        csv_provenance=args.provenance,
        codebook_format=args.codebook_format,
        codebook_include_discovered=not args.no_discovered,
    )

    result = Pipeline(config).run()
    sys.exit(0 if result.ok else 1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="patientpunk",
        description="PatientPunk biomedical extraction pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py run          --schema schemas/covidlonghaulers_schema.json
  python main.py run          --schema schemas/covidlonghaulers_schema.json --limit 10
  python main.py demographics --input-dir ../reddit_sample_data
  python main.py demographics --input-dir ../reddit_sample_data --users-only
  python main.py inspect      --schema schemas/covidlonghaulers_schema.json
  python main.py corpus       --input-dir ../data
  python main.py export       --schema schemas/covidlonghaulers_schema.json --codebook-format markdown
        """,
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    _add_run_parser(sub)
    _add_demographics_parser(sub)
    _add_inspect_parser(sub)
    _add_corpus_parser(sub)
    _add_export_parser(sub)

    args = parser.parse_args()

    dispatch = {
        "run":          _cmd_run,
        "demographics": _cmd_demographics,
        "inspect":      _cmd_inspect,
        "corpus":       _cmd_corpus,
        "export":       _cmd_export,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
