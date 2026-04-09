#!/usr/bin/env python3
"""


Accepts one or more merged_records / discovered_records JSON files.
When multiple files are provided, records with the same (author_hash, post_id)
are merged into a single row - fields from later files fill gaps left by earlier
ones, so you can combine base + discovered schema outputs without duplicating rows.

Usage:
    # Single file
    python records_to_csv.py

    # Specific input / output
    python records_to_csv.py --input output/merged_records_base.json --output output/records.csv

    # Combine base + discovered fields into one CSV
    python records_to_csv.py \\
        --input output/merged_records_base.json \\
                output/discovered_records_covidlonghaulers_v1.json

    # Include provenance columns (age__provenance, conditions__provenance, …)
    python records_to_csv.py --provenance

    # Change multi-value separator (default: " | ")
    python records_to_csv.py --sep "; "

Output:
    One row per unique (author_hash, post_id). Multi-value fields are joined
    with the separator. Null / empty fields are blank cells.
"""


import argparse
import csv
import json
import sys
from pathlib import Path


DEFAULT_INPUT = Path(__file__).parent.parent.parent / "data" / "merged_records_base.json"
DEFAULT_OUTPUT = Path(__file__).parent.parent.parent / "data" / "records.csv"

# Metadata columns always written first
META_COLUMNS = [
    "author_hash",
    "source",
    "post_id",
    "text_count",
    "schema_id",
    "extraction_method",
    "extracted_at",
]


def load_records(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        sys.exit(f"Expected a JSON array in {path}, got {type(data).__name__}")
    return data


def record_key(rec: dict) -> tuple:
    meta = rec.get("record_meta", {})
    return (
        meta.get("author_hash") or "",
        meta.get("post_id") or "",
    )


def flatten_field(field_data: dict | None, sep: str) -> tuple[str, str, str]:
    """Return (values_str, provenance, confidence) for one field."""
    if not field_data:
        return "", "", ""
    values = field_data.get("values") or []
    if isinstance(values, list):
        val_str = sep.join(
            str(item) for item in values if item is not None and str(item).strip()
        )
    else:
        val_str = str(values) if values is not None else ""
    return (
        val_str,
        field_data.get("provenance") or "",
        field_data.get("confidence") or "",
    )


def _all_fields_from_record(rec: dict) -> dict:
    """Return a flat field dict from whichever keys the record uses.

    Records from the regex extractor store fields under ``base`` and
    ``extension``.  Records from the LLM merge step use ``fields`` and
    ``discovered_fields``.  Both are supported here.
    """
    return {
        **rec.get("base", {}),
        **rec.get("extension", {}),
        **rec.get("fields", {}),
        **rec.get("discovered_fields", {}),
    }


def merge_records(base: dict, incoming: dict, sep: str) -> dict:
    """Merge fields from `incoming` into `base`, filling empty values only."""
    base_fields = base.setdefault("_fields_merged", _all_fields_from_record(base))
    for field_name, field_data in _all_fields_from_record(incoming).items():
        if field_name not in base_fields or not (base_fields[field_name].get("values")):
            base_fields[field_name] = field_data
    base["_fields_merged"] = base_fields
    return base


def collect_all_field_names(merged_rows: dict) -> list[str]:
    """Return sorted list of all field names found across all rows."""
    names: set[str] = set()
    for row in merged_rows.values():
        names.update(row.get("_fields_merged", {}).keys())
        names.update(_all_fields_from_record(row).keys())
    return sorted(names)


def build_csv_row(
    rec: dict,
    field_names: list[str],
    sep: str,
    include_provenance: bool,
) -> dict:
    meta = rec.get("record_meta", {})
    row: dict[str, str] = {
        "author_hash": meta.get("author_hash") or "",
        "source": meta.get("source") or "",
        "post_id": meta.get("post_id") or "",
        "text_count": str(meta.get("text_count") or ""),
        "schema_id": rec.get("_schema_id") or "",
        "extraction_method": rec.get("_extraction_method") or "",
        "extracted_at": rec.get("_extracted_at") or "",
    }

    all_fields = rec.get("_fields_merged") or _all_fields_from_record(rec)

    for field_name in field_names:
        val_str, provenance, confidence = flatten_field(all_fields.get(field_name), sep)
        row[field_name] = val_str
        if include_provenance:
            row[f"{field_name}__provenance"] = provenance
            row[f"{field_name}__confidence"] = confidence

    return row


def main():
    parser = argparse.ArgumentParser(
        description="Convert PatientPunk extraction records to CSV.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python records_to_csv.py
  python records_to_csv.py --input output/merged_records_base.json --output output/records.csv
  python records_to_csv.py \\
      --input output/merged_records_base.json \\
              output/discovered_records_covidlonghaulers_v1.json
  python records_to_csv.py --provenance
  python records_to_csv.py --sep "; "

Output columns:
  author_hash, source, post_id, text_count, schema_id, extraction_method,
  extracted_at, then one column per extracted field (multi-values joined
  with --sep). With --provenance: additional {field}__provenance and
  {field}__confidence columns for every field.
        """,
    )
    parser.add_argument(
        "--input", type=Path, nargs="+",
        default=[DEFAULT_INPUT],
        help="One or more JSON record files. Records with the same author+post "
             "are merged into a single row.",
    )
    parser.add_argument(
        "--output", type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output CSV path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--provenance", action="store_true",
        help="Include {field}__provenance and {field}__confidence columns.",
    )
    parser.add_argument(
        "--sep", default=" | ",
        help="Separator for multi-value fields (default: ' | ')",
    )
    args = parser.parse_args()

    # Load and merge all input files
    merged: dict[tuple, dict] = {}  # key → merged record

    for path in args.input:
        if not path.exists():
            sys.exit(f"Input file not found: {path}")
        records = load_records(path)
        print(f"  Loaded {len(records):>5} records from {path.name}")

        for rec in records:
            key = record_key(rec)
            if key not in merged:
                merged[key] = rec
            else:
                merge_records(merged[key], rec, args.sep)

    if not merged:
        sys.exit("No records found.")

    print(f"  {len(merged)} unique rows after merging\n")

    # Collect all field names
    field_names = collect_all_field_names(merged)

    # Build column list
    if args.provenance:
        field_cols = []
        for f in field_names:
            field_cols += [f, f"{f}__provenance", f"{f}__confidence"]
    else:
        field_cols = field_names

    all_columns = META_COLUMNS + field_cols

    # Write CSV
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_columns, extrasaction="ignore")
        writer.writeheader()
        for rec in merged.values():
            row = build_csv_row(rec, field_names, args.sep, args.provenance)
            writer.writerow(row)

    # Summary
    total_rows = len(merged)
    filled: dict[str, int] = {f: 0 for f in field_names}
    for rec in merged.values():
        all_fields = rec.get("_fields_merged") or _all_fields_from_record(rec)
        for field_name in field_names:
            if all_fields.get(field_name, {}).get("values"):
                filled[field_name] += 1

    print(f"Wrote {total_rows} rows x {len(all_columns)} columns to {args.output}\n")
    print(f"{'Field':<40} {'Filled':>6}  {'Coverage':>8}")
    print("-" * 58)
    for field_name in field_names:
        pct = filled[field_name] / total_rows if total_rows else 0
        print(f"  {field_name:<38} {filled[field_name]:>6}  {pct:>7.0%}")


if __name__ == "__main__":
    main()
