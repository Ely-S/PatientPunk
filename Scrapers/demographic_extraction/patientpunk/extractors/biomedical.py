"""
patientpunk.extractors.biomedical
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Regex-based biomedical extractor (Phase 1).

Wraps ``old/extract_biomedical.py``.  Fast, free, no API key required.
Matches 24 base fields plus any extension schema fields using hand-crafted
regex patterns.  Fields tagged ``source: llm_discovered`` are skipped here
and handled by :class:`~patientpunk.extractors.FieldDiscoveryExtractor`.

Output files (written to *temp_dir*)
--------------------------------------
* ``patientpunk_records_{schema_id}.json`` — per-record extraction results
* ``extraction_metadata_{schema_id}.json``  — field hit counts / summary

Example
-------
>>> extractor = BiomedicalExtractor(
...     input_dir=Path("output"),
...     schema_path=Path("schemas/covidlonghaulers_schema.json"),
... )
>>> result = extractor.run()
>>> print(f"Phase 1 done in {result.elapsed:.1f}s")
"""

from __future__ import annotations

from pathlib import Path

from .base import BaseExtractor


class BiomedicalExtractor(BaseExtractor):
    """
    Phase 1 — regex extraction.

    Parameters
    ----------
    input_dir:
        Directory containing the corpus (``subreddit_posts.json``, ``users/``).
    schema_path:
        Extension schema JSON (e.g. ``schemas/covidlonghaulers_schema.json``).
        When *None*, only base fields are extracted.
    temp_dir:
        Directory for intermediate output.  Defaults to ``{input_dir}/temp/``.
    """

    _SCRIPT = "extract_biomedical.py"

    def _build_args(self) -> list[str]:
        args = [
            "--input-dir", str(self.input_dir),
            "--temp-dir",  str(self.temp_dir),
        ]
        if self.schema_path:
            args += ["--schema", str(self.schema_path)]
        return args
