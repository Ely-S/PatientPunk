"""A4 reportability and confidence helpers."""

from __future__ import annotations


CONFIDENCE_RANK = {
    "not_reportable": 0,
    "exploratory": 1,
    "weak_signal": 2,
    "suggestive_signal": 3,
    "stable_descriptive_pattern": 4,
}


def reportability_lookup(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    return {(row.get("unit", ""), row.get("key", "")): row for row in rows}


def run_reportability(rows: list[dict[str, str]], run_id: str) -> dict[str, str]:
    lookup = reportability_lookup(rows)
    return lookup.get(("run", run_id)) or next((row for row in rows if row.get("unit") == "run"), {})


def max_reportability_label(rows: list[dict[str, str]]) -> str:
    labels = [row.get("reportability_label", "not_reportable") for row in rows]
    if not labels:
        return "not_reportable"
    return min(labels, key=lambda label: CONFIDENCE_RANK.get(label, 0))


def cap_label(label: str, cap: str) -> str:
    if CONFIDENCE_RANK.get(label, 0) <= CONFIDENCE_RANK.get(cap, 0):
        return label
    return cap
