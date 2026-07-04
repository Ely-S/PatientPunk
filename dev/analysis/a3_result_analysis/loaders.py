"""Load A2 run outputs for A3 analysis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dev.analysis.a3_result_analysis.common import read_csv, read_json, read_jsonl


@dataclass(frozen=True)
class A2RunPaths:
    run_dir: Path | None
    exports_dir: Path
    run_db: Path | None

    @property
    def run_id(self) -> str:
        if self.run_dir is not None:
            return self.run_dir.name
        manifest = self.exports_dir / "run_manifest.json"
        if manifest.exists():
            data = read_json(manifest)
            if data.get("run_id"):
                return str(data["run_id"])
        return self.exports_dir.parent.name


def resolve_a2_paths(*, run: Path | None = None, exports: Path | None = None) -> A2RunPaths:
    if run is None and exports is None:
        raise ValueError("Pass either run or exports.")
    run_dir = run.resolve() if run is not None else None
    exports_dir = (exports or (run_dir / "exports")).resolve()  # type: ignore[operator]
    run_db = run_dir / "run.sqlite" if run_dir is not None and (run_dir / "run.sqlite").exists() else None
    return A2RunPaths(run_dir=run_dir, exports_dir=exports_dir, run_db=run_db)


@dataclass
class A2ExportData:
    paths: A2RunPaths
    export_manifest: dict[str, Any]
    run_manifest: dict[str, Any]
    run_report: dict[str, Any]
    comments: list[dict[str, str]]
    claims: list[dict[str, str]]
    attempts: list[dict[str, str]]
    failed_items: list[dict[str, str]]
    results: list[dict[str, Any]]


def load_a2_export_data(paths: A2RunPaths) -> A2ExportData:
    exports = paths.exports_dir
    return A2ExportData(
        paths=paths,
        export_manifest=read_json(exports / "export_manifest.json"),
        run_manifest=read_json(exports / "run_manifest.json"),
        run_report=read_json(exports / "run_report.json"),
        comments=read_csv(exports / "comment_rows.csv"),
        claims=read_csv(exports / "claim_rows.csv"),
        attempts=read_csv(exports / "attempts.csv"),
        failed_items=read_csv(exports / "failed_items.csv"),
        results=read_jsonl(exports / "results.jsonl") if (exports / "results.jsonl").exists() else [],
    )

