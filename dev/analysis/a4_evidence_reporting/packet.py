"""Frozen evidence packet generation for A4 report rendering."""

from __future__ import annotations

from typing import Any

from dev.analysis.a4_evidence_reporting.common import json_cell, utc_now_iso
from dev.analysis.a4_evidence_reporting.confidence import max_reportability_label


def build_evidence_packet(
    *,
    report_id: str,
    mode: str,
    data,
    findings: list[dict[str, Any]],
    quote_bank: list[dict[str, Any]],
    caveats: list[dict[str, Any]],
) -> dict[str, Any]:
    denominators = {
        row.get("name", ""): {
            "kind": "denominator",
            "render": f"{row.get('name', '')}: {row.get('value', '')}",
            "value": dict(row),
        }
        for row in data.denominators
        if row.get("name")
    }
    finding_items = {
        f"F{i}": {
            "kind": "finding",
            "finding_id": row["finding_id"],
            "render": row["plain_language_summary"],
            "value": dict(row),
        }
        for i, row in enumerate(findings, start=1)
    }
    quote_items = {
        f"Q{i}": {
            "kind": "quote",
            "quote_id": row.get("quote_id", ""),
            "render": row.get("quote_text_redacted") or row.get("quote_text_original", ""),
            "source_claim_id": row.get("claim_id", ""),
            "redaction_status": row.get("redaction_status", ""),
            "public_allowed": row.get("public_allowed") == "1",
            "value": dict(row),
        }
        for i, row in enumerate(quote_bank, start=1)
    }
    caveat_items = {
        row["caveat_id"]: {
            "kind": "caveat",
            "render": row["text"],
            "value": dict(row),
        }
        for row in caveats
    }
    source_a2_run_ids = data.analysis_manifest.get("source_a2_run_ids") or []
    packet = {
        "packet_id": f"packet:{report_id}",
        "report_id": report_id,
        "mode": mode,
        "generated_at_utc": utc_now_iso(),
        "source_manifests": [
            {
                "analysis_id": data.analysis_manifest.get("analysis_id", data.paths.analysis_id),
                "analysis_dir": str(data.paths.analysis_dir),
                "analysis_manifest_sha256": data.analysis_manifest.get("analysis_file_hashes", {}).get("analysis_manifest.json", ""),
                "source_a2_run_ids_json": json_cell(source_a2_run_ids),
            }
        ],
        "denominators": denominators,
        "findings": finding_items,
        "quotes": quote_items,
        "caveats": caveat_items,
        "provenance": {
            "source_a3_analysis_ids": [data.analysis_manifest.get("analysis_id", data.paths.analysis_id)],
            "source_a2_run_ids": source_a2_run_ids,
            "analysis_version": data.analysis_manifest.get("analysis_version", ""),
            "normalization_version": data.analysis_manifest.get("normalization_version", ""),
            "audit_score_version": data.analysis_manifest.get("audit_score_version", ""),
            "source_file_hashes": data.analysis_manifest.get("source_file_hashes", {}),
            "analysis_file_hashes": data.analysis_manifest.get("analysis_file_hashes", {}),
        },
        "render_policy": {
            "llm_generated": False,
            "public_quotes_allowed": mode == "public_summary" and all(row.get("public_allowed") == "1" for row in quote_bank),
            "max_confidence_label": max_reportability_label(data.reportability),
        },
    }
    return packet
