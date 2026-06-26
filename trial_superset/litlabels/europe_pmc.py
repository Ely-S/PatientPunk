"""Europe PMC client for papers-as-labels.

Free, no auth, biomedical-specific. Indexes ~40M papers from PubMed, PMC,
preprint servers, and clinical-trial registries — and crucially cross-links
registry IDs (NCT/ISRCTN/EUCTR) to the publications that report them, which is
the join we need to attach an outcome to a results:without trial.

Docs: https://europepmc.org/RestfulWebService

------------------------------------------------------------------------
VENDORED + ADAPTED from
  AI_Scientist_Assistant/src/clients/europe_pmc.py
Changes vs upstream:
  - import `cache` locally (was `from src.lib import cache`)
  - generalized `search_for_lit_review` -> `search`
  - added `fulltext_xml()` (text, not JSON) for PMC primary-endpoint extraction
The pooled-client + exponential-backoff core is upstream's, unchanged.
------------------------------------------------------------------------
"""

from __future__ import annotations

import threading
import time
from typing import Any

import httpx

from . import cache

_BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"
_SEARCH_TTL = 7 * 24 * 3600   # registry->paper links are stable; cache a week
_FULLTEXT_TTL = 30 * 24 * 3600  # published full text doesn't change

_client: httpx.Client | None = None
_client_lock = threading.Lock()
_UA = "patientpunk-trial-superset/0.1 (research; papers-as-labels)"


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:  # re-check inside the lock
                _client = httpx.Client(timeout=30.0, headers={"User-Agent": _UA})
    return _client


def search(query: str, page_size: int = 25, result_type: str = "core") -> dict[str, Any]:
    """Search Europe PMC. Returns the raw response:
      {"resultList": {"result": [...]}, "hitCount": N, ...}

    For registry linking, pass a query like 'NCT06366724' (Europe PMC matches the
    trial number in metadata/full text). result_type 'core' includes abstract +
    authors; 'lite' omits them.
    """
    payload = {"query": query, "format": "json", "pageSize": page_size, "resultType": result_type}
    cached = cache.get("europe_pmc/search", payload, _SEARCH_TTL)
    if cached is not None:
        return cached
    body = _get_with_retry(f"{_BASE_URL}/search", payload)
    cache.put("europe_pmc/search", payload, body)
    return body


def fulltext_xml(source: str, ext_id: str) -> str | None:
    """Fetch JATS full-text XML for an open-access article, e.g.
    source='PMC', ext_id='PMC3258128'. Returns the XML string, or None if no
    full text is available (404). Used to read the primary-endpoint result.
    """
    payload = {"source": source, "ext_id": ext_id, "kind": "fullTextXML"}
    cached = cache.get("europe_pmc/fulltext", payload, _FULLTEXT_TTL)
    if cached is not None:
        return cached
    # EPMC full-text endpoint: /{pmcid}/fullTextXML (bare PMCID, NO /{source}/ segment).
    url = f"{_BASE_URL}/{ext_id}/fullTextXML"
    xml = _get_text_with_retry(url)
    if xml is not None:
        cache.put("europe_pmc/fulltext", payload, xml)
    return xml


def _get_with_retry(url: str, params: dict[str, Any], max_attempts: int = 4) -> dict[str, Any]:
    """GET returning JSON, with exponential backoff on 429 / 5xx (cap 8s)."""
    client = _get_client()
    delay = 2.0
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        is_last = attempt == max_attempts - 1
        try:
            response = client.get(url, params=params)
            if response.status_code == 429 or 500 <= response.status_code < 600:
                last_exc = httpx.HTTPStatusError(
                    f"HTTP {response.status_code}", request=response.request, response=response
                )
                if is_last:
                    break
                time.sleep(delay)
                delay = min(delay * 2, 8.0)
                continue
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as exc:
            last_exc = exc
            if is_last:
                break
            time.sleep(delay)
            delay = min(delay * 2, 8.0)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Europe PMC request failed after retries")


def _get_text_with_retry(url: str, max_attempts: int = 4) -> str | None:
    """GET returning text (full-text XML). 404 -> None (no OA full text)."""
    client = _get_client()
    delay = 2.0
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        is_last = attempt == max_attempts - 1
        try:
            response = client.get(url)
            if response.status_code == 404:
                return None
            if response.status_code == 429 or 500 <= response.status_code < 600:
                last_exc = httpx.HTTPStatusError(
                    f"HTTP {response.status_code}", request=response.request, response=response
                )
                if is_last:
                    break
                time.sleep(delay)
                delay = min(delay * 2, 8.0)
                continue
            response.raise_for_status()
            return response.text
        except httpx.RequestError as exc:
            last_exc = exc
            if is_last:
                break
            time.sleep(delay)
            delay = min(delay * 2, 8.0)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Europe PMC full-text request failed after retries")
