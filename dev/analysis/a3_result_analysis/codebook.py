"""Codebook generation for A3 outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dev.analysis.a3_result_analysis.common import write_csv


DESCRIPTIONS = {
    "run_id": "A2 run identifier.",
    "source_line": "Line number in the original source JSONL export.",
    "comment_id": "Bare Reddit comment ID.",
    "claim_id": "Deterministic A2 claim identifier.",
    "claim_hash": "Stable hash of claim content fields.",
    "claim_type": "A1 structured claim type.",
    "raw_text": "Plain-language claim emitted by the model.",
    "normalized_label": "Raw model normalized label.",
    "normalized_label_clean": "A3 deterministic cleaned label.",
    "normalized_label_canonical": "A3 canonical label for analysis.",
    "analysis_bucket": "Optional A3 coarse analysis bucket.",
    "normalization_review_status": "Review state of the canonical label.",
    "evidence_quote": "Direct quote from the target comment supporting the claim.",
    "evidence_source": "Where the evidence quote came from.",
    "reportability_label": "A3/A4 conservative reportability label.",
}


TEXT_COLUMNS = {"raw_text", "evidence_quote", "ambiguity_notes", "notes"}


def generate_codebook(
    *,
    tables: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for table, table_rows in tables.items():
        columns = _columns(table_rows)
        total = len(table_rows)
        for column in columns:
            filled = sum(1 for row in table_rows if str(row.get(column, "")).strip())
            examples = []
            for row in table_rows:
                value = str(row.get(column, "")).strip()
                if value and value not in examples:
                    examples.append(value[:120])
                if len(examples) >= 5:
                    break
            rows.append(
                {
                    "table": table,
                    "column": column,
                    "description": DESCRIPTIONS.get(column, ""),
                    "type": "text" if column in TEXT_COLUMNS else "string",
                    "allowed_values": _allowed_values(column),
                    "source": _source_for_column(column),
                    "nullable": "yes" if filled < total else "no",
                    "contains_text": "yes" if column in TEXT_COLUMNS else "no",
                    "derived": "yes" if _is_derived(column) else "no",
                    "coverage_pct": round(filled / total, 3) if total else 0.0,
                    "example_values": " | ".join(examples),
                }
            )
    return rows


def write_codebook_outputs(output_dir: Path, tables: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows = generate_codebook(tables=tables)
    columns = [
        "table",
        "column",
        "description",
        "type",
        "allowed_values",
        "source",
        "nullable",
        "contains_text",
        "derived",
        "coverage_pct",
        "example_values",
    ]
    write_csv(output_dir / "codebook.csv", rows, columns)
    (output_dir / "codebook.md").write_text(_codebook_md(rows), encoding="utf-8")
    return rows


def _columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return columns


def _source_for_column(column: str) -> str:
    if column.startswith("normalization_") or column in {"normalized_label_clean", "analysis_bucket"}:
        return "a3"
    if column in {"reportability_label", "reason", "gate_decision"}:
        return "a3_reportability"
    return "a2"


def _is_derived(column: str) -> bool:
    return _source_for_column(column).startswith("a3")


def _allowed_values(column: str) -> str:
    values = {
        "claim_type": "symptom, diagnosis, medication_or_treatment, test_or_measurement, timeline_or_course, functional_impact, trigger_or_exacerbating_factor, recovery_or_improvement, healthcare_access, other_health_experience",
        "assertion": "present, absent, uncertain, question, hypothetical",
        "experiencer": "self, other_person, general, unclear",
        "confidence": "high, medium, low",
        "normalization_review_status": "unreviewed, accepted, needs_review, deprecated",
        "reportability_label": "not_reportable, exploratory, weak_signal, suggestive_signal, stable_descriptive_pattern",
    }
    return values.get(column, "")


def _codebook_md(rows: list[dict[str, Any]]) -> str:
    lines = ["# A3 Codebook", ""]
    by_table: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_table.setdefault(row["table"], []).append(row)
    for table, table_rows in by_table.items():
        lines.append(f"## {table}")
        lines.append("")
        lines.append("| Column | Description | Source | Derived | Coverage |")
        lines.append("|---|---|---|---|---|")
        for row in table_rows:
            lines.append(
                f"| `{row['column']}` | {row['description']} | {row['source']} | "
                f"{row['derived']} | {row['coverage_pct']} |"
            )
        lines.append("")
    return "\n".join(lines)

