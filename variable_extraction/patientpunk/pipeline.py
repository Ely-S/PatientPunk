"""
patientpunk.pipeline
~~~~~~~~~~~~~~~~~~~~~
High-level orchestrator for the PatientPunk extraction pipeline.

The :class:`Pipeline` class ties together all five phases -- regex extraction,
LLM gap-filling, field discovery, CSV export, and codebook generation -- into
a single, configurable object.  Each phase is optional and can be skipped via
the ``PipelineConfig`` flags.

Example
-------
>>> from patientpunk.pipeline import Pipeline, PipelineConfig
>>> config = PipelineConfig(
...     schema_path=Path("schemas/covidlonghaulers_schema.json"),
...     input_dir=Path("../output"),
...     workers=10,
... )
>>> pipeline = Pipeline(config)
>>> result = pipeline.run()
>>> print(result.summary())
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._utils import clean_temp_dir, csv_fill_rate, find_discovery_reports, find_newest_glob, get_schema_id, llm_config
from .biomedical import run_biomedical
from .codebook import run_codebook
from .discover import run_discovery
from .export_csv import run_export_csv
from .llm_extract import run_llm_extract
from .phase import PhaseOutput

# Intermediate file glob patterns that live in temp_dir.
# These are wiped at the start of a full run unless clean=False.
# All filenames embed a schema_id suffix (e.g. "covidlonghaulers") so that
# multiple schemas can be processed sequentially in the same temp dir without
# their intermediate files colliding or being mistakenly consumed by the wrong
# schema's phase. The only exception is phase1_candidates.json, which is a
# one-off pre-filter artifact that is never schema-multiplexed.
_TEMP_PATTERNS: list[str] = [
    "patientpunk_records_*.json",
    "extraction_metadata_*.json",
    "llm_records_*.json",
    "llm_field_suggestions_*.json",
    "merged_records_*.json",
    "phase1_candidates.json",
    "discovered_records_*.json",
    "discovered_field_report_*.json",
]


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------

class PipelineConfig(BaseModel):
    """All settings that control a pipeline run."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    schema_path: Path

    # Paths
    input_dir: Path = Field(
        default_factory=lambda: Path.cwd() / "output"
    )
    temp_dir: Path | None = None

    # Phase control
    start_at: int = 1
    run_llm: bool = True
    # Discovery is off by default. Use discovery_mode="auto" to run and
    # auto-merge all candidates, or "review" to stop after candidate
    # generation so the user can select fields in the Marimo variable picker.
    discovery_mode: str | None = None
    clean: bool = True

    # Shared
    workers: int = 10
    limit: int | None = None
    resume: bool = False

    # Phase 2
    llm_skip_threshold: float = 0.7
    llm_focus_gaps: bool = True

    # Phase 3
    candidates_file: Path | None = None
    discovery_sample: int | None = None
    discovery_fill_gaps: bool = True

    # Phase 4
    csv_sep: str = " | "
    csv_provenance: bool = False

    # Phase 5
    codebook_format: str = "csv"
    codebook_include_discovered: bool = True

    @model_validator(mode="after")
    def _coerce_paths_and_validate(self) -> "PipelineConfig":
        """Coerce string paths to Path objects and validate start_at range."""
        self.schema_path = Path(self.schema_path)
        self.input_dir = Path(self.input_dir)
        if self.temp_dir is None:
            self.temp_dir = self.input_dir / "temp"
        else:
            self.temp_dir = Path(self.temp_dir)
        if self.candidates_file:
            self.candidates_file = Path(self.candidates_file)
        if self.start_at not in range(1, 6):
            raise ValueError(f"start_at must be 1-5, got {self.start_at}")
        if self.discovery_mode is not None and self.discovery_mode not in ("auto", "review"):
            raise ValueError(
                f"discovery_mode must be None, 'auto', or 'review', got {self.discovery_mode!r}"
            )
        return self


# ---------------------------------------------------------------------------
# Per-phase result
# ---------------------------------------------------------------------------

class PhaseResult(BaseModel):
    """Outcome and timing for a single pipeline phase."""

    phase: int
    label: str
    skipped: bool = False
    elapsed: float = 0.0
    ok: bool = True
    error: str | None = None
    stats: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pipeline result
# ---------------------------------------------------------------------------

