"""
patientpunk.extractors.discovery
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Multi-model field discovery pipeline (Phase 3).

Wraps ``scripts/discover_fields.py``.  Automatically discovers new biomedical
fields from patient-authored text using a two-model architecture:

* **Haiku** — fast, cheap: scans corpus for field candidates; fills gaps.
* **Sonnet** — precise: writes and validates regex patterns.

The four internal stages are:

1. (Haiku)  Scan corpus → discover field candidates with examples.
2. (Sonnet) For each candidate → write regex → test → iterate.
3. (regex)  Run validated patterns across the full corpus (free).
4. (Haiku)  Fill gaps where regex missed.

Requires an Anthropic API key in ``variable_extraction/.env``.

Output files
------------
* ``schemas/discovered_{timestamp}.json`` — or updates *schema_path* in-place.
* ``temp/discovered_records_{schema_id}.json`` — full extraction results.
* ``temp/discovered_field_report_{schema_id}.json`` — coverage stats.

Example
-------
>>> extractor = FieldDiscoveryExtractor(
...     input_dir=Path("../data"),
...     schema_path=Path("schemas/covidlonghaulers_schema.json"),
...     workers=10,
...     limit=20,
...     fill_gaps=False,
... )
>>> result = extractor.run()
>>> print(f"Phase 3 done in {result.elapsed:.1f}s")
"""

from __future__ import annotations

from pathlib import Path

from .base import BaseExtractor


class FieldDiscoveryExtractor(BaseExtractor):
    """
    Phase 3 — multi-model field discovery.

    Parameters
    ----------
    input_dir:
        Directory containing the corpus and prior extraction output.
    schema_path:
        Extension schema JSON.  Discovered fields are merged *into* this file;
        existing fields are never overwritten.  When *None*, a timestamped
        ``schemas/discovered_{ts}.json`` is created instead.
    temp_dir:
        Directory for intermediate output.  Defaults to ``{input_dir}/temp/``.
    workers:
        Concurrent API workers for Stage 1 and Stage 4 (default: 10).
    limit:
        Limit Stage 1 corpus scan to *N* records (cost-control).
    fill_gaps:
        When *False*, skip Stage 4 gap-filling (regex + discovery only).
    resume:
        When *True*, resume Stage 4 from an existing records file.
    candidates_file:
        Path to a saved ``phase1_candidates.json`` — skips Stage 1 entirely.
        If *None* and ``{temp_dir}/phase1_candidates.json`` exists, it is
        used automatically (the same auto-detect behaviour as ``run_pipeline.py``).
    sample:
        Randomly sample *N* corpus items for Stage 1 instead of using all
        (more representative than ``--limit``).
    per_item_chars:
        Max characters taken from each corpus item in Stage 1.  0 = full text.
    """

    _SCRIPT = "discover_fields.py"

    def __init__(
        self,
        input_dir: Path,
        schema_path: Path | None = None,
        temp_dir: Path | None = None,
        *,
        workers: int = 10,
        limit: int | None = None,
        fill_gaps: bool = True,
        resume: bool = False,
        candidates_file: Path | None = None,
        sample: int | None = None,
        per_item_chars: int = 0,
    ) -> None:
        super().__init__(input_dir, schema_path, temp_dir)
        self.workers = workers
        self.limit = limit
        self.fill_gaps = fill_gaps
        self.resume = resume
        self.candidates_file = Path(candidates_file) if candidates_file else None
        self.sample = sample
        self.per_item_chars = per_item_chars

    def _build_args(self) -> list[str]:
        args = [
            "--input-dir", str(self.input_dir),
            "--temp-dir",  str(self.temp_dir),
            "--workers",   str(self.workers),
        ]
        if self.schema_path:
            args += ["--schema", str(self.schema_path)]
        if self.limit is not None:
            args += ["--limit", str(self.limit)]
        if not self.fill_gaps:
            args += ["--no-fill"]
        if self.resume:
            args += ["--resume"]
        if self.candidates_file:
            args += ["--candidates", str(self.candidates_file)]
        elif self._auto_candidates():
            args += ["--candidates", str(self._auto_candidates())]
        if self.sample is not None:
            args += ["--sample", str(self.sample)]
        if self.per_item_chars:
            args += ["--per-item-chars", str(self.per_item_chars)]
        return args

    def _auto_candidates(self) -> Path | None:
        """Return the auto-detected Phase 1 candidates file, if it exists."""
        candidate = self.temp_dir / "phase1_candidates.json"
        return candidate if candidate.exists() else None
