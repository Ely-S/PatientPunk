"""
patientpunk.pipeline
~~~~~~~~~~~~~~~~~~~~~
High-level orchestrator for the PatientPunk extraction pipeline.

The :class:`Pipeline` class ties together all five phases — regex extraction,
LLM gap-filling, field discovery, CSV export, and codebook generation — into
a single, configurable object.  Each phase is optional and can be skipped via
the ``PipelineConfig`` flags.

Example
-------
>>> from patientpunk.pipeline import Pipeline, PipelineConfig
>>> config = PipelineConfig(
...     schema_path=Path("schemas/covidlonghaulers_schema.json"),
...     input_dir=Path("../data"),
...     workers=10,
... )
>>> pipeline = Pipeline(config)
>>> result = pipeline.run()
>>> print(result.summary())
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from ._utils import clean_temp_dir, csv_fill_rate, find_newest_glob, get_schema_id, load_json
from .extractors import BiomedicalExtractor, ExtractorError, FieldDiscoveryExtractor, LLMExtractor
from .exporters import CSVExporter, CodebookGenerator

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

@dataclass
class PipelineConfig:
    """
    All settings that control a pipeline run.

    Parameters
    ----------
    schema_path:
        Extension schema JSON (e.g. ``schemas/covidlonghaulers_schema.json``).
        Required for named-schema runs; all five phases use it.
    input_dir:
        Directory containing the corpus and where final outputs are written.
        Defaults to ``../../data`` relative to this file.
    temp_dir:
        Directory for intermediate files.  Defaults to ``{input_dir}/temp/``.

    Phase control
    ~~~~~~~~~~~~~
    start_at:
        Phase number to start from (1–5).  Phases before this are skipped.
    run_llm:
        Include Phase 2 — LLM gap-filling (requires Anthropic API key).
    run_discovery:
        Include Phase 3 — field discovery (requires Anthropic API key).
    clean:
        Wipe ``temp_dir`` before starting Phase 1.  Has no effect when
        ``start_at > 1``.

    Shared options
    ~~~~~~~~~~~~~~
    workers:
        Concurrent API workers for LLM phases (default: 10).
    limit:
        Process at most *N* records — useful for cost-capped test runs.
    resume:
        Resume interrupted LLM / discovery runs.

    Phase 2 options
    ~~~~~~~~~~~~~~~
    llm_skip_threshold:
        Skip records where regex already found ≥ this fraction of fields
        (0.0–1.0, default: 0.7).
    llm_focus_gaps:
        Only ask the LLM about fields regex missed (default: *True*).

    Phase 3 options
    ~~~~~~~~~~~~~~~
    candidates_file:
        Path to a saved ``phase1_candidates.json`` — skips Phase 3 Stage 1.
    discovery_sample:
        Randomly sample *N* corpus items for Phase 3 Stage 1.
    discovery_fill_gaps:
        Run Phase 3 Stage 4 gap-filling (default: *True*).

    Phase 4 options
    ~~~~~~~~~~~~~~~
    csv_sep:
        Multi-value separator for the CSV (default: ``" | "``).
    csv_provenance:
        Include ``{field}__provenance`` and ``{field}__confidence`` columns.

    Phase 5 options
    ~~~~~~~~~~~~~~~
    codebook_format:
        ``"csv"`` (default) or ``"markdown"``.
    codebook_include_discovered:
        Include ``llm_discovered`` fields in the codebook (default: *True*).
    """

    schema_path: Path

    # Paths
    input_dir: Path = field(
        default_factory=lambda: Path(__file__).parent.parent.parent / "data"
    )
    temp_dir: Path | None = None

    # Phase control
    start_at: int = 1
    run_llm: bool = True
    run_discovery: bool = True
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

    def __post_init__(self) -> None:
        # Coerce to Path objects here rather than relying on callers to do so.
        # Users often pass plain strings (e.g. from argparse or config files),
        # and all downstream code depends on Path methods (.exists(), /operator,
        # .name, etc.).  Doing the coercion once in __post_init__ keeps every
        # other method clean and avoids silent AttributeErrors at runtime.
        self.schema_path = Path(self.schema_path)
        self.input_dir = Path(self.input_dir)
        if self.temp_dir is None:
            self.temp_dir = self.input_dir / "temp"
        else:
            self.temp_dir = Path(self.temp_dir)
        if self.candidates_file:
            self.candidates_file = Path(self.candidates_file)
        # Validate start_at here (in __post_init__) rather than in Pipeline.run()
        # so that a misconfigured PipelineConfig raises immediately on construction,
        # before any files are touched or API calls are made.
        if self.start_at not in range(1, 6):
            raise ValueError(f"start_at must be 1–5, got {self.start_at}")


# ---------------------------------------------------------------------------
# Per-phase result
# ---------------------------------------------------------------------------

@dataclass
class PhaseResult:
    """Outcome and timing for a single pipeline phase."""

    phase: int
    label: str
    skipped: bool = False
    elapsed: float = 0.0
    ok: bool = True
    error: str | None = None
    stats: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pipeline result
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    """Aggregate result of a full pipeline run."""

    phases: list[PhaseResult] = field(default_factory=list)
    total_elapsed: float = 0.0
    schema_id: str = ""
    input_dir: Path = field(default_factory=Path)
    output_dir: Path = field(default_factory=Path)

    @property
    def ok(self) -> bool:
        """True if every executed phase succeeded."""
        return all(p.ok for p in self.phases if not p.skipped)

    def summary(self) -> str:
        """Return a human-readable multi-line summary string."""
        mins, secs = divmod(int(self.total_elapsed), 60)
        lines = [
            "",
            "=" * 60,
            f"  PIPELINE SUMMARY  ({mins}m {secs}s total)",
            "=" * 60,
        ]
        for pr in self.phases:
            if pr.skipped:
                lines.append(f"\n  Phase {pr.phase} — {pr.label}  [SKIPPED]")
                continue
            status = "OK" if pr.ok else f"FAILED (exit {pr.error})"
            lines.append(f"\n  Phase {pr.phase} — {pr.label}  [{status}]  {pr.elapsed:.0f}s")
            for k, v in pr.stats.items():
                lines.append(f"    {k:<28} {v}")
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
        1: "Regex extraction     (extract_biomedical)",
        2: "LLM gap-filling      (llm_extract)",
        3: "Field discovery      (discover_fields)",
        4: "CSV export           (records_to_csv)",
        5: "Codebook             (make_codebook)",
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

        # Phase 1 — regex extraction
        result.phases.append(
            self._run_phase(
                phase=1,
                skip=(cfg.start_at > 1),
                extractor=BiomedicalExtractor(
                    input_dir=cfg.input_dir,
                    schema_path=cfg.schema_path,
                    temp_dir=self._temp_dir,
                ),
            )
        )
        # Fail-fast pattern: if Phase 1 regex extraction failed there is nothing
        # for Phase 2 to work on — the merged_records file won't exist and every
        # downstream phase would fail with confusing "file not found" errors.
        # Returning early here gives the caller a clean, partial PipelineResult
        # with ok=False on the failed phase rather than a cascade of failures.
        if not result.phases[-1].ok:
            result.total_elapsed = time.time() - pipeline_start
            return result

        # Phase 2 — LLM gap-filling
        result.phases.append(
            self._run_phase(
                phase=2,
                skip=(cfg.start_at > 2 or not cfg.run_llm),
                extractor=LLMExtractor(
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
        )
        # Same fail-fast check: if the LLM phase failed (e.g. API auth error,
        # malformed output), the merged_records file may be incomplete or absent,
        # so there is no point attempting Phase 3 field discovery or CSV export.
        if not result.phases[-1].ok:
            result.total_elapsed = time.time() - pipeline_start
            return result

        # Phase 3 — field discovery
        result.phases.append(
            self._run_phase(
                phase=3,
                skip=(cfg.start_at > 3 or not cfg.run_discovery),
                extractor=FieldDiscoveryExtractor(
                    input_dir=cfg.input_dir,
                    schema_path=cfg.schema_path,
                    temp_dir=self._temp_dir,
                    workers=cfg.workers,
                    limit=cfg.limit,
                    fill_gaps=cfg.discovery_fill_gaps,
                    resume=cfg.resume,
                    candidates_file=cfg.candidates_file,
                    sample=cfg.discovery_sample,
                ),
            )
        )
        # If discovery failed, discovered_records_*.json won't exist; Phase 4
        # would silently export an incomplete CSV with no discovered columns.
        # Stopping here preserves the integrity of the final output.
        if not result.phases[-1].ok:
            result.total_elapsed = time.time() - pipeline_start
            return result

        # Phase 4 — CSV export
        result.phases.append(self._run_phase_4())
        # No CSV means the codebook (Phase 5) has no fill-rate data to work from.
        if not result.phases[-1].ok:
            result.total_elapsed = time.time() - pipeline_start
            return result

        # Phase 5 — codebook
        result.phases.append(self._run_phase_5())

        result.total_elapsed = time.time() - pipeline_start
        print(result.summary())
        return result

    # ------------------------------------------------------------------
    # Internal phase runners
    # ------------------------------------------------------------------

    def _run_phase(self, phase: int, skip: bool, extractor) -> PhaseResult:
        """Generic phase runner that delegates to an extractor/exporter."""
        label = self._PHASE_LABELS[phase]
        if skip:
            print(f"\n  [Skipping phase {phase}]")
            return PhaseResult(phase=phase, label=label, skipped=True)

        self._print_phase_banner(phase, label)
        t0 = time.time()
        try:
            # raise_on_error=True tells the extractor to raise ExtractorError
            # (rather than returning a falsy result) if the subprocess it spawns
            # exits with a non-zero return code.  We catch it here — rather than
            # letting it propagate to the caller — so that _run_phase can always
            # return a fully populated PhaseResult object.  This keeps Pipeline.run()
            # clean: it only needs to inspect result.phases[-1].ok instead of
            # wrapping every phase call in its own try/except.
            ext_result = extractor.run(raise_on_error=True)
            elapsed = time.time() - t0
            stats = self._collect_stats(phase)
            pr = PhaseResult(
                phase=phase,
                label=label,
                elapsed=elapsed,
                ok=True,
                stats=stats,
            )
            self._print_phase_stats(pr)
            return pr
        except ExtractorError as exc:
            elapsed = time.time() - t0
            print(f"\n  [Pipeline stopped] Phase {phase} failed: {exc}")
            return PhaseResult(
                phase=phase,
                label=label,
                elapsed=elapsed,
                ok=False,
                error=str(exc.returncode),
            )

    def _find_discovered_records(self) -> Path | None:
        """
        Return the best discovered-records file for the current base schema.

        Preference order:
        1. A records file referenced by a discovery report whose
           ``pipeline_run.base_schema`` matches this pipeline's schema_id.
        2. Fallback to the newest discovered_records_*.json file in temp/.
        """
        # Newer discovery runs write report files that explicitly record which
        # base schema they were derived from. Use that when available to avoid
        # accidentally mixing discoveries from a different schema.
        matched_records: list[Path] = []
        for report_path in self._temp_dir.glob("discovered_field_report_*.json"):
            report = load_json(report_path)
            if not isinstance(report, dict):
                continue

            run_meta = report.get("pipeline_run", {})
            if not isinstance(run_meta, dict):
                continue
            if run_meta.get("base_schema") != self._schema_id:
                continue

            records_file = report.get("records_file")
            if not isinstance(records_file, str) or not records_file.strip():
                continue

            record_path = Path(records_file)
            if not record_path.is_absolute():
                # Older report paths may be relative to an unknown CWD.
                # Resolve by filename in this run's temp directory.
                record_path = self._temp_dir / record_path.name
            if record_path.exists():
                matched_records.append(record_path)

        if matched_records:
            return max(matched_records, key=lambda p: p.stat().st_mtime)

        return find_newest_glob(self._temp_dir, "discovered_records_*.json")

    def _run_phase_4(self) -> PhaseResult:
        """Phase 4 — assemble input files and call CSVExporter."""
        phase = 4
        label = self._PHASE_LABELS[phase]

        if self.config.start_at > 4:
            print(f"\n  [Skipping phase {phase}]")
            return PhaseResult(phase=phase, label=label, skipped=True)

        self._print_phase_banner(phase, label)

        # Always include merged records (the combined regex + LLM output from
        # Phases 1 and 2).  This is the primary structured dataset.
        input_files = [
            self._temp_dir / f"merged_records_{self._schema_id}.json"
        ]

        # Auto-include the most recent discovered records if they exist.
        # Discovered records are kept as a separate file rather than being
        # pre-merged into merged_records because they use a different JSON
        # schema: each record contains a "discovered_fields" dict with its own
        # value/confidence/provenance structure, whereas merged_records uses a
        # flat "fields" dict.  The CSVExporter (records_to_csv.py) understands
        # both schemas and stitches them into the correct columns itself; if we
        # merged them here we would lose the structural distinction and the
        # exporter would silently drop the discovered columns.
        disc = self._find_discovered_records()
        if disc:
            input_files.append(disc)
            print(f"  Including discovered records: {disc.name}")
        else:
            print(f"  No discovered records found — exporting base records only")

        # Prune missing files
        missing = [p for p in input_files if not p.exists()]
        if missing:
            print(f"  [Warning] Missing: {[p.name for p in missing]}")
        input_files = [p for p in input_files if p.exists()]

        if not input_files:
            print("  [Skipping phase 4 — no input files available]")
            return PhaseResult(phase=phase, label=label, skipped=True)

        output_csv = self.config.input_dir / "records.csv"
        exporter = CSVExporter(
            input_files=input_files,
            output_path=output_csv,
            sep=self.config.csv_sep,
            include_provenance=self.config.csv_provenance,
        )

        t0 = time.time()
        try:
            exporter.run(raise_on_error=True)
            elapsed = time.time() - t0
            stats = csv_fill_rate(output_csv)
            pr = PhaseResult(
                phase=phase, label=label, elapsed=elapsed, ok=True, stats=stats
            )
            self._print_phase_stats(pr)
            return pr
        except ExtractorError as exc:
            elapsed = time.time() - t0
            print(f"\n  [Pipeline stopped] Phase {phase} failed: {exc}")
            return PhaseResult(
                phase=phase, label=label, elapsed=elapsed, ok=False,
                error=str(exc.returncode),
            )

    def _run_phase_5(self) -> PhaseResult:
        """Phase 5 — codebook generation."""
        phase = 5
        label = self._PHASE_LABELS[phase]

        if self.config.start_at > 5:
            print(f"\n  [Skipping phase {phase}]")
            return PhaseResult(phase=phase, label=label, skipped=True)

        self._print_phase_banner(phase, label)
        records_csv = self.config.input_dir / "records.csv"
        gen = CodebookGenerator(
            schema_path=self.config.schema_path,
            records_csv=records_csv if records_csv.exists() else None,
            fmt=self.config.codebook_format,
            include_discovered=self.config.codebook_include_discovered,
        )

        t0 = time.time()
        try:
            gen.run(raise_on_error=True)
            elapsed = time.time() - t0
            return PhaseResult(phase=phase, label=label, elapsed=elapsed, ok=True)
        except ExtractorError as exc:
            elapsed = time.time() - t0
            print(f"\n  [Pipeline stopped] Phase {phase} failed: {exc}")
            return PhaseResult(
                phase=phase, label=label, elapsed=elapsed, ok=False,
                error=str(exc.returncode),
            )

    # ------------------------------------------------------------------
    # Stats collection
    # ------------------------------------------------------------------

    def _collect_stats(self, phase: int) -> dict:
        """Collect lightweight post-phase statistics without reimporting scripts."""
        # json is imported here (inside the method) rather than at the top of the
        # module to avoid a circular import: several modules in this package import
        # from pipeline.py at load time, and importing json at module level inside
        # those modules triggers re-entrant imports before the package is fully
        # initialised.  Deferring the import to call time is safe here because
        # _collect_stats is only ever called after a phase has successfully
        # completed, guaranteeing that the JSON files it reads already exist on disk.
        import json

        sid = self._schema_id
        td = self._temp_dir

        if phase == 1:
            meta_path = td / f"extraction_metadata_{sid}.json"
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
            total = meta.get("total_records_processed", 0)
            hits = meta.get("field_hit_counts", {})
            n_hit = sum(1 for v in hits.values() if v > 0)
            return {
                "records processed":  total,
                "fields with hits":   f"{n_hit}/{len(hits)}",
                "zero-coverage fields": len(hits) - n_hit,
            }

        if phase == 2:
            llm_path = td / f"llm_records_{sid}.json"
            merged_path = td / f"merged_records_{sid}.json"
            try:
                llm = json.loads(llm_path.read_text(encoding="utf-8"))
                merged = json.loads(merged_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
            # Count every non-null field value the LLM returned across all records.
            # This "fills" metric is a proxy for how much work the LLM actually did:
            # a high fill count relative to the number of LLM records means the LLM
            # was finding a lot of fields that regex missed; a low fill count suggests
            # that regex was already covering most of the schema and the LLM added
            # relatively little incremental value.
            fills = sum(
                1 for rec in llm
                for v in rec.get("fields", {}).values()
                if v is not None
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
                records = json.loads(disc_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
            field_hits: dict[str, int] = {}
            for rec in records:
                for fname, fdata in rec.get("discovered_fields", {}).items():
                    if fdata.get("values"):
                        field_hits[fname] = field_hits.get(fname, 0) + 1
            n = len(records)
            covered = sum(
                1 for rec in records
                if any(
                    fd.get("values")
                    for fd in rec.get("discovered_fields", {}).values()
                )
            )
            return {
                "fields discovered":     len(field_hits),
                "records with any hit":  f"{covered}/{n}",
                "coverage %":            f"{round(covered / n * 100, 1) if n else 0}%",
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
        if not cfg.run_discovery:
            print("  Skipping:  phase 3 (run_discovery=False)")

    @staticmethod
    def _print_phase_banner(phase: int, label: str) -> None:
        print("\n" + "=" * 60)
        print(f"  PHASE {phase}: {label}")
        print("=" * 60)

    @staticmethod
    def _print_phase_stats(pr: PhaseResult) -> None:
        if not pr.stats:
            return
        print(f"\n  -- Phase {pr.phase} stats ({pr.elapsed:.0f}s) " + "-" * 26)
        for k, v in pr.stats.items():
            print(f"  {k:<30} {v}")
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
