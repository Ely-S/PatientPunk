"""A3 analysis orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dev.analysis.a3_result_analysis.codebook import write_codebook_outputs
from dev.analysis.a3_result_analysis.common import (
    ANALYSIS_VERSION,
    AUDIT_SCORE_VERSION,
    DEFAULT_A3_RUN_ROOT,
    NORMALIZATION_VERSION,
    analysis_dir_for_run,
    file_sha256,
    read_json,
    utc_now_iso,
    write_json,
)
from dev.analysis.a3_result_analysis.loaders import A2RunPaths, load_a2_export_data, resolve_a2_paths
from dev.analysis.a3_result_analysis.normalization import write_normalization_outputs
from dev.analysis.a3_result_analysis.quotes import write_quote_candidates
from dev.analysis.a3_result_analysis.reportability import write_reportability
from dev.analysis.a3_result_analysis.summaries import write_summary_outputs
from dev.analysis.a3_result_analysis.validate import validate_a2_run


def run_analysis(
    *,
    run: Path | None = None,
    exports: Path | None = None,
    output_root: Path = DEFAULT_A3_RUN_ROOT,
    output_dir: Path | None = None,
    normalization_map: Path | None = None,
) -> dict[str, Any]:
    paths = resolve_a2_paths(run=run, exports=exports)
    out_dir = output_dir or analysis_dir_for_run(paths.run_id, output_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    validation = validate_a2_run(paths, output_path=out_dir / "a2_validation_report.json")
    if not validation["ok"]:
        manifest = _write_analysis_manifest(
            paths=paths,
            output_dir=out_dir,
            validation=validation,
            row_counts={},
            warnings=validation["warnings"],
            errors=validation["errors"],
        )
        return {
            "ok": False,
            "analysis_dir": str(out_dir),
            "validation": validation,
            "analysis_manifest": manifest,
        }

    data = load_a2_export_data(paths)
    norm = write_normalization_outputs(
        claims=data.claims,
        output_dir=out_dir,
        map_path=normalization_map,
    )
    normalized_claims = norm["normalized_claims"]
    summary = write_summary_outputs(
        data=data,
        normalized_claims=normalized_claims,
        output_dir=out_dir,
    )
    quote_rows = write_quote_candidates(out_dir / "quote_candidates.csv", normalized_claims)
    reportability_rows = write_reportability(
        out_dir / "reportability_summary.csv",
        validation=validation,
        normalized_claims=normalized_claims,
    )
    codebook_rows = write_codebook_outputs(
        out_dir,
        tables={
            "comment_rows": data.comments,
            "claim_rows_normalized": normalized_claims,
            "attempts": data.attempts,
            "denominator_summary": summary["denominator_summary"],
            "quote_candidates": quote_rows,
            "reportability_summary": reportability_rows,
        },
    )

    row_counts = {
        "comment_rows": len(data.comments),
        "claim_rows": len(data.claims),
        "claim_rows_normalized": len(normalized_claims),
        "attempts": len(data.attempts),
        "failed_items": len(data.failed_items),
        "results": len(data.results),
        "quote_candidates": len(quote_rows),
        "reportability_rows": len(reportability_rows),
        "codebook_rows": len(codebook_rows),
    }
    manifest = _write_analysis_manifest(
        paths=paths,
        output_dir=out_dir,
        validation=validation,
        row_counts=row_counts,
        warnings=validation["warnings"],
        errors=[],
    )
    return {
        "ok": True,
        "analysis_dir": str(out_dir),
        "validation": validation,
        "row_counts": row_counts,
        "analysis_manifest": manifest,
    }


def _write_analysis_manifest(
    *,
    paths: A2RunPaths,
    output_dir: Path,
    validation: dict[str, Any],
    row_counts: dict[str, int],
    warnings: list[str],
    errors: list[str],
) -> dict[str, Any]:
    export_manifest_path = paths.exports_dir / "export_manifest.json"
    export_manifest = read_json(export_manifest_path) if export_manifest_path.exists() else {}
    analysis_files = _file_hashes(output_dir, exclude={"analysis_manifest.json"})
    normalization_map = output_dir / "normalization_map.csv"
    codebook = output_dir / "codebook.md"
    manifest = {
        "analysis_id": f"a3:{paths.run_id}",
        "analysis_version": ANALYSIS_VERSION,
        "generated_at_utc": utc_now_iso(),
        "source_a2_run_ids": [paths.run_id],
        "source_a2_export_manifests": [str(export_manifest_path)] if export_manifest_path.exists() else [],
        "source_a2_instrument_hashes": [export_manifest.get("instrument_hash")] if export_manifest.get("instrument_hash") else [],
        "source_file_hashes": _source_file_hashes(paths),
        "analysis_file_hashes": analysis_files,
        "normalization_version": NORMALIZATION_VERSION,
        "normalization_map_sha256": file_sha256(normalization_map) if normalization_map.exists() else None,
        "audit_score_version": AUDIT_SCORE_VERSION,
        "codebook_sha256": file_sha256(codebook) if codebook.exists() else None,
        "row_counts": row_counts,
        "validation_ok": validation.get("ok", False),
        "warnings": warnings,
        "errors": errors,
    }
    write_json(output_dir / "analysis_manifest.json", manifest)
    return manifest


def _source_file_hashes(paths: A2RunPaths) -> dict[str, str]:
    hashes = {}
    if not paths.exports_dir.exists():
        return hashes
    for path in sorted(paths.exports_dir.iterdir()):
        if path.is_file():
            hashes[path.name] = file_sha256(path)
    return hashes


def _file_hashes(directory: Path, *, exclude: set[str]) -> dict[str, str]:
    hashes = {}
    if not directory.exists():
        return hashes
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.name not in exclude:
            hashes[str(path.relative_to(directory))] = file_sha256(path)
    return hashes

