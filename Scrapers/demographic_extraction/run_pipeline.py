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
import csv
import json
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


# =============================================================================
# PHASE STATISTICS
# =============================================================================

def _load_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def collect_phase1_stats(temp_dir: Path, schema_id: str) -> dict:
    meta = _load_json(temp_dir / f"extraction_metadata_{schema_id}.json")
    if not meta:
        return {}
    total = meta.get("total_records_processed", 0)
    hits = meta.get("field_hit_counts", {})
    n_fields = len(hits)
    n_hit = sum(1 for v in hits.values() if v > 0)
    top = sorted(hits.items(), key=lambda x: -x[1])[:5]
    weak = [(f, v) for f, v in hits.items() if total and v / total < 0.10]
    return {
        "records": total,
        "fields_available": n_fields,
        "fields_with_hits": n_hit,
        "fields_zero_coverage": n_fields - n_hit,
        "top_fields": [(f, v, v / total if total else 0) for f, v in top],
        "weak_fields": sorted(weak, key=lambda x: x[1]),
    }


def collect_phase2_stats(temp_dir: Path, schema_id: str) -> dict:
    regex_path = temp_dir / f"patientpunk_records_{schema_id}.json"
    llm_path   = temp_dir / f"llm_records_{schema_id}.json"
    merged_path = temp_dir / f"merged_records_{schema_id}.json"
    regex   = _load_json(regex_path) or []
    llm     = _load_json(llm_path) or []
    merged  = _load_json(merged_path) or []

    # Count LLM-filled values: fields that are non-null in llm_records
    llm_fills = 0
    for rec in llm:
        for v in rec.get("fields", {}).values():
            if v is not None:
                llm_fills += 1

    return {
        "records_llm": len(llm),
        "records_merged": len(merged),
        "llm_field_fills": llm_fills,
        "avg_fills_per_record": round(llm_fills / len(llm), 2) if llm else 0,
    }


def collect_phase3_stats(temp_dir: Path) -> dict:
    disc_files = sorted(temp_dir.glob("discovered_records_*.json"))
    if not disc_files:
        return {}
    records = _load_json(disc_files[-1]) or []
    if not records:
        return {}
    # Gather discovered field names and hit counts
    field_hits: dict[str, int] = {}
    for rec in records:
        for fname, fdata in rec.get("discovered_fields", {}).items():
            if fdata.get("values"):
                field_hits[fname] = field_hits.get(fname, 0) + 1
    n_records = len(records)
    records_with_any = sum(
        1 for rec in records
        if any(fd.get("values") for fd in rec.get("discovered_fields", {}).values())
    )
    by_prov: dict[str, int] = {"regex": 0, "llm_filled": 0}
    for rec in records:
        for fdata in rec.get("discovered_fields", {}).values():
            p = fdata.get("provenance")
            if p in by_prov:
                by_prov[p] += 1
    return {
        "fields_discovered": len(field_hits),
        "records_total": n_records,
        "records_with_any_hit": records_with_any,
        "coverage_pct": round(records_with_any / n_records * 100, 1) if n_records else 0,
        "hits_by_regex": by_prov["regex"],
        "hits_by_llm": by_prov["llm_filled"],
        "top_fields": sorted(field_hits.items(), key=lambda x: -x[1])[:5],
    }


def collect_phase4_stats(output_dir: Path) -> dict:
    csv_path = output_dir / "records.csv"
    if not csv_path.exists():
        return {}
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        cols = reader.fieldnames or []
    if not rows:
        return {}
    total_cells = len(rows) * len(cols)
    filled_cells = sum(1 for row in rows for v in row.values() if v and v.strip())
    return {
        "rows": len(rows),
        "columns": len(cols),
        "fill_rate": round(filled_cells / total_cells * 100, 1) if total_cells else 0,
        "total_cells": total_cells,
        "filled_cells": filled_cells,
    }


