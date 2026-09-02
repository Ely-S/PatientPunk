#!/usr/bin/env python3
"""


Reads one base schema + one extension schema to collect field descriptions,
confidence ratings, and ICD-10 codes. Optionally reads the
output CSV to add real coverage stats and example values.

Usage:
    # Minimal (schema only):
    python -m patientpunk.codebook --schema schemas/covidlonghaulers_schema.json

    # Full (schema + CSV for coverage/examples):
    python -m patientpunk.codebook \\
        --schema schemas/covidlonghaulers_schema.json \\
        --csv    ../output/records.csv

    # Markdown output instead of CSV:
    python -m patientpunk.codebook \\
        --schema schemas/covidlonghaulers_schema.json \\
        --csv    ../output/records.csv \\
        --format markdown

    # Custom output path:
    python -m patientpunk.codebook \\
        --schema schemas/covidlonghaulers_schema.json \\
        --csv    ../output/records.csv \\
        --output ../output/codebook.csv

Output columns:
    field, source, description, confidence, icd10, frequency_hint,
    research_value, discovered_at,
    n_filled, coverage_pct, example_values
"""


import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

from .phase import PhaseResult


_VE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_SCHEMA = _VE_ROOT / "schemas" / "base_schema.json"
DEFAULT_OUTPUT_CSV  = _VE_ROOT / "output" / "codebook.csv"
DEFAULT_OUTPUT_MD   = _VE_ROOT / "output" / "codebook.md"

# Meta columns written by patientpunk.export_csv -- skip them in the codebook
META_COLUMNS = {"author_hash", "source", "post_id", "text_count",
                "subreddits", "schema_id", "extraction_method", "extracted_at"}


# ---------------------------------------------------------------------------
# Schema loading helpers
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _ext_row(fname: str, fdata: dict) -> dict:
    """Build one codebook registry row for an extension / discovered field."""
    is_discovered = fdata.get("source") == "llm_discovered"
    return {
        "field":          fname,
        "source":         "llm_discovered" if is_discovered else "extension",
        "description":    fdata.get("description", ""),
        "confidence":     fdata.get("confidence", ""),
        "icd10":          fdata.get("icd10", ""),
        "frequency_hint": fdata.get("frequency_hint", ""),
        "research_value": fdata.get("research_value", ""),
        "discovered_at":  fdata.get("_discovered_at", ""),
    }


def build_field_registry(base_schema: dict, ext_schema: dict,
                         discovered_schema: dict | None = None) -> list[dict]:
    """
    Return an ordered list of field-info dicts covering all extractable fields:
      1. Base fields (always active)
      2. Base-optional fields activated by the extension schema
      3. Extension fields (hand-written + promoted)
      4. LLM-discovered extension fields from the run's discovered schema
         (those not already present in the curated schema)
    """
    active_base_optional = set(ext_schema.get("include_base_fields", []))
    registry: list[dict] = []

    # --- Base fields ---
    for fname, fdata in base_schema.get("base_fields", {}).items():
        registry.append({
            "field":          fname,
            "source":         "base",
            "description":    fdata.get("description", ""),
            "confidence":     fdata.get("confidence", ""),
            "icd10":          fdata.get("icd10", ""),
            "frequency_hint": "",
            "research_value": "",
            "discovered_at":  "",
        })

    # --- Base-optional fields activated for this schema ---
    for fname, fdata in base_schema.get("base_optional_fields", {}).items():
        if fname == "_description":
            continue
        if fname in active_base_optional:
            registry.append({
                "field":          fname,
                "source":         "base_optional",
                "description":    fdata.get("description", ""),
                "confidence":     fdata.get("confidence", ""),
                "icd10":          fdata.get("icd10", ""),
                "frequency_hint": "",
                "research_value": "",
                "discovered_at":  "",
            })

    # --- Extension fields (hand-written + promoted) ---
    seen_ext = set()
    for fname, fdata in ext_schema.get("extension_fields", {}).items():
        # An extension may intentionally override a base field's instructions.
        # Keep one registry row so coverage statistics are consumed exactly once.
        registry = [row for row in registry if row["field"] != fname]
        registry.append(_ext_row(fname, fdata))
        seen_ext.add(fname)

    # --- Discovered extension fields not already in the curated schema ---
    # The run's discovered schema lives in temp/ and is never merged into the
    # curated schema unless promoted, so without this Phase 5 would document zero
    # discovered fields even though records.csv already contains their columns.
    if discovered_schema:
        for fname, fdata in discovered_schema.get("extension_fields", {}).items():
            if fname in seen_ext:
                continue
            registry.append(_ext_row(fname, fdata))

    return registry


# ---------------------------------------------------------------------------
# CSV stats helpers
# ---------------------------------------------------------------------------

