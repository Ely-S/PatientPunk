"""
patientpunk.extractors.base
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Abstract base class for all extractors.

Each extractor wraps one of the legacy scripts in ``old/`` via a subprocess
call so the original battle-tested logic is preserved without modification.
Subclasses declare which script they delegate to and build the argument list;
this base class handles process execution, streaming output, and error
propagation.

Example
-------
>>> from patientpunk.extractors import BiomedicalExtractor
>>> extractor = BiomedicalExtractor(input_dir=Path("output"), schema_path=Path("schemas/covidlonghaulers_schema.json"))
>>> result = extractor.run()
>>> print(result.returncode, result.elapsed)
"""

from __future__ import annotations

import subprocess
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class ExtractorResult:
    """
    The outcome of a single extractor run.

    Attributes
    ----------
    returncode : int
        Process exit code — 0 indicates success.
    elapsed : float
        Wall-clock seconds the subprocess ran.
    args : list[str]
        The exact command that was executed (for logging / debugging).
    stdout : str | None
        Captured standard output when ``capture_output=True`` was used.
        *None* when output was streamed directly to the terminal.
    stderr : str | None
        Captured standard error when ``capture_output=True`` was used.
        *None* when output was streamed directly to the terminal.
    """

    returncode: int
    elapsed: float
    args: list[str] = field(default_factory=list, repr=False)
    stdout: str | None = field(default=None, repr=False)
    stderr: str | None = field(default=None, repr=False)

    @property
    def ok(self) -> bool:
        """True when the subprocess exited cleanly."""
        return self.returncode == 0


# ---------------------------------------------------------------------------
# Sentinel exception
# ---------------------------------------------------------------------------

class ExtractorError(RuntimeError):
    """Raised when an extractor subprocess exits with a non-zero status."""

    def __init__(self, extractor: str, returncode: int) -> None:
        super().__init__(
            f"{extractor} failed with exit code {returncode}."
        )
        self.extractor = extractor
        self.returncode = returncode


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseExtractor(ABC):
    """
    Abstract base class for PatientPunk extractors.

    Each extractor wraps one legacy script in ``old/`` via subprocess.
    Subclasses must set two things:

    1. ``_SCRIPT`` — the filename of the script in ``old/`` to delegate to.
    2. ``_build_args()`` — return the CLI arguments for that script.

    Example subclass::

        class BiomedicalExtractor(BaseExtractor):
            _SCRIPT = "extract_biomedical.py"

            def _build_args(self) -> list[str]:
                args = ["--input-dir", str(self.input_dir)]
                if self.schema_path:
                    args += ["--schema", str(self.schema_path)]
                return args

    The base class handles process execution, timing, error propagation,
    and optional output capture.

    Parameters
    ----------
    input_dir:
        Directory containing the corpus output from ``scrape_corpus.py``.
    schema_path:
        Optional path to an extension schema JSON file.
    temp_dir:
        Directory for intermediate output files.  Defaults to
        ``{input_dir}/temp/`` if not provided.
    """

    #: Filename of the legacy script in ``old/`` that this extractor delegates
    #: to.  Must be overridden by every concrete subclass.
    _SCRIPT: str = ""

    def __init__(
        self,
        input_dir: Path,
        schema_path: Path | None = None,
        temp_dir: Path | None = None,
    ) -> None:
        self.input_dir = Path(input_dir)
        self.schema_path = Path(schema_path) if schema_path else None
        self.temp_dir = Path(temp_dir) if temp_dir else self.input_dir / "temp"

        # Resolve the script path relative to this file's package parent
        self._script_path: Path = (
            Path(__file__).parent.parent.parent / "old" / self._SCRIPT
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(
        self,
        raise_on_error: bool = True,
        capture_output: bool = False,
    ) -> ExtractorResult:
        """
        Execute the extractor subprocess.

        Parameters
        ----------
        raise_on_error:
            When *True* (the default), raise :exc:`ExtractorError` if the
            process exits with a non-zero code.  Set to *False* to inspect
            the return code yourself.
        capture_output:
            When *True*, capture stdout and stderr instead of streaming them
            to the terminal.  The captured text is available on the returned
            :class:`ExtractorResult` as ``.stdout`` and ``.stderr``.  Useful
            for programmatic log capture in notebooks or automated pipelines.
            Default: *False* (output streams to terminal for interactive use).

        Returns
        -------
        ExtractorResult
        """
        cmd = self._full_command()
        t0 = time.time()
        proc = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=capture_output,        # decode bytes→str when capturing
        )
        elapsed = time.time() - t0

        result = ExtractorResult(
            returncode=proc.returncode,
            elapsed=elapsed,
            args=cmd,
            stdout=proc.stdout if capture_output else None,
            stderr=proc.stderr if capture_output else None,
        )

        if raise_on_error and not result.ok:
            raise ExtractorError(
                extractor=self.__class__.__name__,
                returncode=proc.returncode,
            )

        return result

    # ------------------------------------------------------------------
    # Template methods
    # ------------------------------------------------------------------

    @abstractmethod
    def _build_args(self) -> list[str]:
        """
        Return the *extra* CLI arguments for this extractor (not including
        the interpreter or the script path — those are added automatically).
        """

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _full_command(self) -> list[str]:
        """Build the complete command list passed to :func:`subprocess.run`."""
        return [sys.executable, str(self._script_path)] + self._build_args()

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"input_dir={str(self.input_dir)!r}, "
            f"schema={str(self.schema_path)!r})"
        )
