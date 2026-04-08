"""
patientpunk.extractors.llm
~~~~~~~~~~~~~~~~~~~~~~~~~~~
LLM-based gap-filling extractor (Phase 2).

Wraps ``scripts/llm_extract.py``.  Uses Claude Haiku to fill fields that regex
missed.  Designed to run *after* :class:`~patientpunk.extractors.BiomedicalExtractor`.
Merged results (regex + LLM) are written to ``merged_records_{schema_id}.json``.

Requires an Anthropic API key in ``variable_extraction/.env``.

Output files (written to *temp_dir*)
--------------------------------------
* ``llm_records_{schema_id}.json``      — raw LLM extractions
* ``llm_field_suggestions_{schema_id}.json`` — suggested new fields
* ``merged_records_{schema_id}.json``   — combined regex + LLM records

Example
-------
>>> extractor = LLMExtractor(
...     input_dir=Path("../data"),
...     schema_path=Path("schemas/covidlonghaulers_schema.json"),
...     workers=10,
...     skip_threshold=0.7,
... )
>>> result = extractor.run()
>>> print(f"Phase 2 done in {result.elapsed:.1f}s")
"""

from __future__ import annotations

from pathlib import Path

from .base import BaseExtractor


class LLMExtractor(BaseExtractor):
    """
    Phase 2 — LLM gap-filling with Claude Haiku.

    Parameters
    ----------
    input_dir:
        Directory containing the corpus and Phase 1 output.
    schema_path:
        Extension schema JSON.  When *None*, only base fields are targeted.
    temp_dir:
        Directory for intermediate output.  Defaults to ``{input_dir}/temp/``.
    workers:
        Number of concurrent API requests (default: 10).
    skip_threshold:
        Skip records where regex already found at least this fraction of
        fields (0.0–1.0, default: 0.7).  Set to 0.0 to process every record.
    focus_gaps:
        When *True* (the default), send a shorter prompt asking only about
        the fields regex missed.
    merge:
        When *True* (the default), combine LLM results with regex records.
    resume:
        When *True*, skip records already present in the LLM output file —
        useful for continuing a crashed run.
    limit:
        Process at most *limit* records (cost-control / testing).
    """

    _SCRIPT = "llm_extract.py"

    def __init__(
        self,
        input_dir: Path,
        schema_path: Path | None = None,
        temp_dir: Path | None = None,
        *,
        workers: int = 10,
        skip_threshold: float = 0.7,
        focus_gaps: bool = True,
        merge: bool = True,
        resume: bool = False,
        limit: int | None = None,
    ) -> None:
        super().__init__(input_dir, schema_path, temp_dir)
        self.workers = workers
        self.skip_threshold = skip_threshold
        self.focus_gaps = focus_gaps
        self.merge = merge
        self.resume = resume
        self.limit = limit

    def _build_args(self) -> list[str]:
        args = [
            "--input-dir",       str(self.input_dir),
            "--temp-dir",        str(self.temp_dir),
            "--workers",         str(self.workers),
            "--skip-threshold",  str(self.skip_threshold),
        ]
        if self.schema_path:
            args += ["--schema", str(self.schema_path)]
        if not self.focus_gaps:
            args += ["--no-focus-gaps"]
        if not self.merge:
            args += ["--no-merge"]
        if self.resume:
            args += ["--resume"]
        if self.limit is not None:
            args += ["--limit", str(self.limit)]
        return args