def load_csv_stats(csv_path: Path, field_names: list[str],
                   n_examples: int = 5, sep: str = " | ") -> dict[str, dict]:
    """
    Read the records CSV and return per-field stats:
        {field: {"n_filled": int, "n_total": int, "examples": [str, ...]}}
    """
    stats: dict[str, dict] = {
        f: {"n_filled": 0, "n_total": 0, "seen_values": set()} for f in field_names
    }

    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        csv_cols = set(reader.fieldnames or [])
        rows = list(reader)

    n_total = len(rows)
    for field in field_names:
        if field not in csv_cols:
            stats[field]["n_total"] = n_total
            continue
        stats[field]["n_total"] = n_total
        for row in rows:
            cell = (row.get(field) or "").strip()
            if cell:
                stats[field]["n_filled"] += 1
                # Split multi-values and collect unique ones
                for v in cell.split(sep):
                    v = v.strip()
                    if v:
                        stats[field]["seen_values"].add(v)

    # Convert seen_values -> sorted example list (capped at n_examples)
    for field in field_names:
        vals = sorted(stats[field].pop("seen_values"))
        stats[field]["examples"] = vals[:n_examples]

    return stats


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def pct_str(n: int, total: int) -> str:
    if total == 0:
        return ""
    return f"{n / total:.0%}"