class PipelineResult(BaseModel):
    """Aggregate result of a full pipeline run."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    phases: list[PhaseResult] = Field(default_factory=list)
    total_elapsed: float = 0.0
    schema_id: str = ""
    input_dir: Path = Field(default_factory=Path)
    output_dir: Path = Field(default_factory=Path)

    @property
    def ok(self) -> bool:
        """True if every executed phase succeeded."""
        return all(phase.ok for phase in self.phases if not phase.skipped)

    def summary(self) -> str:
        """Return a human-readable multi-line summary string."""
        mins, secs = divmod(int(self.total_elapsed), 60)
        lines = [
            "",
            "=" * 60,
            f"  PIPELINE SUMMARY  ({mins}m {secs}s total)",
            "=" * 60,
        ]
        for phase_result in self.phases:
            if phase_result.skipped:
                lines.append(f"\n  Phase {phase_result.phase} -- {phase_result.label}  [SKIPPED]")
                continue
            status = "OK" if phase_result.ok else f"FAILED ({phase_result.error})"
            lines.append(f"\n  Phase {phase_result.phase} -- {phase_result.label}  [{status}]  {phase_result.elapsed:.0f}s")
            for stat_name, stat_value in phase_result.stats.items():
                lines.append(f"    {stat_name:<28} {stat_value}")
        lines.append("\n" + "=" * 60 + "\n")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------

class Pipeline:
    """
    Orchestrate the full PatientPunk extraction pipeline.

    Parameters
    ----------
    config:
        A :class:`PipelineConfig` instance controlling all phases.
    """

    _PHASE_LABELS = {
        1: "Regex extraction     (biomedical)",
        2: "LLM gap-filling      (llm_extract)",
        3: "Field discovery      (discover)",
        4: "CSV export           (export_csv)",
        5: "Codebook             (codebook)",
    }

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self._schema_id = get_schema_id(config.schema_path)
        self._temp_dir: Path = config.temp_dir  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self) -> PipelineResult:
        """Execute all configured phases in order."""
        cfg = self.config
        result = PipelineResult(
            schema_id=self._schema_id,
            input_dir=cfg.input_dir,
            output_dir=cfg.input_dir,
        )
        pipeline_start = time.time()

        self._print_header()

        # Ensure temp dir exists
        self._temp_dir.mkdir(parents=True, exist_ok=True)

        # Clean intermediate files at the start of a full run
        if cfg.start_at == 1 and cfg.clean:
            self._clean_temp()

        # Record the LLM configuration (model / provider / base_url / temperature)
        # so every output is traceable to the model + settings that produced it.
        prov = {**llm_config(), "schema_id": self._schema_id,
                "run_llm": cfg.run_llm, "discovery_mode": cfg.discovery_mode}
        try:
            (cfg.input_dir / "llm_provenance.json").write_text(
                json.dumps(prov, indent=2), encoding="utf-8")
        except OSError:
            pass
        print(f"  LLM config: provider={prov['provider']}  fast={prov['model_fast']}  "
              f"strong={prov['model_strong']}  temp={prov['temperature']}"
              + (f"  base_url={prov['base_url']}" if prov['base_url'] else ""))

        # Phase 1 -- regex extraction
        result.phases.append(self._run_phase_1())
        if not result.phases[-1].ok:
            result.total_elapsed = time.time() - pipeline_start
            return result

        # Phase 2 -- LLM gap-filling
        result.phases.append(self._run_phase_2())
        if not result.phases[-1].ok:
            result.total_elapsed = time.time() - pipeline_start
            return result

        # Phase 3 -- field discovery
        skip_discovery = cfg.start_at > 3 or cfg.discovery_mode is None
        result.phases.append(self._run_phase_3(skip=skip_discovery))
        if not result.phases[-1].ok and not result.phases[-1].skipped:
            result.total_elapsed = time.time() - pipeline_start
            return result
        if cfg.discovery_mode == "review" and not result.phases[-1].skipped:
            print("\n  Discovery candidates saved to temp/.")
            print("  Review in: marimo run apps/discover.py")
            print("  Then re-run with: --start-at 4 --no-clean")
            result.total_elapsed = time.time() - pipeline_start
            return result

        # Phase 4 -- CSV export
        result.phases.append(self._run_phase_4())
        if not result.phases[-1].ok:
            result.total_elapsed = time.time() - pipeline_start
            return result

        # Phase 5 -- codebook
        result.phases.append(self._run_phase_5())

        result.total_elapsed = time.time() - pipeline_start
        print(result.summary())
        return result

    # ------------------------------------------------------------------
    # Internal phase runners
    # ------------------------------------------------------------------

    def _call_phase(
        self,
        phase: int,
        *,
        skip: bool,
        runner,
    ) -> PhaseResult:
        """Run a phase callable that returns PhaseOutput (or raises)."""
        label = self._PHASE_LABELS[phase]
        if skip:
            print(f"\n  [Skipping phase {phase}]")
            return PhaseResult(phase=phase, label=label, skipped=True)

        self._print_phase_banner(phase, label)
        t0 = time.time()
        try:
            out: PhaseOutput | None = runner()
            elapsed = time.time() - t0
            stats = (out.stats if out and out.stats else None) or self._collect_stats(phase)
            pr = PhaseResult(
                phase=phase,
                label=label,
                elapsed=elapsed,
                ok=True,
                stats=stats,
            )
            self._print_phase_stats(pr)
            return pr
        except Exception as exc:
            elapsed = time.time() - t0
            print(f"\n  [Pipeline stopped] Phase {phase} failed: {exc}")
            return PhaseResult(
                phase=phase,
                label=label,
                elapsed=elapsed,
                ok=False,
                error=str(exc),
            )

    def _run_phase_1(self) -> PhaseResult:
        cfg = self.config
        return self._call_phase(
            1,
            skip=(cfg.start_at > 1),
            runner=lambda: run_biomedical(
                input_dir=cfg.input_dir,
                schema_path=cfg.schema_path,
                temp_dir=self._temp_dir,
            ),
        )

    def _run_phase_2(self) -> PhaseResult:
        cfg = self.config
        return self._call_phase(
            2,
            skip=(cfg.start_at > 2 or not cfg.run_llm),
            runner=lambda: run_llm_extract(
                input_dir=cfg.input_dir,
                schema_path=cfg.schema_path,
                temp_dir=self._temp_dir,
                workers=cfg.workers,
                skip_threshold=cfg.llm_skip_threshold,
                focus_gaps=cfg.llm_focus_gaps,
                resume=cfg.resume,
                limit=cfg.limit,
            ),
        )

    def _run_phase_3(self, *, skip: bool) -> PhaseResult:
        cfg = self.config

        def _runner() -> PhaseOutput:
            candidates = cfg.candidates_file
            if candidates is None:
                auto = self._temp_dir / "phase1_candidates.json"
                if auto.exists():
                    candidates = auto
            return run_discovery(
                input_dir=cfg.input_dir,
                schema_path=cfg.schema_path,
                temp_dir=self._temp_dir,
                workers=cfg.workers,
                limit=cfg.limit,
                fill_gaps=cfg.discovery_fill_gaps,
                resume=cfg.resume,
                candidates_file=candidates,
                sample=cfg.discovery_sample,
            )

        return self._call_phase(3, skip=skip, runner=_runner)

    def _find_discovered_records(self) -> Path | None:
        """
        Return the best discovered-records file for the current base schema.

        Preference order:
        1. A records file referenced by a discovery report whose
           ``pipeline_run.base_schema`` matches this pipeline's schema_id.
        2. Fallback to the newest discovered_records_*.json file in temp/.
        """
        matched_records: list[Path] = []
        for _report_path, report in find_discovery_reports(self._temp_dir, self._schema_id):
            records_file = report.get("records_file")
            if not isinstance(records_file, str) or not records_file.strip():
                continue

            record_path = Path(records_file)
            if not record_path.is_absolute():
                record_path = self._temp_dir / record_path.name
            if record_path.exists():
                matched_records.append(record_path)

        if matched_records:
            return max(matched_records, key=lambda p: p.stat().st_mtime)

        return find_newest_glob(self._temp_dir, "discovered_records_*.json")

    def _find_discovered_schema(self) -> Path | None:
        """Return the discovered-schema JSON for the current base schema, if any.

        Report-driven only: resolves ``schema_file`` from the newest matching
        discovery report.  Unlike :meth:`_find_discovered_records` there is no
        blind-glob fallback -- a bare ``discovered_*.json`` glob would also match
        the report and records files and cannot be schema-verified.
        """
        reports = find_discovery_reports(self._temp_dir, self._schema_id)
        reports.sort(key=lambda rp: rp[0].stat().st_mtime, reverse=True)
        for _report_path, report in reports:
            schema_file = report.get("schema_file")
            if not isinstance(schema_file, str) or not schema_file.strip():
                continue
            schema_path = Path(schema_file)
            if not schema_path.is_absolute():
                schema_path = self._temp_dir / schema_path.name
            if schema_path.exists():
                return schema_path
        return None

    def _run_phase_4(self) -> PhaseResult:
        """Phase 4 -- assemble input files and call run_export_csv."""
        phase = 4
        label = self._PHASE_LABELS[phase]

        if self.config.start_at > 4:
            print(f"\n  [Skipping phase {phase}]")
            return PhaseResult(phase=phase, label=label, skipped=True)

        self._print_phase_banner(phase, label)

        merged_path = self._temp_dir / f"merged_records_{self._schema_id}.json"
        regex_path = self._temp_dir / f"patientpunk_records_{self._schema_id}.json"
        if merged_path.exists():
            input_files = [merged_path]
        elif regex_path.exists():
            print(f"  merged_records not found -- falling back to regex-only records")
            input_files = [regex_path]
        else:
            input_files = [merged_path]

        disc = self._find_discovered_records()
        if disc:
            input_files.append(disc)
            print(f"  Including discovered records: {disc.name}")
        else:
            print(f"  No discovered records found -- exporting base records only")

        missing = [path for path in input_files if not path.exists()]
        if missing:
            print(f"  [Warning] Missing: {[path.name for path in missing]}")
        input_files = [path for path in input_files if path.exists()]

        if not input_files:
            print("  [Skipping phase 4 -- no input files available]")
            return PhaseResult(phase=phase, label=label, skipped=True)

        output_csv = self.config.input_dir / "records.csv"

        t0 = time.time()
        try:
            out = run_export_csv(
                input_files=input_files,
                output_path=output_csv,
                sep=self.config.csv_sep,
                include_provenance=self.config.csv_provenance,
            )
            elapsed = time.time() - t0
            stats = csv_fill_rate(output_csv) or out.stats
            pr = PhaseResult(
                phase=phase, label=label, elapsed=elapsed, ok=True, stats=stats
            )
            self._print_phase_stats(pr)
            return pr
        except Exception as exc:
            elapsed = time.time() - t0
            print(f"\n  [Pipeline stopped] Phase {phase} failed: {exc}")
            return PhaseResult(
                phase=phase, label=label, elapsed=elapsed, ok=False,
                error=str(exc),
            )

    def _run_phase_5(self) -> PhaseResult:
        """Phase 5 -- codebook generation."""
        phase = 5
        label = self._PHASE_LABELS[phase]

        if self.config.start_at > 5:
            print(f"\n  [Skipping phase {phase}]")
            return PhaseResult(phase=phase, label=label, skipped=True)

        self._print_phase_banner(phase, label)
        records_csv = self.config.input_dir / "records.csv"
        disc_schema = (
            self._find_discovered_schema()
            if self.config.codebook_include_discovered else None
        )
        if disc_schema:
            print(f"  Including discovered schema: {disc_schema.name}")

        # Default codebook next to records.csv (input_dir), matching prior CLI default
        # when Pipeline drove make_codebook via the exporter (schema parent was schemas/).
        ext = "md" if self.config.codebook_format == "markdown" else "csv"
        output_path = self.config.input_dir / f"codebook.{ext}"

        t0 = time.time()
        try:
            run_codebook(
                schema_path=self.config.schema_path,
                records_csv=records_csv if records_csv.exists() else None,
                output_path=output_path,
                fmt=self.config.codebook_format,
                include_discovered=self.config.codebook_include_discovered,
                discovered_schema_path=disc_schema,
            )
            elapsed = time.time() - t0
            return PhaseResult(phase=phase, label=label, elapsed=elapsed, ok=True)
        except Exception as exc:
            elapsed = time.time() - t0
            print(f"\n  [Pipeline stopped] Phase {phase} failed: {exc}")
            return PhaseResult(
                phase=phase, label=label, elapsed=elapsed, ok=False,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Stats collection
    # ------------------------------------------------------------------

    def _collect_stats(self, phase: int) -> dict:
        """Collect lightweight post-phase statistics from artifact files."""
        import json as _json

        schema_id = self._schema_id
        temp_dir = self._temp_dir

        if phase == 1:
            meta_path = temp_dir / f"extraction_metadata_{schema_id}.json"
            try:
                meta = _json.loads(meta_path.read_text(encoding="utf-8"))
            except (_json.JSONDecodeError, OSError):
                return {}
            total = meta.get("total_records_processed", 0)
            hits = meta.get("field_hit_counts", {})
            n_hit = sum(1 for hit_count in hits.values() if hit_count > 0)
            return {
                "records processed":  total,
                "fields with hits":   f"{n_hit}/{len(hits)}",
                "zero-coverage fields": len(hits) - n_hit,
            }

        if phase == 2:
            llm_path = temp_dir / f"llm_records_{schema_id}.json"
            merged_path = temp_dir / f"merged_records_{schema_id}.json"
            try:
                llm = _json.loads(llm_path.read_text(encoding="utf-8"))
                merged = _json.loads(merged_path.read_text(encoding="utf-8"))
            except (_json.JSONDecodeError, OSError):
                return {}
            fills = sum(
                1 for rec in llm
                for field_value in rec.get("fields", {}).values()
                if field_value is not None
            )
            return {
                "LLM records":     len(llm),
                "merged records":  len(merged),
                "LLM field fills": fills,
                "avg fills/record": round(fills / len(llm), 2) if llm else 0,
            }

        if phase == 3:
            disc_path = self._find_discovered_records()
            if not disc_path:
                return {}
            try:
                records = _json.loads(disc_path.read_text(encoding="utf-8"))
            except (_json.JSONDecodeError, OSError):
                return {}
            field_hits: dict[str, int] = {}
            for rec in records:
                for fname, fdata in rec.get("discovered_fields", {}).items():
                    if fdata.get("values"):
                        field_hits[fname] = field_hits.get(fname, 0) + 1
            record_count = len(records)
            covered = sum(
                1 for rec in records
                if any(
                    fd.get("values")
                    for fd in rec.get("discovered_fields", {}).values()
                )
            )
            return {
                "fields discovered":     len(field_hits),
                "records with any hit":  f"{covered}/{record_count}",
                "coverage %":            f"{round(covered / record_count * 100, 1) if record_count else 0}%",
            }

        return {}

    # ------------------------------------------------------------------
    # Console output helpers
    # ------------------------------------------------------------------

    def _print_header(self) -> None:
        cfg = self.config
        print(f"\nPatientPunk Pipeline")
        print(f"  Schema:    {cfg.schema_path.name}  (id: {self._schema_id})")
        print(f"  Input/out: {cfg.input_dir}")
        print(f"  Temp:      {self._temp_dir}")
        if cfg.start_at > 1:
            print(f"  Starting at phase {cfg.start_at}")
        if not cfg.run_llm:
            print("  Skipping:  phase 2 (run_llm=False)")
        if cfg.discovery_mode is None:
            print("  Skipping:  phase 3 (discovery off by default; use --discover auto|review)")
        else:
            print(f"  Discovery: {cfg.discovery_mode}")

    @staticmethod
    def _print_phase_banner(phase: int, label: str) -> None:
        print("\n" + "=" * 60)
        print(f"  PHASE {phase}: {label}")
        print("=" * 60)

    @staticmethod
    def _print_phase_stats(phase_result: PhaseResult) -> None:
        if not phase_result.stats:
            return
        print(f"\n  -- Phase {phase_result.phase} stats ({phase_result.elapsed:.0f}s) " + "-" * 26)
        for stat_name, stat_value in phase_result.stats.items():
            print(f"  {stat_name:<30} {stat_value}")
        print("  " + "-" * 52)

    def _clean_temp(self) -> None:
        removed = clean_temp_dir(self._temp_dir, _TEMP_PATTERNS)
        print("\n" + "=" * 60)
        print("  Cleaning intermediate files from temp/")
        print("=" * 60)
        if removed:
            print(f"  Removed {len(removed)} file(s): {', '.join(removed)}")
        else:
            print(f"  {self._temp_dir.name}/ already clean.")
