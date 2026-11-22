"""
patientpunk
~~~~~~~~~~~
Python library for the PatientPunk biomedical extraction pipeline.

Public API
----------
Core data classes::

    from patientpunk import CorpusLoader, CorpusRecord
    from patientpunk import Schema, FieldDefinition

Pipeline orchestrator (Phases 1–4: LLM → discovery → CSV → codebook)::

    from patientpunk import Pipeline, PipelineConfig

In-process phase functions (also used by Pipeline)::

    from patientpunk.llm_extract import run_llm_extract
    from patientpunk.discover import run_discovery
    from patientpunk.export_csv import run_export_csv
    from patientpunk.codebook import run_codebook

Quick-start example::

    from pathlib import Path
    from patientpunk import Pipeline, PipelineConfig

    config = PipelineConfig(
        schema_path=Path("schemas/covidlonghaulers_schema.json"),
        input_dir=Path("../output"),
        run_llm=True,
        discovery_mode=None,   # None=off; "auto"=full discovery; "review"=candidates only
    )
    result = Pipeline(config).run()
    print(result.summary())
"""

from .corpus import CorpusLoader, CorpusRecord
from .pipeline import Pipeline, PipelineConfig, PipelineResult, PhaseResult
from .qualitative_standards import (
    FIELD_DESIGN_STANDARDS,
    EXTRACTION_STANDARDS,
)
from .schema import FieldDefinition, Schema

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
    # Qualitative coding standards (for use in custom prompts / notebooks)
    "FIELD_DESIGN_STANDARDS",
    "EXTRACTION_STANDARDS",
]

__version__ = "0.1.0"
