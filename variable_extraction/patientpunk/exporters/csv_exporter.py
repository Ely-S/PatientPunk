"""
patientpunk.exporters.csv_exporter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Flatten extraction records to a CSV file.

Wraps ``scripts/records_to_csv.py``.  Accepts one or more JSON record files
(e.g. merged_records, discovered_records) and merges records sharing the
same author + post into a single CSV row.

Output file
-----------
* ``{output_dir}/records.csv``  (default; override with *output_path*)

Example
-------
>>> exporter = CSVExporter(
...     input_files=[
...         Path("output/temp/merged_records_covidlonghaulers_v1.json"),
...         Path("output/temp/discovered_records_covidlonghaulers_v1.json"),
...     ],
...     output_path=Path("output/records.csv"),
... )
>>> result = exporter.run()
>>> print(f"CSV export done in {result.elapsed:.1f}s")
"""

from __future__ import annotations

from pathlib import Path

from .base import BaseExporter


class CSVExporter(BaseExporter):
    """
    Phase 4 -- flatten records to CSV.

    Parameters
    ----------
    input_files:
        One or more JSON record files.  Records with the same author + post
        are merged into a single row.
    output_path:
        Output CSV path.  Defaults to ``{first_input_dir}/records.csv``.
    sep:
        Separator for multi-value fields (default: ``" | "``).
    include_provenance:
        When *True*, add ``{field}__provenance`` and ``{field}__confidence``
        columns for every field.
    """

    _SCRIPT = "records_to_csv.py"

    def __init__(
        self,
        input_files: list[Path],
        output_path: Path | None = None,
        *,
        sep: str = " | ",
        include_provenance: bool = False,
    ) -> None:
        if not input_files:
            raise ValueError("CSVExporter requires at least one input file.")
        # Use the parent directory of the first input as the base so that
        # BaseExporter has a sensible input_dir / temp_dir.
        super().__init__(
            input_dir=input_files[0].parent,
            schema_path=None,
            temp_dir=None,
        )
        self.input_files = [Path(input_path) for input_path in input_files]
        self.output_path = Path(output_path) if output_path else None
        self.sep = sep
        self.include_provenance = include_provenance

    def _build_args(self) -> list[str]:
        args = ["--input"] + [str(input_path) for input_path in self.input_files]
        args += ["--sep", self.sep]
        if self.output_path:
            args += ["--output", str(self.output_path)]
        if self.include_provenance:
            args += ["--provenance"]
        return args
