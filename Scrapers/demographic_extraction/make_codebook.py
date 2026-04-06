#!/usr/bin/env python3
"""Generate a codebook / data dictionary for PatientPunk CSV output.

Reads one base schema + one extension schema to collect field descriptions,
confidence ratings, ICD-10 codes, and pattern counts. Optionally reads the
output CSV to add real coverage stats and example values.

Usage:
    # Minimal (schema only):
    python make_codebook.py --schema schemas/covidlonghaulers_schema.json

    # Full (schema + CSV for coverage/examples):
    python make_codebook.py \\
        --schema schemas/covidlonghaulers_schema.json \\
        --csv    ../output/records.csv

    # Markdown output instead of CSV:
    python make_codebook.py \\
        --schema schemas/covidlonghaulers_schema.json \\
        --csv    ../output/records.csv \\
        --format markdown

    # Custom output path:
    python make_codebook.py \\
        --schema schemas/covidlonghaulers_schema.json \\
        --csv    ../output/records.csv \\
        --output ../output/codebook.csv

Output columns:
    field, source, description, confidence, icd10, frequency_hint,
    research_value, n_patterns, discovered_at,
    n_filled, coverage_pct, example_values
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path


DEFAULT_BASE_SCHEMA = Path(__file__).parent / "schemas" / "base_schema.json"
DEFAULT_OUTPUT_CSV  = Path(__file__).parent.parent / "output" / "codebook.csv"
DEFAULT_OUTPUT_MD   = Path(__file__).parent.parent / "output" / "codebook.md"

# Meta columns written by records_to_csv.py -- skip them in the codebook
META_COLUMNS = {"author_hash", "source", "post_id", "text_count",
                "schema_id", "extraction_method", "extracted_at"}


# ---------------------------------------------------------------------------
# Schema loading helpers
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_field_registry(base_schema: dict, ext_schema: dict) -> list[dict]:
    """
    Return an ordered list of field-info dicts covering all extractable fields:
      1. Base fields (always active)
      2. Base-optional fields activated by the extension schema
      3. Extension fields (hand-written)
      4. LLM-discovered extension fields
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
            "n_patterns":     "",   # base patterns live in extract_biomedical.py, not the schema JSON
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
                "n_patterns":     "",
                "discovered_at":  "",
            })

    # --- Extension fields ---
    for fname, fdata in ext_schema.get("extension_fields", {}).items():
        is_discovered = fdata.get("source") == "llm_discovered"
        registry.append({
            "field":          fname,
            "source":         "llm_discovered" if is_discovered else "extension",
            "description":    fdata.get("description", ""),
            "confidence":     fdata.get("confidence", ""),
            "icd10":          fdata.get("icd10", ""),
            "frequency_hint": fdata.get("frequency_hint", ""),
            "research_value": fdata.get("research_value", ""),
            "n_patterns":     len(fdata.get("patterns", [])),
            "discovered_at":  fdata.get("_discovered_at", ""),
        })

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
            lines.append("| Field | Description | Confidence | ICD-10 | Patterns |")
            lines.append("|---|---|---|---|---|")

        for row in group:
            field        = row["field"]
            desc         = (row["description"] or "").replace("|", "/")
            conf         = row["confidence"] or ""
            icd          = row["icd10"] or ""
            n_pat        = str(row.get("n_patterns") or "")
            coverage     = row.get("coverage_pct") or ""
            examples     = (row.get("example_values") or "").replace("|", "/")

            if has_csv:
                lines.append(f"| `{field}` | {desc} | {conf} | {icd} | {coverage} | {examples} |")
            else:
                lines.append(f"| `{field}` | {desc} | {conf} | {icd} | {n_pat} |")

    # Footnotes for llm_discovered
    discovered = by_source.get("llm_discovered", [])
    if discovered:
        lines.append("\n---\n")
        lines.append("### LLM-Discovered Field Details\n")
        for row in discovered:
            lines.append(f"**`{row['field']}`** — discovered {row.get('discovered_at','')[:10]}")
            if row.get("frequency_hint"):
                lines.append(f"  - Frequency hint: {row['frequency_hint']}")
            if row.get("research_value"):
                lines.append(f"  - Research value: {row['research_value']}")
            lines.append("")

    with open(output, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate a codebook / data dictionary for PatientPunk CSV output.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python make_codebook.py --schema schemas/covidlonghaulers_schema.json
  python make_codebook.py \\
      --schema schemas/covidlonghaulers_schema.json \\
      --csv    ../output/records.csv
  python make_codebook.py \\
      --schema schemas/covidlonghaulers_schema.json \\
      --csv    ../output/records.csv \\
      --format markdown
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
        help="Records CSV produced by records_to_csv.py. "
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
    args = parser.parse_args()

    # Resolve output path
    if args.output is None:
        args.output = DEFAULT_OUTPUT_MD if args.format == "markdown" else DEFAULT_OUTPUT_CSV

    # Load schemas
    if not args.base_schema.exists():
        sys.exit(f"Base schema not found: {args.base_schema}")
    if not args.schema.exists():
        sys.exit(f"Extension schema not found: {args.schema}")

    base_schema = load_json(args.base_schema)
    ext_schema  = load_json(args.schema)

    schema_id = ext_schema.get("schema_id", args.schema.stem)
    print(f"Schema: {schema_id}")
    print(f"Base schema: {args.base_schema.name}\n")

    # Build registry
    registry = build_field_registry(base_schema, ext_schema)
    if args.no_discovered:
        n_hidden = sum(1 for r in registry if r["source"] == "llm_discovered")
        registry = [r for r in registry if r["source"] != "llm_discovered"]
        print(f"  (--no-discovered: hiding {n_hidden} llm_discovered fields)")
    field_names = [r["field"] for r in registry]
    print(f"  {len(registry)} fields found")
    print(f"    base:           {sum(1 for r in registry if r['source'] == 'base')}")
    print(f"    base_optional:  {sum(1 for r in registry if r['source'] == 'base_optional')}")
    print(f"    extension:      {sum(1 for r in registry if r['source'] == 'extension')}")
    print(f"    llm_discovered: {sum(1 for r in registry if r['source'] == 'llm_discovered')}")

    # Optionally load CSV stats
    has_csv = False
    csv_stats: dict[str, dict] = {}
    if args.csv:
        if not args.csv.exists():
            sys.exit(f"CSV file not found: {args.csv}")
        csv_stats = load_csv_stats(args.csv, field_names,
                                   n_examples=args.examples, sep=args.sep)
        n_total = next(iter(csv_stats.values()), {}).get("n_total", 0) if csv_stats else 0
        has_csv = True
        print(f"\n  Loaded CSV: {args.csv.name} ({n_total} rows)")

    # Build output rows
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
            "n_patterns":     entry["n_patterns"],
            "discovered_at":  entry["discovered_at"],
        }
        if has_csv:
            stats = csv_stats.get(fname, {})
            n_filled = stats.get("n_filled", 0)
            n_total  = stats.get("n_total", 0)
            row["n_filled"]       = n_filled
            row["n_total"]        = n_total
            row["coverage_pct"]   = pct_str(n_filled, n_total)
            row["example_values"] = args.sep.join(stats.get("examples", []))
        output_rows.append(row)

    # Write output
    if args.format == "markdown":
        write_codebook_md(output_rows, args.output, has_csv)
    else:
        write_codebook_csv(output_rows, args.output)

    print(f"\nWrote codebook ({args.format}) -> {args.output}")

    # Print a quick summary table
    if has_csv:
        print(f"\n{'Field':<40} {'Src':<14} {'Coverage':>8}  {'Conf':<8}")
        print("-" * 74)
        for row in output_rows:
            print(
                f"  {row['field']:<38} {row['source']:<14} "
                f"{row.get('coverage_pct',''):>7}  {row['confidence']:<8}"
            )


if __name__ == "__main__":
    main()
