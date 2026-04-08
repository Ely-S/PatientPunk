"""
patientpunk
~~~~~~~~~~~
Python library for the PatientPunk biomedical extraction pipeline.

Public API
----------
Core data classes::

    from patientpunk import CorpusLoader, CorpusRecord
    from patientpunk import Schema, FieldDefinition

Extractors (each wraps an executable module in ``scripts/``)::

    from patientpunk.extractors import BiomedicalExtractor   # Phase 1
    from patientpunk.extractors import LLMExtractor          # Phase 2
    from patientpunk.extractors import FieldDiscoveryExtractor  # Phase 3

Exporters::

    from patientpunk.exporters import CSVExporter            # Phase 4
    from patientpunk.exporters import CodebookGenerator      # Phase 5

Pipeline orchestrator (Phases 1–5: regex → LLM → discovery → CSV → codebook)::

    from patientpunk import Pipeline, PipelineConfig

Standalone demographics (LLM-only, age/sex/location — no regex, no schema)::

    from patientpunk import DemographicsExtractor

.. note::

   **When to use Pipeline vs DemographicsExtractor:**

   * Use ``Pipeline`` when you want the full clinical picture — all 37+
     schema fields (conditions, medications, treatment outcomes, etc.)
     extracted via regex + LLM backfill.

   * Use ``DemographicsExtractor`` when you only need age, sex/gender,
     and location.  It is simpler, cheaper, and applies a strict
     self-reference constraint (only extracts what the author says about
     *themselves*).  Works especially well with full user posting
     histories, which yield 4–5x more demographic coverage than single
     posts.

Quick-start example::

    from pathlib import Path
    from patientpunk import Pipeline, PipelineConfig

    config = PipelineConfig(
        schema_path=Path("schemas/covidlonghaulers_schema.json"),
        input_dir=Path("../data"),
        run_llm=True,
        run_discovery=False,   # skip the expensive discovery step
    )
    result = Pipeline(config).run()
    print(result.summary())
"""

from .corpus import CorpusLoader, CorpusRecord
from .schema import FieldDefinition, Schema
from .pipeline import Pipeline, PipelineConfig, PipelineResult, PhaseResult
from .extractors import DemographicCoder, DemographicsExtractor
from .qualitative_standards import (
    FIELD_DESIGN_STANDARDS,
    EXTRACTION_STANDARDS,
    DEMOGRAPHIC_STANDARDS,
    INDUCTIVE_DEMOGRAPHIC_STANDARDS,
)

__all__ = [
    # Corpus
    "CorpusLoader",
    "CorpusRecord",
    # Schema
    "Schema",
    "FieldDefinition",
    # Pipeline
    "Pipeline",
    "PipelineConfig",
    "PipelineResult",
    "PhaseResult",
    # Demographic coding
    "DemographicCoder",           # inductive + deductive (primary)
    "DemographicsExtractor",      # deductive only (legacy)
    # Qualitative coding standards (for use in custom prompts / notebooks)
    "FIELD_DESIGN_STANDARDS",
    "EXTRACTION_STANDARDS",
    "DEMOGRAPHIC_STANDARDS",
    "INDUCTIVE_DEMOGRAPHIC_STANDARDS",
]

__version__ = "0.1.0"
