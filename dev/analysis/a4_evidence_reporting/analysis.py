"""A4 report package orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dev.analysis.a4_evidence_reporting.caveats import build_caveats
from dev.analysis.a4_evidence_reporting.common import (
    DEFAULT_A4_REPORT_ROOT,
    DEFAULT_MODE,
    DEFAULT_REPORT_TYPE,
    report_dir_for_id,
    slug,
    utc_now_compact,
    write_json,
)
from dev.analysis.a4_evidence_reporting.findings import build_finding_cards, write_finding_outputs
from dev.analysis.a4_evidence_reporting.loaders import load_a3_analysis_data, resolve_a3_paths, validate_a3_analysis
from dev.analysis.a4_evidence_reporting.manifest import source_rows, write_report_manifest
from dev.analysis.a4_evidence_reporting.mart import build_evidence_mart
from dev.analysis.a4_evidence_reporting.packet import build_evidence_packet
from dev.analysis.a4_evidence_reporting.quotes import build_quote_bank, write_quote_outputs
from dev.analysis.a4_evidence_reporting.render import render_limitations_md, render_methods_md, render_provenance_md, render_report_md
from dev.analysis.a4_evidence_reporting.tables import write_table_outputs
from dev.analysis.a4_evidence_reporting.validate import validate_report_package


def build_report(
    *,
    a3: Path,
    output_root: Path = DEFAULT_A4_REPORT_ROOT,
    output_dir: Path | None = None,
    report_id: str | None = None,
    report_type: str = DEFAULT_REPORT_TYPE,
    mode: str = DEFAULT_MODE,
) -> dict[str, Any]:
    paths = resolve_a3_paths(a3)
    report_id = report_id or f"a4_{slug(paths.analysis_dir.name)}_{utc_now_compact()}"
    out_dir = output_dir or report_dir_for_id(report_id, output_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    source_validation = validate_a3_analysis(paths, output_path=out_dir / "source_a3_validation_report.json")
    if not source_validation["ok"]:
        return {
            "ok": False,
            "report_id": report_id,
            "report_dir": str(out_dir),
            "source_validation": source_validation,
        }

    data = load_a3_analysis_data(paths)
    quote_bank = build_quote_bank(data, mode=mode)
    findings = build_finding_cards(data, report_id=report_id, quote_bank=quote_bank)
    caveats = build_caveats(mode=mode, data=data)
    packet = build_evidence_packet(
        report_id=report_id,
        mode=mode,
        data=data,
        findings=findings,
        quote_bank=quote_bank,
        caveats=caveats,
    )

    write_quote_outputs(out_dir, quote_bank)
    write_finding_outputs(out_dir, findings)
    table_rows = write_table_outputs(out_dir, data, findings)
    write_json(out_dir / "evidence_packet.json", packet)

    report_md = render_report_md(report_id=report_id, mode=mode, data=data, findings=findings, quote_bank=quote_bank, packet=packet)
    methods_md = render_methods_md(report_id=report_id, mode=mode, data=data, packet=packet)
    limitations_md = render_limitations_md(data=data, packet=packet)
    (out_dir / "report.md").write_text(report_md, encoding="utf-8")
    (out_dir / "methods.md").write_text(methods_md, encoding="utf-8")
    (out_dir / "limitations.md").write_text(limitations_md, encoding="utf-8")
    (out_dir / "provenance.md").write_text(render_provenance_md(report_id=report_id, output_dir=out_dir, data=data), encoding="utf-8")

    report_manifest_rows, source_a3_rows, source_file_rows = source_rows(data)
    build_evidence_mart(
        path=out_dir / "evidence_mart.sqlite",
        report_manifest_rows=report_manifest_rows,
        source_a3_rows=source_a3_rows,
        source_file_rows=source_file_rows,
        data=data,
        findings=findings,
        quote_bank=quote_bank,
        caveats=caveats,
    )

    row_counts = {
        "comments": len(data.comments),
        "claims": len(data.claims),
        "finding_cards": len(findings),
        "quote_bank": len(quote_bank),
        "caveats": len(caveats),
        **{name: len(rows) for name, rows in table_rows.items()},
    }
    manifest = write_report_manifest(
        output_dir=out_dir,
        report_id=report_id,
        report_type=report_type,
        mode=mode,
        data=data,
        row_counts=row_counts,
    )
    (out_dir / "provenance.md").write_text(
        render_provenance_md(report_id=report_id, output_dir=out_dir, data=data, manifest=manifest),
        encoding="utf-8",
    )
    manifest = write_report_manifest(
        output_dir=out_dir,
        report_id=report_id,
        report_type=report_type,
        mode=mode,
        data=data,
        row_counts=row_counts,
    )
    validation = validate_report_package(out_dir, output_path=out_dir / "validation_report.json")
    return {
        "ok": validation["ok"],
        "report_id": report_id,
        "report_dir": str(out_dir),
        "source_validation": source_validation,
        "validation": validation,
        "row_counts": row_counts,
        "report_manifest": manifest,
    }
