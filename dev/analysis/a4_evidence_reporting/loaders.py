"""Load and validate A3 analysis packages for A4."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dev.analysis.a4_evidence_reporting.common import file_sha256, read_csv, read_json, write_json


REQUIRED_A3_FILES = [
    "analysis_manifest.json",
    "a2_validation_report.json",
    "run_quality_report.json",
    "claim_rows_normalized.csv",
    "claim_label_frequency.csv",
    "denominator_summary.csv",
    "reportability_summary.csv",
    "quote_candidates.csv",
    "normalization_manifest.json",
    "normalization_map.csv",
    "codebook.csv",
    "codebook.md",
]


@dataclass(frozen=True)
class A3AnalysisPaths:
    analysis_dir: Path

    @property
    def analysis_id(self) -> str:
        manifest = self.analysis_dir / "analysis_manifest.json"
        if manifest.exists():
            data = read_json(manifest)
            if data.get("analysis_id"):
                return str(data["analysis_id"])
        return f"a3:{self.analysis_dir.name}"


@dataclass
class A3AnalysisData:
    paths: A3AnalysisPaths
    analysis_manifest: dict[str, Any]
    validation_report: dict[str, Any]
    run_quality_report: dict[str, Any]
    normalization_manifest: dict[str, Any]
    comments: list[dict[str, str]]
    claims: list[dict[str, str]]
    claim_label_frequency: list[dict[str, str]]
    denominators: list[dict[str, str]]
    reportability: list[dict[str, str]]
    quote_candidates: list[dict[str, str]]
    source_export_dirs: list[Path]


def resolve_a3_paths(a3: Path) -> A3AnalysisPaths:
    return A3AnalysisPaths(analysis_dir=a3.resolve())


def validate_a3_analysis(paths: A3AnalysisPaths, *, output_path: Path | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    analysis_dir = paths.analysis_dir

    if not analysis_dir.exists():
        errors.append(f"A3 analysis directory not found: {analysis_dir}")
        result = _result(paths, errors, warnings, {})
        _maybe_write(output_path, result)
        return result

    for name in REQUIRED_A3_FILES:
        if not (analysis_dir / name).exists():
            errors.append(f"required A3 artifact missing: {name}")

    if errors:
        result = _result(paths, errors, warnings, {})
        _maybe_write(output_path, result)
        return result

    manifest = read_json(analysis_dir / "analysis_manifest.json")
    analysis_hash_checks = _verify_analysis_hashes(analysis_dir, manifest)
    errors.extend(analysis_hash_checks["errors"])
    warnings.extend(analysis_hash_checks["warnings"])

    source_hash_checks = _verify_source_hashes(analysis_dir, manifest)
    errors.extend(source_hash_checks["errors"])
    warnings.extend(source_hash_checks["warnings"])

    details = {
        "analysis_hash_checks": analysis_hash_checks["hashes"],
        "source_hash_checks": source_hash_checks["hashes"],
        "source_export_dirs": [str(path) for path in _source_export_dirs(manifest, analysis_dir)],
        "row_counts": manifest.get("row_counts", {}),
    }
    result = _result(paths, errors, warnings, details)
    _maybe_write(output_path, result)
    return result


def load_a3_analysis_data(paths: A3AnalysisPaths) -> A3AnalysisData:
    analysis_dir = paths.analysis_dir
    analysis_manifest = read_json(analysis_dir / "analysis_manifest.json")
    source_export_dirs = _source_export_dirs(analysis_manifest, analysis_dir)
    comments: list[dict[str, str]] = []
    for exports_dir in source_export_dirs:
        comment_path = exports_dir / "comment_rows.csv"
        if comment_path.exists():
            comments.extend(read_csv(comment_path))

    return A3AnalysisData(
        paths=paths,
        analysis_manifest=analysis_manifest,
        validation_report=read_json(analysis_dir / "a2_validation_report.json"),
        run_quality_report=read_json(analysis_dir / "run_quality_report.json"),
        normalization_manifest=read_json(analysis_dir / "normalization_manifest.json"),
        comments=comments,
        claims=read_csv(analysis_dir / "claim_rows_normalized.csv"),
        claim_label_frequency=read_csv(analysis_dir / "claim_label_frequency.csv"),
        denominators=read_csv(analysis_dir / "denominator_summary.csv"),
        reportability=read_csv(analysis_dir / "reportability_summary.csv"),
        quote_candidates=read_csv(analysis_dir / "quote_candidates.csv"),
        source_export_dirs=source_export_dirs,
    )


def _verify_analysis_hashes(analysis_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    hashes: dict[str, str] = {}
    for rel_path, expected in (manifest.get("analysis_file_hashes") or {}).items():
        path = analysis_dir / rel_path
        if not path.exists():
            errors.append(f"manifest-listed A3 file missing: {rel_path}")
            continue
        actual = file_sha256(path)
        hashes[rel_path] = actual
        if expected and actual != expected:
            errors.append(f"A3 hash mismatch for {rel_path}: expected {expected}, got {actual}")
    if not hashes:
        warnings.append("analysis_manifest.json has no analysis_file_hashes")
    return {"errors": errors, "warnings": warnings, "hashes": hashes}


def _verify_source_hashes(analysis_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    hashes: dict[str, dict[str, str]] = {}
    source_hashes = manifest.get("source_file_hashes") or {}
    export_dirs = _source_export_dirs(manifest, analysis_dir)
    if not export_dirs:
        errors.append("analysis_manifest.json has no resolvable source A2 export directories")
        return {"errors": errors, "warnings": warnings, "hashes": hashes}
    for exports_dir in export_dirs:
        export_hashes: dict[str, str] = {}
        hashes[str(exports_dir)] = export_hashes
        for name, expected in source_hashes.items():
            path = exports_dir / name
            if not path.exists():
                errors.append(f"source A2 file missing: {path}")
                continue
            actual = file_sha256(path)
            export_hashes[name] = actual
            if expected and actual != expected:
                errors.append(f"source A2 hash mismatch for {name}: expected {expected}, got {actual}")
    if not source_hashes:
        warnings.append("analysis_manifest.json has no source_file_hashes")
    return {"errors": errors, "warnings": warnings, "hashes": hashes}


def _source_export_dirs(manifest: dict[str, Any], analysis_dir: Path) -> list[Path]:
    out: list[Path] = []
    for value in manifest.get("source_a2_export_manifests") or []:
        path = Path(value)
        candidates = [path]
        if not path.is_absolute():
            candidates.append(analysis_dir / path)
        for candidate in candidates:
            if candidate.exists():
                out.append(candidate.resolve().parent)
                break
    return out


def _result(paths: A3AnalysisPaths, errors: list[str], warnings: list[str], details: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": not errors,
        "analysis_id": paths.analysis_id,
        "analysis_dir": str(paths.analysis_dir),
        "errors": errors,
        "warnings": warnings,
        "details": details,
    }


def _maybe_write(path: Path | None, result: dict[str, Any]) -> None:
    if path is not None:
        write_json(path, result)