def write_codebook_csv(rows: list[dict], output: Path) -> None:
    if not rows:
        sys.exit("No fields to write.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_codebook_md(rows: list[dict], output: Path, has_csv: bool) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)

    # Group by source for section headers
    source_order = ["base", "base_optional", "extension", "llm_discovered"]
    source_label = {
        "base":           "Base Fields (always active)",
        "base_optional":  "Base-Optional Fields (activated for this schema)",
        "extension":      "Extension Fields (hand-written)",
        "llm_discovered": "LLM-Discovered Extension Fields",
    }

    by_source: dict[str, list] = defaultdict(list)
    for row in rows:
        by_source[row["source"]].append(row)

    lines: list[str] = ["# PatientPunk Codebook\n"]

    for src in source_order:
        group = by_source.get(src)
        if not group:
            continue
        lines.append(f"\n## {source_label.get(src, src)}\n")

        # Table header
        if has_csv:
            lines.append("| Field | Description | Confidence | ICD-10 | Coverage | Examples |")
            lines.append("|---|---|---|---|---|---|")
        else:
            lines.append("| Field | Description | Confidence | ICD-10 |")
            lines.append("|---|---|---|---|")

        for row in group:
            field        = row["field"]
            desc         = (row["description"] or "").replace("|", "/")
            conf         = row["confidence"] or ""
            icd          = row["icd10"] or ""
            coverage     = row.get("coverage_pct") or ""
            examples     = (row.get("example_values") or "").replace("|", "/")

            if has_csv:
                lines.append(f"| `{field}` | {desc} | {conf} | {icd} | {coverage} | {examples} |")
            else:
                lines.append(f"| `{field}` | {desc} | {conf} | {icd} |")

    # Footnotes for llm_discovered
    discovered = by_source.get("llm_discovered", [])
    if discovered:
        lines.append("\n---\n")
        lines.append("### LLM-Discovered Field Details\n")
        for row in discovered:
            lines.append(f"**`{row['field']}`** - discovered {row.get('discovered_at','')[:10]}")
            if row.get("frequency_hint"):
                lines.append(f"  - Frequency hint: {row['frequency_hint']}")
            if row.get("research_value"):
                lines.append(f"  - Research value: {row['research_value']}")
            lines.append("")

    with open(output, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Library entrypoint
# ---------------------------------------------------------------------------

def run_codebook(
    *,
    schema_path: Path,
    base_schema_path: Path | None = None,
    records_csv: Path | None = None,
    output_path: Path | None = None,
    fmt: str = "csv",
    max_examples: int = 5,
    sep: str = " | ",
    include_discovered: bool = True,
    discovered_schema_path: Path | None = None,
) -> PhaseResult:
    """Generate a codebook / data dictionary for PatientPunk CSV output."""
    schema_path = Path(schema_path)
    base_schema_path = Path(base_schema_path) if base_schema_path else DEFAULT_BASE_SCHEMA

    if output_path is None:
        output_path = DEFAULT_OUTPUT_MD if fmt == "markdown" else DEFAULT_OUTPUT_CSV
    else:
        output_path = Path(output_path)

    if not base_schema_path.exists():
        raise FileNotFoundError(f"Base schema not found: {base_schema_path}")
    if not schema_path.exists():
        raise FileNotFoundError(f"Extension schema not found: {schema_path}")

    base_schema = load_json(base_schema_path)
    ext_schema = load_json(schema_path)

    discovered_schema = None
    if discovered_schema_path:
        discovered_schema_path = Path(discovered_schema_path)
        if discovered_schema_path.exists():
            discovered_schema = load_json(discovered_schema_path)
            if not isinstance(discovered_schema, dict):
                print(f"  ! discovered schema not valid JSON, ignoring: {discovered_schema_path}")
                discovered_schema = None
        else:
            print(f"  ! discovered schema not found, ignoring: {discovered_schema_path}")

    schema_id = ext_schema.get("schema_id", schema_path.stem)
    print(f"Schema: {schema_id}")
    print(f"Base schema: {base_schema_path.name}\n")

    registry = build_field_registry(base_schema, ext_schema, discovered_schema)
    if not include_discovered:
        n_hidden = sum(1 for r in registry if r["source"] == "llm_discovered")
        registry = [r for r in registry if r["source"] != "llm_discovered"]
        print(f"  (--no-discovered: hiding {n_hidden} llm_discovered fields)")
    field_names = [r["field"] for r in registry]
    print(f"  {len(registry)} fields found")
    print(f"    base:           {sum(1 for r in registry if r['source'] == 'base')}")
    print(f"    base_optional:  {sum(1 for r in registry if r['source'] == 'base_optional')}")
    print(f"    extension:      {sum(1 for r in registry if r['source'] == 'extension')}")
    print(f"    llm_discovered: {sum(1 for r in registry if r['source'] == 'llm_discovered')}")

    has_csv = False
    csv_stats: dict[str, dict] = {}
    if records_csv:
        records_csv = Path(records_csv)
        if not records_csv.exists():
            raise FileNotFoundError(f"CSV file not found: {records_csv}")
        csv_stats = load_csv_stats(records_csv, field_names,
                                   n_examples=max_examples, sep=sep)
        n_total = next(iter(csv_stats.values()), {}).get("n_total", 0) if csv_stats else 0
        has_csv = True
        print(f"\n  Loaded CSV: {records_csv.name} ({n_total} rows)")

    output_rows: list[dict] = []
    for entry in registry:
        fname = entry["field"]
        row = {
            "field":          fname,
            "source":         entry["source"],
            "description":    entry["description"],
            "confidence":     entry["confidence"],
            "icd10":          entry["icd10"],
            "frequency_hint": entry["frequency_hint"],
            "research_value": entry["research_value"],
            "discovered_at":  entry["discovered_at"],
        }
        if has_csv:
            stats = csv_stats.get(fname, {})
            n_filled = stats.get("n_filled", 0)
            n_total = stats.get("n_total", 0)
            row["n_filled"] = n_filled
            row["n_total"] = n_total
            row["coverage_pct"] = pct_str(n_filled, n_total)
            row["example_values"] = sep.join(stats.get("examples", []))
        output_rows.append(row)

    if fmt == "markdown":
        write_codebook_md(output_rows, output_path, has_csv)
    else:
        write_codebook_csv(output_rows, output_path)

    print(f"\nWrote codebook ({fmt}) -> {output_path}")

    if has_csv:
        print(f"\n{'Field':<40} {'Src':<14} {'Coverage':>8}  {'Conf':<8}")
        print("-" * 74)
        for row in output_rows:
            print(
                f"  {row['field']:<38} {row['source']:<14} "
                f"{row.get('coverage_pct',''):>7}  {row['confidence']:<8}"
            )

    return PhaseResult(
        artifacts={"codebook": output_path},
        stats={"fields": len(output_rows)},
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Generate a codebook / data dictionary for PatientPunk CSV output.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m patientpunk.codebook --schema schemas/covidlonghaulers_schema.json
  python -m patientpunk.codebook --schema schemas/covidlonghaulers_schema.json --csv ../output/records.csv
        """,
    )
    parser.add_argument(
        "--schema", type=Path, required=True,
        help="Extension schema JSON (e.g. schemas/covidlonghaulers_schema.json)",
    )
    parser.add_argument(
        "--base-schema", type=Path, default=DEFAULT_BASE_SCHEMA,
        help=f"Base schema JSON (default: {DEFAULT_BASE_SCHEMA})",
    )
    parser.add_argument(
        "--csv", type=Path, default=None,
        help="Records CSV produced by export_csv. "
             "If provided, adds coverage % and example values to each field.",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Output path (default: ../output/codebook.csv or .md depending on --format)",
    )
    parser.add_argument(
        "--format", choices=["csv", "markdown"], default="csv",
        help="Output format: csv (default) or markdown",
    )
    parser.add_argument(
        "--examples", type=int, default=5,
        help="Max example values to show per field (default: 5)",
    )
    parser.add_argument(
        "--sep", default=" | ",
        help="Multi-value separator used in the records CSV (default: ' | ')",
    )
    parser.add_argument(
        "--no-discovered", action="store_true",
        help="Exclude llm_discovered fields from the codebook output.",
    )
    parser.add_argument(
        "--discovered-schema", type=Path, default=None,
        help="Discovered-schema JSON whose extension_fields are appended.",
    )
    args = parser.parse_args(argv)

    try:
        run_codebook(
            schema_path=args.schema,
            base_schema_path=args.base_schema,
            records_csv=args.csv,
            output_path=args.output,
            fmt=args.format,
            max_examples=args.examples,
            sep=args.sep,
            include_discovered=not args.no_discovered,
            discovered_schema_path=args.discovered_schema,
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
