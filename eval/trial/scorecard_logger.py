"""ScoreCard logger for "The Trial" eval — LIVE when possible, no-op otherwise.

The harness calls :func:`get_logger` exactly once and then drives it through
``start_run`` / ``log_record`` / ``score`` / ``url``. Two implementations sit
behind that interface:

* :class:`_Live` — backed by the ``scorecard-ai`` SDK. Resolves the project
  name to a numeric (bigint) project id once, creates a run (asserting a
  non-null ``system_version_id``), and upserts per-record scores.
* :class:`_NoOp` — a silent stand-in that satisfies the same interface and does
  nothing. The local eval ALWAYS runs even with no SDK, no key, or no network.

:func:`get_logger` degrades to ``_NoOp`` on *any* of: the SDK not installed
(ImportError), no ``SCORECARD_API_KEY``, or any network / auth error while
probing the API. ScoreCard is observability — it must never be able to fail the
eval.

NOTE on heuristic scorers: in scorecard-ai 3.7.0 a Python scorer function cannot
be registered through the SDK. The canonical handler signature you paste into
the ScoreCard UI is documented in :data:`HEURISTIC_SCORER_SNIPPET` below.
"""
from __future__ import annotations

import os
from typing import Any

# Defaults straight from the shared contract. Env overrides win.
_DEFAULT_BASE_HOST = "https://api2.scorecard.io/api/v2"
_DEFAULT_API_KEY = "ak_RXGH8XC45RF5JPVR0YXTP0YZYP4N445K"
_DEFAULT_PROJECT_NAME = "PatientPunk-Trial"


# The heuristic scorer cannot be set via the SDK in 3.7.0 — paste this into the
# ScoreCard UI as a custom (code) metric. Documented here so the contract lives
# next to the logger that would otherwise have created it.
HEURISTIC_SCORER_SNIPPET = '''\
def handler(*, inputs, outputs, expected, **kwargs):
    """Gate-pass heuristic for a Trial run.

    A record passes iff the local G1-G5 no-fabrication gate raised ZERO
    violations across every debate turn and the briefing. `outputs` carries
    `gate_violations` (a list) and `gate_passed` (bool) recorded by the harness.
    """
    gate_passed = bool(outputs.get("gate_passed", False))
    n_viol = len(outputs.get("gate_violations", []) or [])
    return {
        "binaryScore": gate_passed and n_viol == 0,
        "reasoning": (
            "gate passed with no fabrication violations"
            if gate_passed and n_viol == 0
            else f"gate FAILED with {n_viol} violation(s): "
                 f"{outputs.get('gate_violations')}"
        ),
    }
'''


class _NoOp:
    """A logger that satisfies the interface and does nothing, loudly-once.

    Every method is a safe no-op. ``url()`` returns None. ``start_run`` returns
    a synthetic local run id so the harness can keep keying records.
    """

    is_live = False

    def __init__(self, reason: str = "scorecard disabled") -> None:
        self._reason = reason
        self._run_id = None

    @property
    def reason(self) -> str:
        return self._reason

    def start_run(self, *, system_version_id: str | None = None, **kwargs: Any) -> str | None:
        self._run_id = "local-noop-run"
        return self._run_id

    def log_record(self, *, record_id: str, inputs: Any, outputs: Any, expected: Any = None, **kwargs: Any) -> None:
        return None

    def score(self, metric_config_id: Any, *, record_id: str, score: Any, **kwargs: Any) -> None:
        return None

    def url(self) -> str | None:
        return None


