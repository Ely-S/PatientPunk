"""
patientpunk
~~~~~~~~~~~
Python library for the PatientPunk biomedical extraction pipeline.

Public API
----------
Core data classes::

    from patientpunk import CorpusLoader, CorpusRecord
    from patientpunk import Schema, FieldDefinition

Extractors (each wraps a legacy script in ``old/``)::

    from patientpunk.extractors import BiomedicalExtractor   # Phase 1
    from patientpunk.extractors import LLMExtractor          # Phase 2
    from patientpunk.extractors import FieldDiscoveryExtractor  # Phase 3

Exporters::

    from patientpunk.exporters import CSVExporter            # Phase 4
    from patientpunk.exporters import CodebookGenerator      # Phase 5

Pipeline orchestrator::

    from patientpunk import Pipeline, PipelineConfig

Quick-start example::

    from pathlib import Path
    from patientpunk import Pipeline, PipelineConfig

    config = PipelineConfig(
        schema_path=Path("schemas/covidlonghaulers_schema.json"),
        input_dir=Path("output"),
        run_llm=True,
        run_discovery=False,   # skip the expensive discovery step
    )
    result = Pipeline(config).run()
    print(result.summary())
"""

from .corpus import CorpusLoader, CorpusRecord
from .schema import FieldDefinition, Schema
from .pipeline import Pipeline, PipelineConfig, PipelineResult, PhaseResult
from .extractors import DemographicsExtractor
from .qualitative_standards import (
    FIELD_DESIGN_STANDARDS,
    EXTRACTION_STANDARDS,
    DEMOGRAPHIC_STANDARDS,
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
    # Standalone extractors
    "DemographicsExtractor",
    # Qualitative coding standards (for use in custom prompts / notebooks)
    "FIELD_DESIGN_STANDARDS",
    "EXTRACTION_STANDARDS",
    "DEMOGRAPHIC_STANDARDS",
]

__version__ = "0.1.0"
