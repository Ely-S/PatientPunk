"""Summarize pipeline B outcomes, linked doses, and administration routes."""

from __future__ import annotations

import collections
import statistics
import sys

from study_support import (
    COMPOUNDS,
    StudyPaths,
    compound_for_treatment,
    load_pipeline_b_records,
    summarize_target_dosages,
    summarize_target_values,
)

META = {"author_hash", "source", "text_count", "schema_id", "extraction_method", "extracted_at"}


def _median_iqr(values: list[float]) -> tuple[float, float, float]:
    median = statistics.median(values)
    if len(values) == 1:
        return median, median, median
    quartiles = statistics.quantiles(values, n=4, method="inclusive")
    return median, quartiles[0], quartiles[2]


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

    dosage_summary = summarize_target_dosages(records)
    print("\nTREATMENT-LINKED MASS DOSAGES")
    for compound in COMPOUNDS:
        total = sum(dosage_summary.counts[compound].values())
        print(
            f"\n  {compound}: {total} quantitative entries from "
            f"{len(dosage_summary.authors[compound])} authors"
        )
        entry_values = dosage_summary.midpoints_mg[compound]
        author_values = [
            statistics.median(values)
            for values in dosage_summary.author_midpoints_mg[compound].values()
        ]
        if entry_values:
            entry_median, entry_q1, entry_q3 = _median_iqr(entry_values)
            author_median, author_q1, author_q3 = _median_iqr(author_values)
            print(
                f"     entry midpoint median {entry_median:g} mg "
                f"(IQR {entry_q1:g}-{entry_q3:g})"
            )
            print(
                f"     author median dose {author_median:g} mg "
                f"(IQR {author_q1:g}-{author_q3:g})"
            )
        for value, count in dosage_summary.counts[compound].most_common(12):
            print(f"     {value:24s} {count:4,}")
        excluded = dosage_summary.excluded[compound]
        if excluded:
            values = ", ".join(f"{value} ({count})" for value, count in excluded.items())
            print(f"     excluded non-mass/invalid: {values}")

    route_summary = summarize_target_values(records, "administration_route")
    print("\nTREATMENT-LINKED ADMINISTRATION ROUTES")
    for compound in COMPOUNDS:
        total = sum(route_summary.counts[compound].values())
        print(
            f"\n  {compound}: {total} explicit entries from "
            f"{len(route_summary.authors[compound])} authors"
        )
        for value, count in route_summary.counts[compound].most_common(12):
            print(f"     {value:24s} {count:4,}")


if __name__ == "__main__":
    main()