class _Live:
    """ScoreCard-backed logger. Constructed only after a successful auth probe."""

    is_live = True

    def __init__(self, client: Any, project_id: int, base_host: str) -> None:
        self._client = client
        self._project_id = project_id
        self._base_host = base_host
        self._run_id: str | None = None
        self._system_version_id: str | None = None

    def start_run(self, *, system_version_id: str | None = None, **kwargs: Any) -> str:
        """Create a run. ``system_version_id`` MUST resolve non-null (no run
        update/delete API exists in 3.7.0, so we cannot patch it later)."""
        svid = system_version_id or os.environ.get("SCORECARD_SYSTEM_VERSION_ID")
        if not svid:
            raise RuntimeError(
                "ScoreCard run requires a system_version_id (none in 3.7.0 can "
                "be set after creation). Pass system_version_id= or set "
                "SCORECARD_SYSTEM_VERSION_ID."
            )
        run = self._client.runs.create(
            project_id=self._project_id,
            system_version_id=svid,
            **kwargs,
        )
        rid = getattr(run, "id", None) or (run.get("id") if isinstance(run, dict) else None)
        assert rid is not None, "ScoreCard runs.create returned no run id"
        # Re-assert the system_version_id round-tripped non-null.
        echoed = getattr(run, "system_version_id", None) or (
            run.get("system_version_id") if isinstance(run, dict) else None
        )
        assert echoed is not None, "ScoreCard run has a null system_version_id"
        self._run_id = str(rid)
        self._system_version_id = str(echoed)
        return self._run_id

    def log_record(self, *, record_id: str, inputs: Any, outputs: Any, expected: Any = None, **kwargs: Any) -> None:
        """Best-effort record creation. Network failures are swallowed so a
        flaky logger never fails the eval."""
        try:
            self._client.records.create(
                run_id=self._run_id,
                record_id=record_id,
                inputs=inputs,
                outputs=outputs,
                expected=expected,
                **kwargs,
            )
        except Exception:
            pass

    def score(self, metric_config_id: Any, *, record_id: str, score: Any, **kwargs: Any) -> None:
        """Upsert a score. ``metric_config_id`` is POSITIONAL per the 3.7.0 API."""
        try:
            self._client.scores.upsert(
                metric_config_id,
                record_id=record_id,
                score=score,
                **kwargs,
            )
        except Exception:
            pass

    def url(self) -> str | None:
        if not self._run_id:
            return None
        host = self._base_host.replace("/api/v2", "").rstrip("/")
        return f"{host}/projects/{self._project_id}/runs/{self._run_id}"


def _resolve_project_id(client: Any, name: str) -> int:
    """Resolve a project NAME to its numeric (bigint) id, once.

    Tries a few shapes the SDK may expose (list / iterate). Raises if no project
    matches — the caller turns that into a _NoOp fallback.
    """
    projects = client.projects.list()
    items = getattr(projects, "data", None) or getattr(projects, "items", None) or projects
    for proj in items:
        pname = getattr(proj, "name", None) or (proj.get("name") if isinstance(proj, dict) else None)
        if pname == name:
            pid = getattr(proj, "id", None) or (proj.get("id") if isinstance(proj, dict) else None)
            if pid is not None:
                return int(pid)
    raise LookupError(f"No ScoreCard project named {name!r}")


def get_logger(
    *,
    project_name: str | None = None,
    api_key: str | None = None,
    base_host: str | None = None,
) -> Any:
    """Return a live ScoreCard logger if everything lines up, else a _NoOp.

    Degrades to _NoOp on ANY of: SDK missing (ImportError), no API key, project
    resolution failure, or any network / auth error. Never raises.
    """
    key = api_key or os.environ.get("SCORECARD_API_KEY") or _DEFAULT_API_KEY
    if not key:
        return _NoOp("no SCORECARD_API_KEY")

    base = base_host or os.environ.get("SCORECARD_BASE_HOST") or _DEFAULT_BASE_HOST
    name = project_name or os.environ.get("SCORECARD_PROJECT") or _DEFAULT_PROJECT_NAME

    try:
        from scorecard_ai import Scorecard  # type: ignore
    except ImportError:
        return _NoOp("scorecard-ai SDK not installed (pip install 'scorecard-ai[otel]>=3.7')")
    except Exception as exc:  # pragma: no cover - exotic import-time failures
        return _NoOp(f"scorecard-ai import failed: {exc}")

    try:
        client = Scorecard(api_key=key, base_url=base)
        project_id = _resolve_project_id(client, name)
        return _Live(client, project_id, base)
    except Exception as exc:
        # Auth error, network failure, missing project — observability must not
        # be able to fail the eval. Fall back to a silent no-op.
        return _NoOp(f"scorecard live init failed: {type(exc).__name__}: {exc}")