def collect_phase5_stats(output_dir: Path) -> dict:
    for name in ("codebook.csv", "codebook.md"):
        p = output_dir / name
        if p.exists():
            if name.endswith(".csv"):
                with open(p, encoding="utf-8") as f:
                    rows = list(csv.DictReader(f))
                covered = sum(1 for r in rows if r.get("coverage_pct", "").replace("%","").strip() not in ("", "0", "0.0"))
                return {"fields": len(rows), "fields_with_coverage": covered}
            else:
                lines = p.read_text(encoding="utf-8").splitlines()
                fields = sum(1 for l in lines if l.startswith("## "))
                return {"fields": fields}
    return {}


def print_phase_summary(phase: int, stats: dict, elapsed: float) -> None:
    """Print a compact stats block right after a phase completes."""
    if not stats:
        return
    label = PHASE_NAMES.get(phase, f"Phase {phase}")
    print(f"\n  ── Phase {phase} stats ({elapsed:.0f}s) ──────────────────────────")
    if phase == 1:
        total = stats.get("records", 0)
        print(f"  Records processed : {total}")
        print(f"  Fields with hits  : {stats['fields_with_hits']}/{stats['fields_available']}")
        print(f"  Zero coverage     : {stats['fields_zero_coverage']} field(s)")
        print(f"  Top fields        :", end="")
        for f, n, pct in stats.get("top_fields", []):
            print(f"  {f} {pct:.0%}", end="")
        print()
    elif phase == 2:
        print(f"  LLM records       : {stats.get('records_llm', 0)}")
        print(f"  Merged records    : {stats.get('records_merged', 0)}")
        print(f"  LLM field fills   : {stats.get('llm_field_fills', 0)}")
        print(f"  Avg fills/record  : {stats.get('avg_fills_per_record', 0)}")
    elif phase == 3:
        if not stats:
            print("  No fields discovered this run.")
        else:
            print(f"  Fields discovered : {stats.get('fields_discovered', 0)}")
            print(f"  Records with hits : {stats.get('records_with_any_hit', 0)}/{stats.get('records_total', 0)} ({stats.get('coverage_pct', 0)}%)")
            print(f"  Hits by regex     : {stats.get('hits_by_regex', 0)}")
            print(f"  Hits by LLM fill  : {stats.get('hits_by_llm', 0)}")
    elif phase == 4:
        print(f"  Rows              : {stats.get('rows', 0)}")
        print(f"  Columns           : {stats.get('columns', 0)}")
        print(f"  Overall fill rate : {stats.get('fill_rate', 0)}%  ({stats.get('filled_cells', 0)}/{stats.get('total_cells', 0)} cells)")
    elif phase == 5:
        print(f"  Fields documented : {stats.get('fields', 0)}")
        if "fields_with_coverage" in stats:
            print(f"  Fields with data  : {stats['fields_with_coverage']}")
    print(f"  {'─' * 52}")


def print_pipeline_summary(all_stats: dict, total_elapsed: float) -> None:
    """Print the final end-to-end summary table."""
    mins, secs = divmod(int(total_elapsed), 60)
    print("\n" + "=" * 60)
    print(f"  PIPELINE SUMMARY  ({mins}m {secs}s total)")
    print("=" * 60)

    p1 = all_stats.get(1, {})
    p2 = all_stats.get(2, {})
    p3 = all_stats.get(3, {})
    p4 = all_stats.get(4, {})
    p5 = all_stats.get(5, {})

    if p1:
        print(f"\n  Phase 1 — Regex extraction")
        print(f"    {p1.get('records', 0)} records   "
              f"{p1.get('fields_with_hits', 0)}/{p1.get('fields_available', 0)} fields hit   "
              f"{p1.get('fields_zero_coverage', 0)} fields empty")
    if p2:
        print(f"\n  Phase 2 — LLM gap-fill")
        print(f"    {p2.get('records_merged', 0)} merged records   "
              f"{p2.get('llm_field_fills', 0)} LLM fills   "
              f"{p2.get('avg_fills_per_record', 0)} fills/record avg")
    if p3:
        print(f"\n  Phase 3 — Field discovery")
        print(f"    {p3.get('fields_discovered', 0)} new fields   "
              f"{p3.get('records_with_any_hit', 0)}/{p3.get('records_total', 0)} records hit "
              f"({p3.get('coverage_pct', 0)}%)")
        print(f"    regex hits: {p3.get('hits_by_regex', 0)}   "
              f"llm fills: {p3.get('hits_by_llm', 0)}")
        if p3.get("top_fields"):
            tops = "  ".join(f"{f}({n})" for f, n in p3["top_fields"])
            print(f"    top: {tops}")
    elif 3 in all_stats:
        print(f"\n  Phase 3 — Field discovery")
        print(f"    0 new fields discovered")
    if p4:
        print(f"\n  Phase 4 — CSV export")
        print(f"    {p4.get('rows', 0)} rows × {p4.get('columns', 0)} columns   "
              f"{p4.get('fill_rate', 0)}% fill rate")
    if p5:
        print(f"\n  Phase 5 — Codebook")
        print(f"    {p5.get('fields', 0)} fields documented   "
              f"{p5.get('fields_with_coverage', '?')} with observed data")

    print("\n" + "=" * 60 + "\n")


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


