"""
patientpunk.exporters.codebook
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Generate a data dictionary (codebook) from the extraction schema.

Wraps ``scripts/make_codebook.py``.  Produces a human-readable reference that
documents every field -- its description, confidence tier, ICD-10 code (where
applicable), data type, example values, and observed coverage percentage.

Output file
-----------
* ``{output_dir}/codebook.csv``  (default)
* ``{output_dir}/codebook.md``   (when *fmt="markdown"*)

Example
-------
>>> gen = CodebookGenerator(
...     schema_path=Path("schemas/covidlonghaulers_schema.json"),
...     records_csv=Path("output/records.csv"),
...     fmt="csv",
... )
>>> result = gen.run()
>>> print(f"Codebook done in {result.elapsed:.1f}s")
"""

from __future__ import annotations

from pathlib import Path

from .base import BaseExporter

# Default base schema location, resolved from PACKAGE_ROOT.
from .._utils import PACKAGE_ROOT
_DEFAULT_BASE_SCHEMA = PACKAGE_ROOT / "schemas" / "base_schema.json"


class CodebookGenerator(BaseExporter):
    """
    Phase 5 -- generate data dictionary / codebook.

    Parameters
    ----------
    schema_path:
        Extension schema JSON (required).
    base_schema_path:
        Base schema JSON.  Defaults to the ``schemas/base_schema.json``
        sibling of this package.
    records_csv:
        Records CSV produced by :class:`~patientpunk.exporters.CSVExporter`.
        When provided, adds coverage percentage and example values to every
        field entry.
    output_path:
        Output file path.  Defaults to ``../data/codebook.{csv|md}``.
    fmt:
        Output format -- ``"csv"`` (default) or ``"markdown"``.
    max_examples:
        Maximum example values to include per field (default: 5).
    sep:
        Multi-value separator used in the records CSV (default: ``" | "``).
    include_discovered:
        When *False*, exclude ``llm_discovered`` fields from the output.
    """

    _SCRIPT = "make_codebook.py"

    def __init__(
        self,
        schema_path: Path,
        base_schema_path: Path | None = None,
        *,
        records_csv: Path | None = None,
        output_path: Path | None = None,
        fmt: str = "csv",
        max_examples: int = 5,
        sep: str = " | ",
        include_discovered: bool = True,
    ) -> None:
        super().__init__(
            input_dir=Path(schema_path).parent,
            schema_path=schema_path,
            temp_dir=None,
        )
        self.base_schema_path = (
            Path(base_schema_path) if base_schema_path else _DEFAULT_BASE_SCHEMA
        )
        self.records_csv = Path(records_csv) if records_csv else None
        self.output_path = Path(output_path) if output_path else None
        self.fmt = fmt
        self.max_examples = max_examples
        self.sep = sep
        self.include_discovered = include_discovered

    def _build_args(self) -> list[str]:
        args = [
            "--schema",      str(self.schema_path),
            "--base-schema", str(self.base_schema_path),
            "--format",      self.fmt,
            "--examples",    str(self.max_examples),
            "--sep",         self.sep,
        ]
        if self.records_csv:
            args += ["--csv", str(self.records_csv)]
        if self.output_path:
            args += ["--output", str(self.output_path)]
        if not self.include_discovered:
            args += ["--no-discovered"]
        return args
