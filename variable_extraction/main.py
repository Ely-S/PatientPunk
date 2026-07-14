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

    python main.py corpus --input-dir ../output

Re-export CSV and codebook from existing temp files::

    python main.py export --schema schemas/covidlonghaulers_schema.json \\
        --codebook-format markdown
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make sure the package is importable when run from this directory.
sys.path.insert(0, str(Path(__file__).parent))

from patientpunk import Pipeline, PipelineConfig, run_demographic_coding
from patientpunk.corpus import CorpusLoader
from patientpunk.schema import Schema
from patientpunk._utils import get_schema_id, load_json
from patientpunk.promote import (
    find_latest_discovery,
    promote_discovered_fields,
    resolve_discovered_schema,
)
from patientpunk.consolidate import consolidate_schemas
from patientpunk.evaluate import export_gold_template, load_records, score_extraction
from patientpunk.cluster_prep import (
    aggregate_patients,
    build_matrix,
    read_records,
    readiness_report,
    select_fields,
    write_matrix,
)
from patientpunk.aggregate import aggregate_corpus_by_author, read_posts, write_corpus
from patientpunk.normalize import (
    DROP_FIELDS,
    TREATMENT_OUTCOME_DERIVED,
    cardinality_report,
    normalize_records,
)


# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).parent
_DEFAULT_INPUT_DIR = _HERE.parent / "output"
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
    try:
        run_demographic_coding(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            mode=args.mode,
            workers=args.workers,
            include_posts=not args.users_only,
            include_users=not args.posts_only,
            max_chars=args.max_chars,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


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
# Subcommand: promote
# ---------------------------------------------------------------------------

def _add_promote_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    promote_parser = sub.add_parser(
        "promote",
        help="Merge discovered fields into a curated schema.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Promote auto-discovered fields (from a prior `run --discover auto`) into a
schema's extension_fields, so future runs extract AND LLM-fill them as
first-class variables on any data.

By default, finds the newest discovery report in temp/ whose base_schema matches
--schema and writes the merged schema to a NEW file
(schemas/{name}_promoted.json) -- the curated schema is never overwritten unless
--in-place.

Workflow:
  python main.py run     --schema schemas/foo.json --discover auto    # discover
  python main.py promote --schema schemas/foo.json --min-coverage 0.1 # promote
  python main.py run     --schema schemas/foo_promoted.json           # fill any data
        """,
    )
    promote_parser.add_argument("--schema", type=Path, required=True,
                   help="Curated extension schema to merge discoveries into.")
    promote_parser.add_argument("--input-dir", type=Path, default=_DEFAULT_INPUT_DIR,
                   help=f"Corpus / output directory (default: {_DEFAULT_INPUT_DIR})")
    promote_parser.add_argument("--temp-dir", type=Path, default=None,
                   help="Intermediate file directory (default: {input-dir}/temp/).")
    promote_parser.add_argument("--discovered-schema", type=Path, default=None,
                   help="Explicit discovered-schema JSON (skips temp/ report lookup).")
    promote_parser.add_argument("--min-coverage", type=float, default=None,
                   help="Only promote fields with discovery coverage >= this (0-1).")
    promote_parser.add_argument("--fields", default=None,
                   help="Comma-separated allowlist of field names to promote.")
    promote_parser.add_argument("--exclude", default=None,
                   help="Comma-separated field names to skip.")
    out_group = promote_parser.add_mutually_exclusive_group()
    out_group.add_argument("--output", type=Path, default=None,
                   help="Output schema path (default: schemas/{name}_promoted.json).")
    out_group.add_argument("--in-place", action="store_true",
                   help="Overwrite the --schema file in place.")
    promote_parser.add_argument("--overwrite-existing", action="store_true",
                   help="Overwrite fields already present in the target schema.")
    promote_parser.add_argument("--dry-run", action="store_true",
                   help="Report what would be promoted without writing.")


def _cmd_promote(args: argparse.Namespace) -> None:
    schema_path = args.schema if args.schema.is_absolute() else _HERE / args.schema
    if not schema_path.exists():
        sys.exit(f"Schema not found: {schema_path}")

    temp_dir = args.temp_dir or (args.input_dir / "temp")
    schema_id = get_schema_id(schema_path)

    field_stats: dict | None = None
    if args.discovered_schema:
        disc_path = (args.discovered_schema if args.discovered_schema.is_absolute()
                     else _HERE / args.discovered_schema)
        if not disc_path.exists():
            sys.exit(f"Discovered schema not found: {disc_path}")
        latest = find_latest_discovery(temp_dir, schema_id)
        if latest:                       # use matching report for coverage stats
            field_stats = latest[1].get("field_stats")
    else:
        latest = find_latest_discovery(temp_dir, schema_id)
        if not latest:
            sys.exit(
                f"No discovery report found in {temp_dir} for schema_id '{schema_id}'.\n"
                f"  Run discovery first: python main.py run --schema {args.schema} --discover auto"
            )
        report_path, report = latest
        disc_path = resolve_discovered_schema(report, temp_dir)
        if not disc_path:
            found = report.get("discovery_results", {}).get("candidates_found", "?")
            sys.exit(
                f"Discovery report {report_path.name} has no promotable schema "
                f"({found} candidate(s) found, none validated) -- nothing to promote."
            )
        field_stats = report.get("field_stats")

    discovered_schema = load_json(disc_path)
    if not isinstance(discovered_schema, dict):
        sys.exit(f"Discovered schema is not valid JSON: {disc_path}")

    if args.in_place:
        output_path = schema_path
    elif args.output:
        output_path = args.output if args.output.is_absolute() else _HERE / args.output
    else:
        output_path = schema_path.with_name(f"{schema_path.stem}_promoted.json")

    include = {f.strip() for f in args.fields.split(",") if f.strip()} if args.fields else None
    exclude = {f.strip() for f in args.exclude.split(",") if f.strip()} if args.exclude else None

    result = promote_discovered_fields(
        schema_path,
        discovered_schema,
        field_stats=field_stats,
        min_coverage=args.min_coverage,
        include=include,
        exclude=exclude,
        overwrite_existing=args.overwrite_existing,
        output_path=output_path,
        dry_run=args.dry_run,
    )

    print(f"\nDiscovered schema: {disc_path.name}")
    print(f"Target schema:     {schema_path.name}")
    print(f"\n{result.summary()}")
    if result.added:
        print(f"\n  Promoted fields ({len(result.added)}):")
        for name in result.added:
            cov = ""
            if field_stats and isinstance(field_stats.get(name), dict):
                c = field_stats[name].get("coverage")
                if isinstance(c, (int, float)):
                    cov = f"  (coverage {c * 100:.0f}%)"
            print(f"    + {name}{cov}")
    if result.skipped_existing:
        print(f"\n  Skipped (already present): {', '.join(result.skipped_existing)}")
    if args.dry_run:
        print("\n  [dry-run] nothing written.")
    else:
        print(f"\n  Wrote: {result.output_path}")
        print(f"  Next:  python main.py run --schema {result.output_path} --input-dir {args.input_dir}")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Subcommand: consolidate
# ---------------------------------------------------------------------------

def _build_llm_group_fn(schemas: list[dict]):
    """Return ``fn(names) -> list[list[str]]`` that asks the strong model to group
    semantically-synonymous variable names (for the optional --llm pass)."""
    from patientpunk._utils import get_llm_client, MODEL_STRONG

    descs: dict[str, str] = {}
    for s in schemas:
        for n, d in (s.get("extension_fields") or {}).items():
            if isinstance(d, dict):
                descs.setdefault(n, d.get("description", ""))

    def group(names: list[str]) -> list[list[str]]:
        client = get_llm_client()
        listing = "\n".join(f"- {n}: {descs.get(n, '')[:140]}" for n in names)
        prompt = (
            "These are auto-discovered data variables; some are the SAME concept "
            "under different names. Group ONLY true synonyms (same concept). Return "
            "a JSON array of arrays of variable names; every name appears in exactly "
            "one array; singletons are fine. No prose.\n\n" + listing
        )
        try:
            resp = client.messages.create(
                model=MODEL_STRONG, max_tokens=4000, temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text
            start, end = text.find("["), text.rfind("]")
            groups = json.loads(text[start:end + 1]) if start >= 0 else []
            return [g for g in groups if isinstance(g, list) and len(g) > 1]
        except Exception as exc:  # defensive: fall back to deterministic only
            print(f"  ! LLM grouping failed ({exc}); using deterministic grouping only")
            return []

    return group


def _add_consolidate_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = sub.add_parser(
        "consolidate",
        help="Merge discovered schemas from multiple runs into one deduped schema.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Merge the discovered schemas from several discovery runs into ONE deduplicated
emergent schema, collapsing naming drift (medication_trial_outcome_category /
medication_trial_outcome / med_response -> one canonical field).

Run AFTER discovering on multiple slices, BEFORE promote + deductive extraction:
  for slice in ...: python main.py run --schema base.json --discover auto --input-dir <slice>
  python main.py consolidate --inputs <slice1>/temp/discovered_*.json ... --min-runs 2
  python main.py promote     --schema base.json --discovered-schema schemas/consolidated_schema.json
  python main.py run         --schema base_promoted.json   # deductive, at scale

--min-runs is the robustness knob: keep only concepts that re-emerged in >= N
independent runs (high = tight clusterable core; 1 = keep the full emergent tail).
        """,
    )
    p.add_argument("--inputs", type=Path, nargs="+", default=None,
                   help="Discovered schema JSON files (default: glob {temp-dir}/discovered_*.json).")
    p.add_argument("--input-dir", type=Path, default=_DEFAULT_INPUT_DIR,
                   help=f"Corpus / output dir, used to locate temp/ (default: {_DEFAULT_INPUT_DIR}).")
    p.add_argument("--temp-dir", type=Path, default=None,
                   help="Where discovered_*.json live (default: {input-dir}/temp/).")
    p.add_argument("--name-threshold", type=float, default=0.6,
                   help="Token-overlap threshold for merging near-synonym names (default 0.6).")
    p.add_argument("--min-runs", type=int, default=1,
                   help="Keep only concepts seen in >= this many discovery runs (robustness filter).")
    p.add_argument("--llm", action="store_true",
                   help="Add an LLM semantic-synonym pass (non-deterministic; uses MODEL_STRONG).")
    p.add_argument("--base-schema-id", default=None,
                   help="Recorded as _base_schema on the output (lineage).")
    p.add_argument("--output", type=Path, default=None,
                   help="Output schema (default: schemas/consolidated_schema.json).")
    p.add_argument("--dry-run", action="store_true",
                   help="Report the merge without writing.")


def _cmd_consolidate(args: argparse.Namespace) -> None:
    if args.inputs:
        paths = [p if p.is_absolute() else _HERE / p for p in args.inputs]
    else:
        temp_dir = args.temp_dir or (args.input_dir / "temp")
        paths = sorted(
            p for p in temp_dir.glob("discovered_*.json")
            if "field_report" not in p.name and "records" not in p.name
        )

    schemas: list[dict] = []
    for p in paths:
        if not p.exists():
            sys.exit(f"Not found: {p}")
        d = load_json(p)
        if isinstance(d, dict) and d.get("extension_fields") is not None:
            schemas.append(d)
        else:
            print(f"  ! skipping (no extension_fields): {p.name}")

    if not schemas:
        sys.exit(
            "No discovered schemas found.\n"
            "  Run discovery on >=2 slices first: python main.py run --schema ... --discover auto"
        )
    if len(schemas) < 2:
        print(f"  ! only {len(schemas)} schema -- consolidation is most useful across >=2 discovery runs")

    llm_fn = _build_llm_group_fn(schemas) if args.llm else None
    result = consolidate_schemas(
        schemas,
        name_threshold=args.name_threshold,
        min_runs=args.min_runs,
        base_schema_id=args.base_schema_id,
        llm_group_fn=llm_fn,
    )

    print(f"\nInputs: {len(schemas)} discovered schema(s)")
    print(result.summary())
    multi = [m for m in result.merges if len(m["members"]) > 1]
    if multi:
        print(f"\n  Merged synonym groups ({len(multi)}):")
        for m in multi:
            others = [x for x in m["members"] if x != m["canonical"]]
            print(f"    [{m['n_runs']}x] {m['canonical']}  <-  {', '.join(others)}")

    out = args.output if args.output else (_DEFAULT_SCHEMA_DIR / "consolidated_schema.json")
    if not out.is_absolute():
        out = _HERE / out
    if args.dry_run:
        print("\n  [dry-run] nothing written.")
    else:
        out.write_text(
            json.dumps(result.consolidated_schema, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\n  Wrote: {out}  ({result.n_consolidated} fields)")
        print(f"  Next:  python main.py promote --schema <base_schema> --discovered-schema {out}")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Subcommand: validate
# ---------------------------------------------------------------------------

def _add_validate_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = sub.add_parser(
        "validate",
        help="Score an extraction against a reference, per field (or export a gold template).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Per-field evaluation: score a CANDIDATE records.csv against a REFERENCE
records.csv (gold human labels, or a trusted strong-model silver reference).
Decide -- per field -- whether a cheaper model (e.g. on dispersed) is good
enough before scaling.

  python main.py validate --reference gold.csv --candidate cheap_model.csv

Or export a blank gold-labeling sheet from a records.csv for a human to fill:

  python main.py validate --export-template --records output/records.csv \\
      --corpus output/subreddit_posts.json --n 150 --out gold_template.csv
        """,
    )
    p.add_argument("--reference", type=Path, default=None, help="Reference (gold/silver) records.csv.")
    p.add_argument("--candidate", type=Path, default=None, help="Candidate records.csv to score.")
    p.add_argument("--export-template", action="store_true",
                   help="Export a blank gold-labeling sheet instead of scoring.")
    p.add_argument("--records", type=Path, default=None,
                   help="(template mode) records.csv to sample rows from.")
    p.add_argument("--corpus", type=Path, default=None,
                   help="(template mode) subreddit_posts.json for inline source text.")
    p.add_argument("--n", type=int, default=None, help="(template mode) number of rows to sample.")
    p.add_argument("--fields", default=None,
                   help="Comma-separated fields to score/label (default: all data fields).")
    p.add_argument("--key", default="author_hash,post_id",
                   help="Join key columns (default: author_hash,post_id).")
    p.add_argument("--sep", default=" | ", help="Multi-value separator (default: ' | ').")
    p.add_argument("--out", type=Path, default=None,
                   help="Write scorecard CSV (score mode) or template CSV (template mode).")


def _cmd_validate(args: argparse.Namespace) -> None:
    key = tuple(c.strip() for c in args.key.split(",") if c.strip())
    fields = [f.strip() for f in args.fields.split(",") if f.strip()] if args.fields else None

    if args.export_template:
        records = args.records or (_DEFAULT_INPUT_DIR / "records.csv")
        if not records.exists():
            sys.exit(f"records not found: {records}")
        rows, _ = load_records(records, key)
        if not rows:
            sys.exit(f"no rows in {records}")
        if fields is None:
            from patientpunk.evaluate import _data_fields
            fields = _data_fields(next(iter(rows.values())))
        corpus_text = None
        if args.corpus and args.corpus.exists():
            corpus_text = {}
            data = load_json(args.corpus) or []

            def _walk(node):
                pid = node.get("post_id") or node.get("id")
                txt = "\n".join(filter(None, [node.get("title", ""), node.get("body", ""), node.get("text", "")]))
                if pid:
                    corpus_text[pid] = txt
                for c in node.get("comments") or []:
                    _walk(c)

            for post in (data if isinstance(data, list) else []):
                _walk(post)
        out = args.out or (_HERE.parent / "gold_template.csv")
        n_written = export_gold_template(rows, fields, out, key=key, corpus_text=corpus_text, n=args.n)
        print(f"  Wrote gold-labeling template: {out}  ({n_written} rows x {len(fields)} fields to label)")
        print("  Fill the blank field columns with TRUE values, then score a model against it:")
        print(f"    python main.py validate --reference {out} --candidate <model_output>.csv")
        sys.exit(0)

    # --- score mode ---
    if not args.reference or not args.candidate:
        sys.exit("Score mode needs --reference and --candidate (or use --export-template).")
    if not args.reference.exists():
        sys.exit(f"reference not found: {args.reference}")
    if not args.candidate.exists():
        sys.exit(f"candidate not found: {args.candidate}")

    ref_rows, _ = load_records(args.reference, key)
    cand_rows, _ = load_records(args.candidate, key)
    result = score_extraction(ref_rows, cand_rows, fields=fields, sep=args.sep)

    print(f"\nReference: {args.reference.name} ({result.n_reference} rows)")
    print(f"Candidate: {args.candidate.name} ({result.n_candidate} rows)")
    print(f"Matched on {','.join(key)}: {result.n_matched} rows\n")
    scored = [(f, m) for f, m in result.per_field.items() if m["n_present"] > 0]
    scored.sort(key=lambda fm: fm[1]["f1"])   # worst first -- surface the problems
    print(f"  {'field':<40}{'f1':>6}{'prec':>6}{'rec':>6}{'agree':>7}{'n':>5}  ref/cand")
    for f, m in scored:
        print(f"  {f:<40}{m['f1']:>6.2f}{m['precision']:>6.2f}{m['recall']:>6.2f}"
              f"{m['agreement_present']:>7.2f}{m['n_present']:>5}  {m['ref_fill']}/{m['cand_fill']}")
    o = result.overall
    print(f"\n  macro F1: {o['macro_f1']:.2f}   macro agreement: {o['macro_agreement']:.2f}   "
          f"({o['n_fields_with_data']}/{o['n_fields_scored']} fields had data)")
    if args.out:
        import csv as _csv
        with open(args.out, "w", newline="", encoding="utf-8") as fh:
            w = _csv.writer(fh)
            w.writerow(["field", "f1", "precision", "recall", "agreement_present",
                        "n_present", "ref_fill", "cand_fill"])
            for f, m in result.per_field.items():
                w.writerow([f, m["f1"], m["precision"], m["recall"], m["agreement_present"],
                            m["n_present"], m["ref_fill"], m["cand_fill"]])
        print(f"  Wrote scorecard: {args.out}")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Subcommand: cluster-prep
# ---------------------------------------------------------------------------

def _add_cluster_prep_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = sub.add_parser(
        "cluster-prep",
        help="Build a per-patient, clustering-ready feature matrix from records.csv.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Turn records.csv (per-record, wide, high-cardinality free-text) into a
clustering-ready PER-PATIENT feature matrix:

  aggregate by patient -> drop sparse fields (--min-coverage) -> encode with a
  controlled vocabulary (top-k values/field + 'other') -> CSV + clusterability
  report (n, p/n, density, pairwise similarity, silhouette by k).

  python main.py cluster-prep --records output/records.csv --min-coverage 0.3 --top-k 8

--encode topk (default) collapses cardinality to the top values per field -- the
single biggest clusterability lever. Use --encode presence for the most
aggressive collapse, multihot for none.
        """,
    )
    p.add_argument("--records", type=Path, default=_DEFAULT_INPUT_DIR / "records.csv",
                   help=f"Extraction records.csv (default: {_DEFAULT_INPUT_DIR / 'records.csv'}).")
    p.add_argument("--key", default="author_hash",
                   help="Patient-unit column (default: author_hash).")
    p.add_argument("--min-coverage", type=float, default=0.25,
                   help="Drop fields below this patient coverage (default: 0.25).")
    p.add_argument("--encode", choices=["presence", "topk", "multihot"], default="topk",
                   help="Encoding (default: topk = controlled vocabulary).")
    p.add_argument("--top-k", type=int, default=8,
                   help="topk: number of values kept per field (default: 8).")
    p.add_argument("--fields", default=None, help="Restrict to these comma-separated fields.")
    p.add_argument("--sep", default=" | ", help="Multi-value separator (default: ' | ').")
    p.add_argument("--out", type=Path, default=None,
                   help="Matrix CSV (default: <records dir>/feature_matrix.csv).")
    p.add_argument("--no-report", action="store_true", help="Skip the clusterability report.")


def _cmd_cluster_prep(args: argparse.Namespace) -> None:
    records = args.records
    if not records.exists():
        sys.exit(f"records not found: {records}")
    rows = read_records(records)
    if not rows:
        sys.exit(f"no rows in {records}")

    patients, all_fields = aggregate_patients(rows, key_col=args.key, sep=args.sep)
    if not patients:
        sys.exit(f"no patients found (is --key '{args.key}' a column in {records.name}?)")
    fields = [f.strip() for f in args.fields.split(",") if f.strip()] if args.fields else all_fields
    kept, _cov = select_fields(patients, fields, args.min_coverage)
    if not kept:
        sys.exit(f"no fields with >= {args.min_coverage:.0%} coverage; lower --min-coverage")
    pids, names, X = build_matrix(patients, kept, encode=args.encode, top_k=args.top_k)

    print(f"\nGRAIN:    {len(rows)} records -> {len(pids)} patients (by {args.key})")
    print(f"FEATURES: {len(kept)}/{len(all_fields)} fields >= {args.min_coverage:.0%} coverage; "
          f"encode={args.encode}" + (f" top_k={args.top_k}" if args.encode == "topk" else ""))
    print(f"MATRIX:   {len(pids)} x {len(names)} features")

    out = args.out or (records.parent / "feature_matrix.csv")
    write_matrix(out, pids, names, X)
    print(f"  Wrote: {out}")

    if args.no_report:
        sys.exit(0)

    rep = readiness_report(pids, names, X)
    print("\nCLUSTERABILITY:")
    print(f"  n={rep['n_patients']}  features={rep['n_features']}  "
          f"p/n={rep['p_over_n']}  density={rep['density'] * 100:.1f}%")
    if not rep["sklearn"]:
        print("  (install scikit-learn for similarity + silhouette: pip install 'patientpunk[cluster]')")
    else:
        print(f"  pairwise similarity: median={rep['similarity_median']}  mean={rep['similarity_mean']}")
        sk = rep.get("silhouette_by_k", {})
        if sk:
            print("  silhouette by k:  " + "  ".join(f"k{k}={v:+.2f}" for k, v in sk.items()))
            bs = rep["best_silhouette"]
            verdict = ("STRONG structure" if bs >= 0.5 else
                       "reasonable structure" if bs >= 0.25 else
                       "WEAK / none -- not appropriate")
            print(f"  best silhouette {bs:+.2f} at k={rep['best_k']}  ->  {verdict}")
    if rep["p_over_n"] > 3:
        print("  ! p/n > 3 (too many features per patient) -- raise --min-coverage / lower --top-k")
    if rep["n_patients"] < 100:
        print("  ! n < 100 patients -- too few for trustworthy subpopulations; scale the corpus")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Subcommand: aggregate
# ---------------------------------------------------------------------------

def _add_aggregate_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = sub.add_parser(
        "aggregate",
        help="Collapse a posts+comments corpus into one synthetic post per author (per-patient).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Turn subreddit_posts.json (one record per POST, comments nested) into one
synthetic post per AUTHOR -- a per-PATIENT corpus -- then run the normal pipeline
on the output dir. Extracts once per patient instead of once per post: matches
the clustering unit (cluster-prep aggregates per author anyway) and cuts LLM cost
several-fold.

Every text segment is attributed to ITS OWN author (a reply by B under A's post
counts toward B), so commenters become patients too. --min-items drops authors
with too little text to profile.

  python main.py aggregate --input-dir output --out-dir output_perpatient --min-items 3
  python main.py run --schema schemas/..._promoted.json --input-dir output_perpatient
        """,
    )
    p.add_argument("--input-dir", type=Path, default=_DEFAULT_INPUT_DIR,
                   help=f"Corpus with subreddit_posts.json (default: {_DEFAULT_INPUT_DIR}).")
    p.add_argument("--out-dir", type=Path, default=None,
                   help="Output corpus dir (default: <input-dir>_perpatient).")
    p.add_argument("--min-items", type=int, default=1,
                   help="Drop authors with fewer than this many text segments (default: 1).")
    p.add_argument("--sep", default="\n\n---\n\n",
                   help="Separator joining an author's segments (default: blank-line rule).")


def _cmd_aggregate(args: argparse.Namespace) -> None:
    in_dir = args.input_dir if args.input_dir.is_absolute() else _HERE.parent / args.input_dir
    out_dir = args.out_dir or in_dir.parent / f"{in_dir.name}_perpatient"
    try:
        posts = read_posts(in_dir)
    except FileNotFoundError as exc:
        sys.exit(str(exc))

    agg, stats = aggregate_corpus_by_author(posts, min_items=args.min_items, sep=args.sep)
    if not agg:
        sys.exit(f"no patients after aggregation (min_items={args.min_items}); lower --min-items")
    out_file = write_corpus(out_dir, agg)

    print(f"\nAGGREGATE (per-patient):  {in_dir}  ->  {out_dir}")
    print(f"  in:   {stats['in_posts']} posts + {stats['in_comments']} comments "
          f"({stats['authors_seen']} distinct authors)")
    print(f"  out:  {stats['patients_out']} patients  "
          f"(dropped {stats['dropped_below_min']} with < {stats['min_items']} items)")
    print(f"  text: avg {stats['avg_items_per_patient']} items/patient, "
          f"median {stats['median_body_chars']} chars, max {stats['max_body_chars']}")
    print(f"  wrote {out_file}")
    print(f"\n  next: python main.py run --schema <promoted>.json --input-dir {out_dir}")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Subcommand: normalize
# ---------------------------------------------------------------------------

def _add_normalize_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = sub.add_parser(
        "normalize",
        help="Collapse free-text backbone fields to a controlled vocabulary.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Map the dense free-text fields (conditions, treatment_outcome, symptom_trajectory,
functional_status_tier, ...) onto a small curated vocabulary so cluster-prep
encodes real signal instead of surface noise ("bedbound"/"bedridden",
"helped"/"60% better" -> one value each). Writes a normalized records.csv and
prints the before->after distinct-value collapse. Over-fragmented fields
(targeted_symptom_domain) are blanked unless --keep-dropped.

  python main.py normalize --records output/records.csv
  python main.py cluster-prep --records output/records_normalized.csv --min-coverage 0.25
        """,
    )
    p.add_argument("--records", type=Path, default=_DEFAULT_INPUT_DIR / "records.csv",
                   help=f"records.csv to normalize (default: {_DEFAULT_INPUT_DIR / 'records.csv'}).")
    p.add_argument("--out", type=Path, default=None,
                   help="Output CSV (default: <records>_normalized.csv).")
    p.add_argument("--sep", default=" | ", help="Multi-value separator (default: ' | ').")
    p.add_argument("--keep-dropped", action="store_true",
                   help="Keep over-fragmented DROP_FIELDS instead of blanking them.")


def _cmd_normalize(args: argparse.Namespace) -> None:
    import csv
    src = args.records
    if not src.exists():
        sys.exit(f"records not found: {src}")
    with open(src, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)
    if not rows:
        sys.exit(f"no rows in {src}")

    drop = set() if args.keep_dropped else None
    norm = normalize_records(rows, sep=args.sep, drop_fields=drop)
    rep = cardinality_report(rows, norm, sep=args.sep)
    # Decomposition adds derived treatment_outcome columns -> extend the header.
    # Rows have heterogeneous keys (only rows with treatment_outcome get the
    # derived cols), so union all keys in one pass rather than scanning per column.
    present_cols = set().union(*(r.keys() for r in norm)) if norm else set()
    out_fields = list(fields) + [c for c in TREATMENT_OUTCOME_DERIVED
                                 if c not in fields and c in present_cols]
    out = args.out or src.parent / f"{src.stem}_normalized.csv"
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_fields)
        w.writeheader()
        w.writerows(norm)

    blanked = set() if args.keep_dropped else DROP_FIELDS
    print(f"\nNORMALIZE: {src}  ->  {out}")
    print(f"  {len(rows)} rows; controlled-vocab collapse (distinct values, before -> after):")
    for fld, (b, a) in sorted(rep.items(), key=lambda x: -(x[1][0] - x[1][1])):
        tag = "   [blanked: too fragmented]" if fld in blanked else ""
        print(f"    {fld:28} {b:4} -> {a:4}{tag}")
    print(f"\n  next: python main.py cluster-prep --records {out} --min-coverage 0.25")
    sys.exit(0)


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
  python main.py corpus       --input-dir ../output
  python main.py export       --schema schemas/covidlonghaulers_schema.json --codebook-format markdown
  python main.py promote      --schema schemas/covidlonghaulers_schema.json --min-coverage 0.1
  python main.py consolidate  --inputs run1/temp/discovered_*.json run2/temp/discovered_*.json --min-runs 2
  python main.py validate     --reference gold.csv --candidate model_output.csv
  python main.py cluster-prep --records output/records.csv --min-coverage 0.3 --top-k 8
        """,
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    _add_run_parser(sub)
    _add_demographics_parser(sub)
    _add_inspect_parser(sub)
    _add_corpus_parser(sub)
    _add_export_parser(sub)
    _add_promote_parser(sub)
    _add_consolidate_parser(sub)
    _add_validate_parser(sub)
    _add_cluster_prep_parser(sub)
    _add_aggregate_parser(sub)
    _add_normalize_parser(sub)

    args = parser.parse_args()

    dispatch = {
        "run":          _cmd_run,
        "demographics": _cmd_demographics,
        "inspect":      _cmd_inspect,
        "corpus":       _cmd_corpus,
        "export":       _cmd_export,
        "promote":      _cmd_promote,
        "consolidate":  _cmd_consolidate,
        "validate":     _cmd_validate,
        "cluster-prep": _cmd_cluster_prep,
        "aggregate":    _cmd_aggregate,
        "normalize":    _cmd_normalize,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
