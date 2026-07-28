#!/usr/bin/env python3
"""


Accepts one or more records / discovered_records JSON files.
When multiple files are provided, records with the same (author_hash, post_id)
are merged into a single row - fields from later files fill gaps left by earlier
ones, so you can combine base + discovered schema outputs without duplicating rows.

Usage:
    # Single file
    python -m patientpunk.export_csv

    # Specific input / output
    python -m patientpunk.export_csv --input output/records_base.json --output output/records.csv

    # Combine base + discovered fields into one CSV
    python -m patientpunk.export_csv \\
        --input output/records_base.json \\
                output/discovered_records_covidlonghaulers_v1.json

    # Include confidence columns (age__confidence, conditions__confidence, …)
    python -m patientpunk.export_csv --confidence

    # Change multi-value separator (default: " | ")
    python -m patientpunk.export_csv --sep "; "

Output:
    One row per unique (author_hash, post_id). Multi-value fields are joined
    with the separator. Null / empty fields are blank cells.
"""


import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from .phase import PhaseResult


_VE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = _VE_ROOT / "output" / "temp" / "records_base.json"
DEFAULT_OUTPUT = _VE_ROOT / "output" / "records.csv"

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
        raise ValueError(f"Expected a JSON array in {path}, got {type(data).__name__}")
    return data


def record_key(rec: dict) -> tuple:
    meta = rec.get("record_meta", {})
    return (
        meta.get("author_hash") or "",
        meta.get("post_id") or "",
    )


def flatten_field(field_data: dict | None, sep: str) -> tuple[str, str]:
    """Return (values_str, confidence) for one field."""
    if not field_data:
        return "", ""
    values = field_data.get("values") or []
    if isinstance(values, list):
        val_str = sep.join(
            str(item) for item in values if item is not None and str(item).strip()
        )
    else:
        val_str = str(values) if values is not None else ""
    return val_str, field_data.get("confidence") or ""


def _normalize_entry(value) -> dict:
    """Coerce one field entry to the ``{"values": ...}`` shape."""
    if isinstance(value, dict):
        return value
    return {"values": value, "confidence": None}


def _all_fields_from_record(rec: dict) -> dict:
    """Return a flat field dict from whichever keys the record uses.

    Base extraction stores fields under ``fields``; discovery uses
    ``discovered_fields``.  Every entry is normalised to a dict so callers
    can assume one shape.
    """
    merged = {
        **(rec.get("fields") or {}),
        **(rec.get("discovered_fields") or {}),
    }
    return {name: _normalize_entry(entry) for name, entry in merged.items()}


def merge_records(base: dict, incoming: dict) -> dict:
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
    include_confidence: bool,
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
        val_str, confidence = flatten_field(all_fields.get(field_name), sep)
        row[field_name] = val_str
        if include_confidence:
            row[f"{field_name}__confidence"] = confidence

    return row


def run_export_csv(
    *,
    input_files: list[Path],
    output_path: Path,
    sep: str = " | ",
    include_confidence: bool = False,
) -> PhaseResult:
    """Flatten one or more JSON record files into a CSV.

    Raises FileNotFoundError / ValueError on bad inputs.
    """
    if not input_files:
        raise ValueError("run_export_csv requires at least one input file.")

    merged: dict[tuple, dict] = {}

    for path in input_files:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")
        records = load_records(path)
        print(f"  Loaded {len(records):>5} records from {path.name}")

        for rec in records:
            key = record_key(rec)
            if key not in merged:
                merged[key] = rec
            else:
                merge_records(merged[key], rec)

    if not merged:
        raise ValueError("No records found.")

    print(f"  {len(merged)} unique rows after merging\n")

    field_names = collect_all_field_names(merged)

    if include_confidence:
        field_cols: list[str] = []
        for f in field_names:
            field_cols += [f, f"{f}__confidence"]
    else:
        field_cols = field_names

    all_columns = META_COLUMNS + field_cols

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_columns, extrasaction="ignore")
        writer.writeheader()
        for rec in merged.values():
            row = build_csv_row(rec, field_names, sep, include_confidence)
            writer.writerow(row)

    total_rows = len(merged)
    filled: dict[str, int] = {f: 0 for f in field_names}
    for rec in merged.values():
        all_fields = rec.get("_fields_merged") or _all_fields_from_record(rec)
        for field_name in field_names:
            if all_fields.get(field_name, {}).get("values"):
                filled[field_name] += 1

    print(f"Wrote {total_rows} rows x {len(all_columns)} columns to {output_path}\n")
    print(f"{'Field':<40} {'Filled':>6}  {'Coverage':>8}")
    print("-" * 58)
    for field_name in field_names:
        pct = filled[field_name] / total_rows if total_rows else 0
        print(f"  {field_name:<38} {filled[field_name]:>6}  {pct:>7.0%}")

    stats: dict[str, Any] = {
        "rows": total_rows,
        "columns": len(all_columns),
        "fields": len(field_names),
    }
    return PhaseResult(artifacts={"csv": output_path}, stats=stats)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Convert PatientPunk extraction records to CSV.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m patientpunk.export_csv
  python -m patientpunk.export_csv --input output/records_base.json --output output/records.csv
  python -m patientpunk.export_csv --confidence
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
        "--confidence", action="store_true",
        help="Include {field}__confidence columns.",
    )
    parser.add_argument(
        "--sep", default=" | ",
        help="Separator for multi-value fields (default: ' | ')",
    )
    args = parser.parse_args(argv)

    try:
        run_export_csv(
            input_files=args.input,
            output_path=args.output,
            sep=args.sep,
            include_confidence=args.confidence,
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
