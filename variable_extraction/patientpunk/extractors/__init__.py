from .base import BaseExtractor, ExtractorError, ExtractorResult
from .biomedical import BiomedicalExtractor
from .demographic_coder import DemographicCoder
from .demographics import DemographicsExtractor
from .llm import LLMExtractor

try:
    from .discovery import FieldDiscoveryExtractor
except ImportError:
    FieldDiscoveryExtractor = None  # discovery module is optional (separate PR)

__all__ = [
    "BaseExtractor",
    "ExtractorError",
    "ExtractorResult",
    "BiomedicalExtractor",
    "DemographicCoder",
    "DemographicsExtractor",
    "LLMExtractor",
    "FieldDiscoveryExtractor",
]
