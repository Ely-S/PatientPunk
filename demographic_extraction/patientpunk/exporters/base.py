"""
patientpunk.exporters.base
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Abstract base class for all exporters.

Exporters follow the same subprocess-delegation pattern as extractors, so
this class is a thin specialisation of
:class:`~patientpunk.extractors.base.BaseExtractor` with an export-oriented
name and docstring.

The ``_SCRIPT`` class attribute and ``_build_args`` abstract method must be
defined by each concrete subclass.
"""

from __future__ import annotations

# Re-use the extractor base — the run / subprocess plumbing is identical.
from patientpunk.extractors.base import BaseExtractor, ExtractorError, ExtractorResult

__all__ = ["BaseExporter", "ExporterError", "ExporterResult"]

# Friendly type aliases so callers import from the exporters namespace.
ExporterResult = ExtractorResult
ExporterError = ExtractorError


class BaseExporter(BaseExtractor):
    """
    Abstract base for PatientPunk exporters.

    Inherits all subprocess-running machinery from
    :class:`~patientpunk.extractors.base.BaseExtractor`.  Subclasses need
    only set ``_SCRIPT`` and implement ``_build_args``.
    """
