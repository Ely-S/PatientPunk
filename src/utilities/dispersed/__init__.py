"""Dispersed (https://api.dispersed.com) compute integration.

Three building blocks:
  - auth.py        : HMAC-SHA256 request signing for the Dispersed REST API
  - api_client.py  : Authenticated HTTP client for jobs / recipes / endpoints
  - llm_client.py  : Anthropic-interface wrapper around a vLLM-on-Dispersed
                     OpenAI-compatible endpoint, so llm_call() works unchanged

Provider selection happens in utilities/__init__.py via LLM_PROVIDER=dispersed.
"""
from utilities.dispersed.api_client import DispersedAPIClient, DispersedAPIError
from utilities.dispersed.auth import make_headers
from utilities.dispersed.llm_client import DispersedLLMClient

__all__ = [
    "DispersedAPIClient",
    "DispersedAPIError",
    "DispersedLLMClient",
    "make_headers",
]
