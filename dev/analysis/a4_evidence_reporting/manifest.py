"""Report manifest helpers for A4."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dev.analysis.a4_evidence_reporting.common import A4_VERSION, file_sha256, utc_now_iso, write_json


def source_rows(data) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    report_manifest_rows = [
        {"key": "analysis_id", "value": data.analysis_manifest.get("analysis_id", data.paths.analysis_id)},
        {"key": "analysis_version", "value": data.analysis_manifest.get("analysis_version", "")},
        {"key": "normalization_version", "value": data.analysis_manifest.get("normalization_version", "")},
        {"key": "validation_ok", "value": data.analysis_manifest.get("validation_ok", "")},
    ]
    source_a3_rows = [
        {
            "analysis_id": data.analysis_manifest.get("analysis_id", data.paths.analysis_id),
            "analysis_dir": str(data.paths.analysis_dir),
            "generated_at_utc": data.analysis_manifest.get("generated_at_utc", ""),
            "validation_ok": data.analysis_manifest.get("validation_ok", ""),
        }
    ]
    source_file_rows = []
    for kind, hashes in [
        ("a3_analysis", data.analysis_manifest.get("analysis_file_hashes") or {}),
        ("a2_source", data.analysis_manifest.get("source_file_hashes") or {}),
    ]:
        for name, digest in hashes.items():
            source_file_rows.append({"kind": kind, "path": name, "sha256": digest})
    return report_manifest_rows, source_a3_rows, source_file_rows


def write_report_manifest(
    *,
    output_dir: Path,
    report_id: str,
    report_type: str,
    mode: str,
    data,
    row_counts: dict[str, int],
) -> dict[str, Any]:
    manifest = {
        "report_id": report_id,
        "report_type": report_type,
        "mode": mode,
        "a4_version": A4_VERSION,
        "generated_at_utc": utc_now_iso(),
        "report_dir": str(output_dir),
        "source_a3_analysis_ids": [data.analysis_manifest.get("analysis_id", data.paths.analysis_id)],
        "source_a3_analysis_dirs": [str(data.paths.analysis_dir)],
        "source_a2_run_ids": data.analysis_manifest.get("source_a2_run_ids") or [],
        "source_a3_analysis_manifest_sha256": file_sha256(data.paths.analysis_dir / "analysis_manifest.json"),
        "row_counts": row_counts,
        "report_file_hashes": _report_file_hashes(output_dir),
    }
    write_json(output_dir / "report_manifest.json", manifest)
    return manifest


def _report_file_hashes(output_dir: Path) -> dict[str, str]:
    hashes = {}
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name not in {"report_manifest.json", "validation_report.json"}:
            hashes[str(path.relative_to(output_dir))] = file_sha256(path)
    return hashes
