"""Summarize pipeline B outcomes, linked doses, and administration routes."""

from __future__ import annotations

import collections
import sys

from study_support import (
    COMPOUNDS,
    StudyPaths,
    compound_for_treatment,
    load_pipeline_b_records,
    summarize_target_values,
)

META = {"author_hash", "source", "text_count", "schema_id", "extraction_method", "extracted_at"}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    records = load_pipeline_b_records(StudyPaths.from_environment().records)
    if not records:
        raise SystemExit("Pipeline B records file is empty.")

    rows = [record.model_dump() for record in records]
    fields = [key for key in rows[0] if key not in META]
    print(f"{len(rows):,} records | {len(fields)} clinical fields\n")

    fill: collections.Counter[str] = collections.Counter()
    for row in rows:
        for key in fields:
            if str(row.get(key) or "").strip():
                fill[key] += 1
    print("FIELD FILL RATES (top 12)")
    for key, value in fill.most_common(12):
        print(f"  {key:32s} {value:4,}  {100 * value / len(rows):5.1f}%")

    outcomes = {compound: collections.Counter() for compound in COMPOUNDS}
    users = {compound: set() for compound in COMPOUNDS}
    details = {compound: collections.Counter() for compound in COMPOUNDS}
    for record in records:
        for entry in record.treatment_outcome.split("|"):
            treatment, separator, remainder = entry.strip().partition(":")
            if not separator:
                continue
            outcome, detail_separator, detail = remainder.strip().partition(":")
            compound = compound_for_treatment(treatment)
            if compound is None or not outcome:
                continue
            outcomes[compound][outcome.lower()] += 1
            users[compound].add(record.author_hash)
            if detail_separator and detail.strip():
                details[compound][detail.strip().lower()] += 1

    print("\nOUTCOMES BY COMPOUND")
    for compound in COMPOUNDS:
        total = sum(outcomes[compound].values())
        if not total:
            continue
        print(f"\n  {compound}: {total} outcome entries from {len(users[compound])} authors")
        for outcome, count in outcomes[compound].most_common():
            print(f"     {outcome:16s} {count:4,}  {100 * count / total:5.1f}%")
        if details[compound]:
            values = ", ".join(value for value, _ in details[compound].most_common(6))
            print(f"     what it helped/affected: {values}")

    for field, title in (
        ("dosage", "TREATMENT-LINKED DOSAGES"),
        ("administration_route", "TREATMENT-LINKED ADMINISTRATION ROUTES"),
    ):
        summary = summarize_target_values(records, field)
        print(f"\n{title}")
        for compound in COMPOUNDS:
            total = sum(summary.counts[compound].values())
            print(
                f"\n  {compound}: {total} explicit entries from "
                f"{len(summary.authors[compound])} authors"
            )
            for value, count in summary.counts[compound].most_common(12):
                print(f"     {value:24s} {count:4,}")


if __name__ == "__main__":
    main()
