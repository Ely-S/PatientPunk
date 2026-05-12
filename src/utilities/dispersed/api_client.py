"""Authenticated HTTP client for the Dispersed REST API.

Wraps httpx with HMAC-SHA256 request signing (see auth.py). Exposes the
subset of endpoints we actually use:

  - list_jobs(recipe_uuid=..., status=...)
  - create_job(recipe_uuid, ...)        — POST /v1/jobs
  - get_job(uuid)                       — GET  /v1/jobs/{uuid}
  - wait_for_running(uuid, timeout)     — convenience poller
  - extract_endpoint(job)               — pull the inference URL from a job

The base URL is https://api.dispersed.com by default; overridable for tests.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from utilities.dispersed.auth import make_headers

log = logging.getLogger("pipeline")

DEFAULT_BASE_URL = "https://api.dispersed.com"

# Job statuses per the OpenAPI spec (jobs vs job-runs share most of these).
RUNNING_STATUSES = {"RUNNING"}
PENDING_STATUSES = {"PENDING", "ASSIGNED", "PREPARING"}
TERMINAL_FAIL_STATUSES = {"FAILED", "FAILING", "CANCELLED", "CANCELLING"}


class DispersedAPIError(RuntimeError):
    """Raised when the Dispersed API returns a non-2xx response."""

    def __init__(self, status_code: int, body: str, *, code: str | None = None):
        self.status_code = status_code
        self.body = body
        self.code = code
        super().__init__(f"Dispersed API {status_code}: {body[:300]}")


class DispersedAPIClient:
    """Minimal authenticated client for the Dispersed REST API.

    All requests carry the four signed headers from auth.make_headers().
    Bodies are JSON, encoded with sorted keys and no whitespace — the
    docs require the canonical form for signing, and we sign exactly what
    we send.
    """

    def __init__(
        self,
        public_key: str,
        secret_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ):
        if not public_key or not secret_key:
            raise ValueError("DispersedAPIClient requires public_key and secret_key")
        self._public_key = public_key
        self._secret_key = secret_key
        self._base_url = base_url.rstrip("/")
        # Allow injection of a pre-configured client for tests / mocking.
        self._http = http_client or httpx.Client(timeout=timeout)
        self._owns_http = http_client is None

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> "DispersedAPIClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # ── Core signed request ─────────────────────────────────────────────────
    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict | None = None,
        body: dict | None = None,
    ) -> Any:
        # Canonicalize the body the same way we sign it: sorted keys, no spaces.
        body_bytes = (
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
            if body is not None
            else b""
        )
        headers = make_headers(
            self._public_key, self._secret_key,
            method=method, path=path, query=query, body=body_bytes,
        )
        if body_bytes:
            headers["Content-Type"] = "application/json"

        url = f"{self._base_url}{path}"
        resp = self._http.request(
            method, url, params=query, content=body_bytes, headers=headers,
        )
        if resp.status_code >= 400:
            # Try to extract structured error code per the docs' shape.
            err_code = None
            try:
                err_body = resp.json()
                err_code = (err_body.get("error") or {}).get("code")
            except Exception:
                pass
            raise DispersedAPIError(resp.status_code, resp.text, code=err_code)
        if not resp.content:
            return None
        return resp.json()

    # ── Job endpoints ───────────────────────────────────────────────────────
    def list_jobs(
        self,
        *,
        recipe_uuid: str | None = None,
        status: str | list[str] | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """List jobs, optionally filtered by recipe and status."""
        query: dict = {"limit": str(limit)}
        if recipe_uuid:
            query["filter[recipe_uuid]"] = recipe_uuid
        if status:
            if isinstance(status, list):
                # Dispersed accepts comma-separated lists for multi-value filters
                # per the OpenAPI patterns we've seen.
                query["filter[status]"] = ",".join(status)
            else:
                query["filter[status]"] = status
        data = self._request("GET", "/v1/jobs", query=query)
        # Responses appear to be either {data: [...]} or a bare list — handle both.
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return data or []

    def create_job(
        self,
        recipe_uuid: str,
        *,
        task_type: str = "PERSISTENT",
        env: dict | None = None,
        extra: dict | None = None,
    ) -> dict:
        """Instantiate a new job from a recipe."""
        body: dict[str, Any] = {
            "recipe_uuid": recipe_uuid,
            "task_type": task_type,
        }
        if env:
            body["env"] = env
        if extra:
            body.update(extra)
        return self._request("POST", "/v1/jobs", body=body)

    def get_job(self, uuid: str) -> dict:
        return self._request("GET", f"/v1/jobs/{uuid}")

    # ── Convenience helpers ─────────────────────────────────────────────────
    @staticmethod
    def extract_endpoint(job: dict) -> str | None:
        """Best-effort: pull the inference URL out of a job's response.

        The Dispersed docs don't pin a single field for the public endpoint,
        so we try the most plausible shapes in order. If none match, return
        None and let the caller decide whether to wait or fail.
        """
        for key in ("endpoint_url", "public_url", "service_url", "url"):
            if (v := job.get(key)):
                return v
        # Nested shapes
        for parent in ("network", "container", "access"):
            if isinstance(p := job.get(parent), dict):
                for key in ("endpoint_url", "public_url", "service_url", "url"):
                    if (v := p.get(key)):
                        return v
                # host + port
                host = p.get("host") or p.get("public_host") or p.get("address")
                port = p.get("port") or p.get("public_port")
                if host and port:
                    return f"http://{host}:{port}"
        return None

    def wait_for_running(
        self,
        uuid: str,
        *,
        timeout: float = 600.0,
        poll_interval: float = 5.0,
    ) -> dict:
        """Poll job until it reaches RUNNING (or fails / times out).

        Returns the job dict once RUNNING. Raises DispersedAPIError if the job
        terminates in a failure state, TimeoutError if it doesn't start in time.
        """
        deadline = time.monotonic() + timeout
        last_status = None
        while time.monotonic() < deadline:
            job = self.get_job(uuid)
            status = (job.get("status") or "").upper()
            if status != last_status:
                log.info(f"Dispersed job {uuid[:8]}… status: {status}")
                last_status = status
            if status in RUNNING_STATUSES:
                return job
            if status in TERMINAL_FAIL_STATUSES:
                raise DispersedAPIError(
                    0, f"job {uuid} ended in status {status}", code="JOB_FAILED",
                )
            time.sleep(poll_interval)
        raise TimeoutError(
            f"Dispersed job {uuid} did not reach RUNNING within {timeout}s "
            f"(last status: {last_status})"
        )
