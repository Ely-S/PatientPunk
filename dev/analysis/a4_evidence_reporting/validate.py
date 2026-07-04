"""Validate generated A4 report packages."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from dev.analysis.a4_evidence_reporting.common import file_sha256, read_csv, read_json, write_json


REQUIRED_REPORT_FILES = [
    "report_manifest.json",
    "evidence_mart.sqlite",
    "finding_cards.jsonl",
    "finding_cards.csv",
    "evidence_packet.json",
    "tables/claim_counts_by_label.csv",
    "tables/claim_counts_by_type.csv",
    "tables/monthly_claim_counts.csv",
    "tables/reportability_by_label.csv",
    "tables/source_denominators.csv",
    "quotes/quote_bank_private.csv",
    "quotes/quote_review_template.csv",
    "report.md",
    "methods.md",
    "limitations.md",
    "provenance.md",
]

_NUM_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(%?)")


def validate_report_package(report_dir: Path, *, output_path: Path | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    report_dir = report_dir.resolve()
    for rel in REQUIRED_REPORT_FILES:
        if not (report_dir / rel).exists():
            errors.append(f"required A4 report file missing: {rel}")

    if errors:
        result = _result(report_dir, errors, warnings, {})
        _maybe_write(output_path, result)
        return result

    manifest = read_json(report_dir / "report_manifest.json")
    packet = read_json(report_dir / "evidence_packet.json")
    findings = read_csv(report_dir / "finding_cards.csv")
    quotes = read_csv(report_dir / "quotes" / "quote_bank_private.csv")
    denominators = set(packet.get("denominators", {}).keys())
    claim_ids = _claim_ids_from_mart(report_dir / "evidence_mart.sqlite")

    for rel, expected in (manifest.get("report_file_hashes") or {}).items():
        path = report_dir / rel
        if not path.exists():
            errors.append(f"manifest-listed report file missing: {rel}")
            continue
        actual = file_sha256(path)
        if expected and actual != expected:
            errors.append(f"A4 report hash mismatch for {rel}: expected {expected}, got {actual}")

    for finding in findings:
        denominator_name = finding.get("denominator_name", "")
        if denominator_name and denominator_name not in denominators:
            errors.append(f"finding uses unknown denominator {denominator_name}: {finding.get('finding_id')}")
        for claim_id in _json_list(finding.get("source_claim_ids_json")):
            if claim_id and claim_id not in claim_ids:
                errors.append(f"finding references unknown claim_id {claim_id}: {finding.get('finding_id')}")

    for quote in quotes:
        claim_id = quote.get("claim_id", "")
        if claim_id and claim_id not in claim_ids:
            errors.append(f"quote references unknown claim_id {claim_id}: {quote.get('quote_id')}")

    if manifest.get("mode") == "public_summary":
        unsafe = [row.get("quote_id", "") for row in quotes if row.get("public_allowed") != "1"]
        if unsafe:
            errors.append(f"public_summary contains {len(unsafe)} quote candidates not approved for public use")

    orphan_numbers = _orphan_numbers(report_dir / "report.md", packet)
    for token in orphan_numbers:
        errors.append(f"report.md contains orphan number not present in evidence_packet.json: {token}")

    details = {
        "finding_count": len(findings),
        "quote_count": len(quotes),
        "mart_counts": _mart_counts(report_dir / "evidence_mart.sqlite"),
        "orphan_numbers": orphan_numbers,
    }
    result = _result(report_dir, errors, warnings, details)
    _maybe_write(output_path, result)
    return result


def _claim_ids_from_mart(path: Path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {row[0] for row in conn.execute("SELECT claim_id FROM claims WHERE claim_id IS NOT NULL AND claim_id != ''")}
    finally:
        conn.close()


def _mart_counts(path: Path) -> dict[str, int]:
    conn = sqlite3.connect(path)
    try:
        out = {}
        for table in ["comments", "claims", "quote_bank", "finding_cards", "denominators"]:
            try:
                out[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.OperationalError:
                out[table] = -1
        return out
    finally:
        conn.close()


def _orphan_numbers(report_path: Path, packet: dict[str, Any]) -> list[str]:
    packet_numbers = _numbers(json.dumps(packet, sort_keys=True, ensure_ascii=False))
    report_text = _strip_inline_code(report_path.read_text(encoding="utf-8"))
    out: list[str] = []
    for token in sorted(_numbers(report_text)):
        plain = token.rstrip("%")
        if token not in packet_numbers and plain not in packet_numbers and f"{plain}%" not in packet_numbers:
            out.append(token)
    return out


def _numbers(text: str) -> set[str]:
    out = set()
    for digits, pct in _NUM_RE.findall(text):
        token = digits.rstrip("0").rstrip(".") if "." in digits else digits
        out.add(token)
        if pct:
            out.add(token + "%")
    return out


def _strip_inline_code(text: str) -> str:
    return re.sub(r"`[^`]*`", " ", text)


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _result(report_dir: Path, errors: list[str], warnings: list[str], details: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": not errors,
        "report_dir": str(report_dir),
        "errors": errors,
        "warnings": warnings,
        "details": details,
    }


def _maybe_write(path: Path | None, result: dict[str, Any]) -> None:
    if path is not None:
        write_json(path, result)
