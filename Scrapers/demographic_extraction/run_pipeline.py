#!/usr/bin/env python3
"""PatientPunk full pipeline runner.

Runs all extraction steps in sequence, then exports to CSV and codebook.

Steps:
  1  extract_biomedical.py   Regex extraction (free, seconds)
  2  llm_extract.py          LLM gap-filling with Claude Haiku
  3  discover_fields.py      Field discovery + regex + Haiku fill
  4  records_to_csv.py       Flatten records to CSV
  5  make_codebook.py        Generate data dictionary

Intermediate files are written to output/temp/ and wiped at the start of
each full run (--start-at 1). Pass --no-clean to skip the wipe.

Usage:
    # Full run (all steps):
    python run_pipeline.py --schema schemas/covidlonghaulers_schema.json

    # Skip Phase 1 discovery (reuse saved candidates):
    python run_pipeline.py --schema schemas/covidlonghaulers_schema.json --candidates ../output/temp/phase1_candidates.json

    # Skip LLM steps entirely (regex only, free):
    python run_pipeline.py --schema schemas/covidlonghaulers_schema.json --no-llm

    # Skip discover_fields (just regex + LLM + export):
    python run_pipeline.py --schema schemas/covidlonghaulers_schema.json --no-discover

    # Resume interrupted run starting from a specific step:
    python run_pipeline.py --schema schemas/covidlonghaulers_schema.json --start-at 3

    # Test run (cheap — limit records, skip discover):
    python run_pipeline.py --schema schemas/covidlonghaulers_schema.json --limit 10 --no-discover

    # Codebook in markdown:
    python run_pipeline.py --schema schemas/covidlonghaulers_schema.json --codebook-format markdown
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


HERE = Path(__file__).parent
OUTPUT_DIR = HERE.parent / "output"
TEMP_DIR = OUTPUT_DIR / "temp"

PHASE_NAMES = {
    1: "extract_biomedical.py   (regex extraction)",
    2: "llm_extract.py          (LLM gap-filling)",
    3: "discover_fields.py      (field discovery)",
    4: "records_to_csv.py       (CSV export)",
    5: "make_codebook.py        (codebook)",
}

# Intermediate file patterns that live in TEMP_DIR.
# These are wiped at the start of a full run (--start-at 1).
TEMP_PATTERNS = [
    "patientpunk_records_*.json",
    "extraction_metadata_*.json",
    "llm_records_*.json",
    "llm_field_suggestions_*.json",
    "merged_records_*.json",
    "phase1_candidates.json",
    "discovered_records_*.json",
    "discovered_field_report_*.json",
]


def clean_temp(temp_dir: Path) -> None:
    """Remove all intermediate files from temp_dir."""
    if not temp_dir.exists():
        return
    removed = []
    for pattern in TEMP_PATTERNS:
        for f in temp_dir.glob(pattern):
            f.unlink()
            removed.append(f.name)
    if removed:
        print(f"  Cleaned {len(removed)} intermediate file(s) from {temp_dir.name}/:")
        for name in sorted(removed):
            print(f"    {name}")
    else:
        print(f"  {temp_dir.name}/ already clean.")


def banner(phase: int, label: str) -> None:
    print("\n" + "=" * 60)
    print(f"  PHASE {phase}: {label}")
    print("=" * 60)


def run(cmd: list[str], phase: int) -> None:
    """Run a command, streaming output. Exit on failure."""
    print(f"  Running: {' '.join(str(c) for c in cmd)}\n")
    result = subprocess.run(cmd, cwd=HERE)
    if result.returncode != 0:
        print(f"\n[Pipeline stopped] Phase {phase} failed with exit code {result.returncode}.")
        sys.exit(result.returncode)


def get_schema_id(schema_path: Path) -> str:
    with open(schema_path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("schema_id", schema_path.stem)


def find_discovered_records(schema_id: str, temp_dir: Path) -> Path | None:
    path = temp_dir / f"discovered_records_{schema_id}.json"
    return path if path.exists() else None


def main():
    parser = argparse.ArgumentParser(
        description="Run the full PatientPunk extraction pipeline end-to-end.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Phases:
  1  extract_biomedical.py   Regex extraction (free, seconds)
  2  llm_extract.py          LLM gap-filling (Claude Haiku)
  3  discover_fields.py      Field discovery — 4 internal stages (Haiku + Sonnet)
                               Stage 1: Candidate scan (Haiku)
                               Stage 2: Regex generation (Sonnet)
                               Stage 3: Regex extraction (free)
                               Stage 4: Gap fill (Haiku)
  4  records_to_csv.py       Flatten all records to CSV
  5  make_codebook.py        Generate data dictionary / codebook

Intermediate files:
  All intermediate files go to output/temp/ and are wiped at the start
  of each full run (--start-at 1). Final outputs (records.csv, codebook.csv)
  stay in output/. Pass --no-clean to keep intermediates from a prior run.

Auto-detect behaviour:
  If output/temp/phase1_candidates.json exists when step 3 runs, it is used
  automatically (saves Phase 1 cost). A notice is printed. Pass --candidates
  to override the file used, or use --no-clean to preserve and reuse it.

Examples:
  # Full run — the recommended way to run the pipeline
  python run_pipeline.py --schema schemas/covidlonghaulers_schema.json

  # Supply saved Phase 1 candidates explicitly
  python run_pipeline.py --schema schemas/covidlonghaulers_schema.json \\
      --candidates ../output/temp/phase1_candidates.json

  # Free-only run (no API calls): regex + CSV + codebook
  python run_pipeline.py --schema schemas/covidlonghaulers_schema.json \\
      --no-llm --no-discover

  # Skip field discovery but still run LLM gap-filling
  python run_pipeline.py --schema schemas/covidlonghaulers_schema.json --no-discover

  # Cheap test run (10 records, no discovery)
  python run_pipeline.py --schema schemas/covidlonghaulers_schema.json \\
      --limit 10 --no-discover

  # Resume interrupted run from phase 3 (field discovery)
  python run_pipeline.py --schema schemas/covidlonghaulers_schema.json --start-at 3

  # Markdown codebook
  python run_pipeline.py --schema schemas/covidlonghaulers_schema.json \\
      --codebook-format markdown
        """,
    )

    # Core
    parser.add_argument("--schema", type=Path, required=True,
                        help="Extension schema JSON (e.g. schemas/covidlonghaulers_schema.json)")
    parser.add_argument("--input-dir", type=Path, default=OUTPUT_DIR,
                        help=f"Input/output directory (default: {OUTPUT_DIR})")
    parser.add_argument("--temp-dir", type=Path, default=None,
                        help="Intermediate file directory (default: {input-dir}/temp/)")

    # Phase control
    parser.add_argument("--start-at", type=int, default=1, choices=[1, 2, 3, 4, 5],
                        help="Start from this phase number (skip earlier phases). "
                             "1=regex, 2=LLM, 3=discover, 4=CSV, 5=codebook")
    parser.add_argument("--no-llm", action="store_true",
                        help="Skip phase 2 (llm_extract.py)")
    parser.add_argument("--no-discover", action="store_true",
                        help="Skip phase 3 (discover_fields.py)")
    parser.add_argument("--no-clean", action="store_true",
                        help="Skip wiping output/temp/ at the start. Useful when resuming "
                             "or reusing cached Phase 1 candidates.")

    # discover_fields options
    parser.add_argument("--candidates", type=Path, default=None,
                        help=(
                            "Path to a saved phase1_candidates.json — skips Stage 1 of "
                            "discover_fields.py. If not supplied and output/temp/phase1_candidates.json "
                            "exists, it is used automatically (a notice is printed). "
                            "Pass --no-clean to preserve and reuse the cached candidates."
                        ))
    parser.add_argument("--no-fill", action="store_true",
                        help="Skip Stage 4 gap-filling in discover_fields.py")
    parser.add_argument("--sample", type=int, default=None,
                        help="Random sample N corpus items for discover Stage 1")

    # Shared options
    parser.add_argument("--workers", type=int, default=10,
                        help="Concurrent workers for LLM calls (default: 10)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process at most N records (cost-control / testing)")
    parser.add_argument("--resume", action="store_true",
                        help="Resume interrupted LLM / discover runs")

    # Export options
    parser.add_argument("--sep", default=" | ",
                        help="Multi-value separator for CSV (default: ' | ')")
    parser.add_argument("--provenance", action="store_true",
                        help="Include provenance + confidence columns in CSV")
    parser.add_argument("--codebook-format", choices=["csv", "markdown"], default="csv",
                        help="Codebook output format (default: csv)")

    args = parser.parse_args()

    schema_path = args.schema if args.schema.is_absolute() else HERE / args.schema
    if not schema_path.exists():
        sys.exit(f"Schema not found: {schema_path}")

    schema_id = get_schema_id(schema_path)
    input_dir = args.input_dir
    temp_dir = args.temp_dir if args.temp_dir else input_dir / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    python = sys.executable

    start = time.time()
    print(f"\nPatientPunk Pipeline")
    print(f"  Schema:    {schema_path.name}  (id: {schema_id})")
    print(f"  Input/out: {input_dir}")
    print(f"  Temp:      {temp_dir}")
    if args.start_at > 1:
        print(f"  Starting at phase {args.start_at}")
    if args.no_llm:
        print(f"  Skipping:  phase 2 (--no-llm)")
    if args.no_discover:
        print(f"  Skipping:  phase 3 (--no-discover)")

    # -------------------------------------------------------------------------
    # Clean temp/ at the start of a full run
    # -------------------------------------------------------------------------
    if args.start_at == 1 and not args.no_clean:
        print("\n" + "=" * 60)
        print("  Cleaning intermediate files from temp/")
        print("=" * 60)
        clean_temp(temp_dir)

    # -------------------------------------------------------------------------
    # Phase 1: Regex extraction
    # -------------------------------------------------------------------------
    if args.start_at <= 1:
        banner(1, PHASE_NAMES[1])
        cmd = [python, "extract_biomedical.py",
               "--schema", str(schema_path),
               "--input-dir", str(input_dir),
               "--temp-dir", str(temp_dir)]
        run(cmd, phase=1)

    # -------------------------------------------------------------------------
    # Phase 2: LLM gap-filling
    # -------------------------------------------------------------------------
    if args.start_at <= 2 and not args.no_llm:
        banner(2, PHASE_NAMES[2])
        cmd = [python, "llm_extract.py",
               "--schema", str(schema_path),
               "--input-dir", str(input_dir),
               "--temp-dir", str(temp_dir),
               "--workers", str(args.workers)]
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        if args.resume:
            cmd += ["--resume"]
        run(cmd, phase=2)
    elif args.start_at <= 2:
        print(f"\n  [Skipping phase 2 — --no-llm]")

    # -------------------------------------------------------------------------
    # Phase 3: Field discovery
    # -------------------------------------------------------------------------
    if args.start_at <= 3 and not args.no_discover:
        banner(3, PHASE_NAMES[3])
        cmd = [python, "discover_fields.py",
               "--schema", str(schema_path),
               "--input-dir", str(input_dir),
               "--temp-dir", str(temp_dir),
               "--workers", str(args.workers)]

        # Auto-detect candidates file if not specified
        candidates = args.candidates
        if candidates is None:
            auto = temp_dir / "phase1_candidates.json"
            if auto.exists():
                print(f"  Auto-detected saved candidates: {auto.name}")
                print(f"  (Pass --no-clean on next run to reuse, or delete to re-run Stage 1)\n")
                candidates = auto

        if candidates:
            cmd += ["--candidates", str(candidates)]
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        if args.sample:
            cmd += ["--sample", str(args.sample)]
        if args.resume:
            cmd += ["--resume"]
        if args.no_fill:
            cmd += ["--no-fill"]
        run(cmd, phase=3)
    elif args.start_at <= 3:
        print(f"\n  [Skipping phase 3 — --no-discover]")

    # -------------------------------------------------------------------------
    # Phase 4: CSV export
    # -------------------------------------------------------------------------
    if args.start_at <= 4:
        banner(4, PHASE_NAMES[4])

        # Always include base merged records
        input_files = [temp_dir / "merged_records_base.json"]

        # Add discovered records if they exist
        discovered = find_discovered_records(schema_id, temp_dir)
        if discovered:
            input_files.append(discovered)
            print(f"  Including discovered records: {discovered.name}")
        else:
            print(f"  No discovered records found for schema '{schema_id}' — exporting base only")

        # Check at least one input exists
        missing = [p for p in input_files if not p.exists()]
        if missing:
            print(f"\n  [Warning] Missing input files: {[str(p) for p in missing]}")
            input_files = [p for p in input_files if p.exists()]
        if not input_files:
            print("  [Skipping phase 4 — no input files found]")
        else:
            cmd = [python, "records_to_csv.py",
                   "--input"] + [str(p) for p in input_files] + [
                   "--sep", args.sep]
            if args.provenance:
                cmd += ["--provenance"]
            run(cmd, phase=4)

    # -------------------------------------------------------------------------
    # Phase 5: Codebook
    # -------------------------------------------------------------------------
    if args.start_at <= 5:
        banner(5, PHASE_NAMES[5])
        records_csv = OUTPUT_DIR / "records.csv"
        cmd = [python, "make_codebook.py",
               "--schema", str(schema_path),
               "--format", args.codebook_format]
        if records_csv.exists():
            cmd += ["--csv", str(records_csv)]
        else:
            print(f"  [Note] records.csv not found — codebook will have schema info only")
        run(cmd, phase=5)

    # -------------------------------------------------------------------------
    # Done
    # -------------------------------------------------------------------------
    elapsed = time.time() - start
    mins, secs = divmod(int(elapsed), 60)
    print("\n" + "=" * 60)
    print(f"  Pipeline complete  ({mins}m {secs}s)")
    print(f"  CSV:      {OUTPUT_DIR / 'records.csv'}")
    codebook_ext = "md" if args.codebook_format == "markdown" else "csv"
    print(f"  Codebook: {OUTPUT_DIR / f'codebook.{codebook_ext}'}")
    print(f"  Temp:     {temp_dir}  (intermediates preserved — delete to free space)")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