def find_discovered_records(temp_dir: Path) -> Path | None:
    """Find the most recent discovered_records_*.json in temp/.

    Discoveries are now always written to a new timestamped file in temp/
    rather than merged into the curated schema, so we find by glob and
    take the newest one.
    """
    matches = sorted(temp_dir.glob("discovered_records_*.json"))
    return matches[-1] if matches else None


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
    parser.add_argument("--codebook-no-discovered", action="store_true",
                        help="Exclude llm_discovered fields from the codebook output.")

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
    all_stats: dict[int, dict] = {}
    phase_times: dict[int, float] = {}
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
        t0 = time.time()
        run(cmd, phase=1)
        phase_times[1] = time.time() - t0
        all_stats[1] = collect_phase1_stats(temp_dir, schema_id)
        print_phase_summary(1, all_stats[1], phase_times[1])

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
        t0 = time.time()
        run(cmd, phase=2)
        phase_times[2] = time.time() - t0
        all_stats[2] = collect_phase2_stats(temp_dir, schema_id)
        print_phase_summary(2, all_stats[2], phase_times[2])
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
        t0 = time.time()
        run(cmd, phase=3)
        phase_times[3] = time.time() - t0
        all_stats[3] = collect_phase3_stats(temp_dir)
        print_phase_summary(3, all_stats[3], phase_times[3])
    elif args.start_at <= 3:
        print(f"\n  [Skipping phase 3 — --no-discover]")

    # -------------------------------------------------------------------------
    # Phase 4: CSV export
    # -------------------------------------------------------------------------
    if args.start_at <= 4:
        banner(4, PHASE_NAMES[4])

        # Always include merged records for this schema
        input_files = [temp_dir / f"merged_records_{schema_id}.json"]

        # Add discovered records if they exist (most recent in temp/)
        discovered = find_discovered_records(temp_dir)
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
            t0 = time.time()
            run(cmd, phase=4)
            phase_times[4] = time.time() - t0
            all_stats[4] = collect_phase4_stats(OUTPUT_DIR)
            print_phase_summary(4, all_stats[4], phase_times[4])

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
        if args.codebook_no_discovered:
            cmd += ["--no-discovered"]
        t0 = time.time()
        run(cmd, phase=5)
        phase_times[5] = time.time() - t0
        all_stats[5] = collect_phase5_stats(OUTPUT_DIR)
        print_phase_summary(5, all_stats[5], phase_times[5])

    # -------------------------------------------------------------------------
    # Final summary
    # -------------------------------------------------------------------------
    elapsed = time.time() - start
    print_pipeline_summary(all_stats, elapsed)

    codebook_ext = "md" if args.codebook_format == "markdown" else "csv"
    print(f"  CSV:      {OUTPUT_DIR / 'records.csv'}")
    print(f"  Codebook: {OUTPUT_DIR / f'codebook.{codebook_ext}'}")
    print(f"  Temp:     {temp_dir}")
    print()


if __name__ == "__main__":
    main()
