"""Generic planning and execution engine for second-pass probes.

Probe packages provide only three things:

* ``cohort.sql`` — a read-only query returning ``author_hash`` and ``target``;
* ``evidence.collect_windows`` — source retrieval and deterministic windows;
* ``claim.build_prompt(unit, *, variant, feedback)`` and ``claim.parse_claims``
  — domain prompt and schema. ``variant`` is the zero-based attempt index and
  ``feedback`` the previous validation error, so a retry can differ from the
  attempt that failed.

Everything else here is shared: identity, bounded units, private response
storage, mechanical validation, cache reuse, and resumable execution.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import sqlite3
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote as url_quote

from .models import (
    Attempt,
    AttemptStatus,
    Claim,
    CohortMember,
    ProbeRun,
    RunConfig,
    SourceWindow,
    Unit,
    UnitStatus,
    Usage,
)
from .store import ProbeStore, canonical_json, text_sha256


PLACEHOLDER_RE = re.compile(
    r"^\s*(not specified|unknown|none mentioned|n/?a|not available|unspecified)\s*$",
    re.IGNORECASE,
)
PROBE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
PARAGRAPH_RE = re.compile(r"\n{2,}")
MAX_PROVIDER_ATTEMPTS = 3
ERROR_LOG_LIMIT = 360
UNIT_KEY_LOG_CHARS = 12

# Which request settings each provider can actually carry. ``get_llm_client``
# routes "anthropic" and "openrouter" through the Anthropic SDK, which has no
# parameter to put any of these in; only the OpenAI-compatible adapter does.
# ``run_probe`` therefore builds the client from RunConfig.provider, not env
# LLM_PROVIDER. A setting that changes the answer must never be dropped.
PROVIDER_EXTRAS: dict[str, frozenset[str]] = {
    "openai": frozenset({"service_tier", "reasoning_effort", "provider_routing"}),
    "anthropic": frozenset(),
    "openrouter": frozenset(),
}


@dataclass(frozen=True)
class LoadedProbe:
    """Imported probe modules and their committed specification files."""

    name: str
    package_dir: Path
    cohort_sql: str
    evidence: Any
    claim: Any

    @property
    def spec_hash(self) -> str:
        """Hash the complete probe contract used to answer the question."""

        file_hashes = {}
        for filename in ("cohort.sql", "evidence.py", "claim.py"):
            path = self.package_dir / filename
            file_hashes[filename] = hashlib.sha256(path.read_bytes()).hexdigest()
        return _sha256({"probe": self.name, "files": file_hashes})


@dataclass(frozen=True)
class PlanResult:
    """The immutable run identity and its planned private units."""

    run: ProbeRun
    members: list[CohortMember]
    units: list[Unit]
    reused: bool = False


@dataclass(frozen=True)
class RunResult:
    """Small public summary of a resumable execution."""

    run_id: str
    attempted_units: int
    completed_units: int
    failed_units: int
    cache_hits: int


def _sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_probe(name: str) -> LoadedProbe:
    """Load a probe's SQL, evidence adapter, and claim adapter."""

    if not PROBE_NAME_RE.fullmatch(name):
        raise ValueError(f"invalid probe name: {name!r}")
    package = importlib.import_module(f"probes.{name}")
    package_dir = Path(package.__file__).resolve().parent
    sql_path = package_dir / "cohort.sql"
    if not sql_path.is_file():
        raise FileNotFoundError(f"probe is missing cohort.sql: {sql_path}")
    evidence = importlib.import_module(f"probes.{name}.evidence")
    claim = importlib.import_module(f"probes.{name}.claim")
    return LoadedProbe(
        name=name,
        package_dir=package_dir,
        cohort_sql=sql_path.read_text(encoding="utf-8"),
        evidence=evidence,
        claim=claim,
    )


def read_only_connection(path: Path) -> sqlite3.Connection:
    """Open SQLite read-only and reject write operations at the authorizer.

    Shared with probe evidence adapters: every database a probe reads is an
    input, so no probe should be able to write one even by accident.
    """

    if not path.is_file():
        raise FileNotFoundError(path)
    uri = f"file:{url_quote(str(path.resolve()), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.execute("PRAGMA query_only = ON")

    def deny_writes(action: int, *_: object) -> int:
        writes = {
            sqlite3.SQLITE_CREATE_INDEX,
            sqlite3.SQLITE_CREATE_TABLE,
            sqlite3.SQLITE_CREATE_TEMP_INDEX,
            sqlite3.SQLITE_CREATE_TEMP_TABLE,
            sqlite3.SQLITE_CREATE_TEMP_TRIGGER,
            sqlite3.SQLITE_CREATE_TEMP_VIEW,
            sqlite3.SQLITE_CREATE_TRIGGER,
            sqlite3.SQLITE_CREATE_VIEW,
            sqlite3.SQLITE_DELETE,
            sqlite3.SQLITE_DROP_INDEX,
            sqlite3.SQLITE_DROP_TABLE,
            sqlite3.SQLITE_DROP_TEMP_INDEX,
            sqlite3.SQLITE_DROP_TEMP_TABLE,
            sqlite3.SQLITE_DROP_TEMP_TRIGGER,
            sqlite3.SQLITE_DROP_TEMP_VIEW,
            sqlite3.SQLITE_DROP_TRIGGER,
            sqlite3.SQLITE_DROP_VIEW,
            sqlite3.SQLITE_INSERT,
            sqlite3.SQLITE_UPDATE,
            sqlite3.SQLITE_ALTER_TABLE,
            sqlite3.SQLITE_ATTACH,
            sqlite3.SQLITE_DETACH,
        }
        return sqlite3.SQLITE_DENY if action in writes else sqlite3.SQLITE_OK

    connection.set_authorizer(deny_writes)
    return connection


def _validate_cohort_sql(sql: str) -> str:
    """Allow one SELECT/CTE statement and reject statement concatenation."""

    statement = sql.strip()
    if statement.endswith(";"):
        statement = statement[:-1].rstrip()
    if not statement or ";" in statement:
        raise ValueError("cohort.sql must contain one SQL statement")
    if not re.match(r"^(?:SELECT|WITH)\b", statement, re.IGNORECASE):
        raise ValueError("cohort.sql must be a SELECT or WITH ... SELECT")
    return statement


def resolve_cohort(path: Path, sql: str) -> list[CohortMember]:
    """Execute and normalize a read-only cohort query."""

    statement = _validate_cohort_sql(sql)
    connection = read_only_connection(path)
    try:
        cursor = connection.execute(statement)
        columns = [description[0].lower() for description in cursor.description or ()]
        if "author_hash" not in columns:
            raise ValueError("cohort query must return author_hash")
        unexpected = set(columns) - {"author_hash", "target"}
        if unexpected:
            raise ValueError(f"cohort query returned unexpected columns: {sorted(unexpected)}")
        author_index = columns.index("author_hash")
        target_index = columns.index("target") if "target" in columns else None
        members = []
        for row in cursor.fetchall():
            author_hash = str(row[author_index] or "").strip()
            if not author_hash:
                raise ValueError("cohort query returned an empty author_hash")
            target = (
                str(row[target_index]).strip() if target_index is not None and row[target_index] else None
            )
            members.append(CohortMember(author_hash=author_hash, target=target))
    finally:
        connection.close()

    members.sort(key=lambda member: (member.author_hash, member.target or ""))
    keys = [(member.author_hash, member.target) for member in members]
    if len(keys) != len(set(keys)):
        raise ValueError("cohort query returned duplicate author_hash/target rows")
    return members


def _collect_windows(
    probe: LoadedProbe,
    source_db: Path,
    members: list[CohortMember],
    evidence_config: dict[str, Any],
) -> dict[tuple[str, str | None], list[SourceWindow]]:
    """Call the probe's evidence adapter and normalize its window objects."""

    collector = getattr(probe.evidence, "collect_windows", None)
    if collector is None:
        raise AttributeError(f"probe {probe.name!r} must define evidence.collect_windows")
    raw = collector(source_db, members, config=evidence_config)
    if not isinstance(raw, dict):
        raise TypeError("evidence.collect_windows must return a mapping")
    windows: dict[tuple[str, str | None], list[SourceWindow]] = {}
    for member in members:
        key = (member.author_hash, member.target)
        values = raw.get(key, raw.get(member.author_hash, []))
        windows[key] = [SourceWindow.model_validate(value) for value in values]
    return windows


def _split_text(text: str, max_chars: int) -> list[str]:
    """Cut text into <= max_chars pieces, preferring paragraph boundaries."""

    pieces: list[str] = []
    current = ""
    for paragraph in PARAGRAPH_RE.split(text):
        if not paragraph:
            continue
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            pieces.append(current)
            current = ""
        if len(paragraph) <= max_chars:
            current = paragraph
            continue
        # A single paragraph over budget has no boundary to respect.
        for start in range(0, len(paragraph), max_chars):
            current = paragraph[start : start + max_chars]
            if len(current) == max_chars:
                pieces.append(current)
                current = ""
    if current:
        pieces.append(current)
    return pieces


def _split_window(window: SourceWindow, max_chars: int) -> list[SourceWindow]:
    """Divide an oversized window rather than abandoning the whole plan.

    One long post must not cost a run every other unit. Parts are content
    addressed like any other window, so replanning reproduces the same ids.
    """

    if len(window.text) <= max_chars:
        return [window]
    pieces = _split_text(window.text, max_chars)
    return [
        SourceWindow(
            source_window_id=_sha256(
                {
                    "parent": window.source_window_id,
                    "part": index,
                    "text_sha256": text_sha256(piece),
                }
            ),
            source_type=window.source_type,
            source_id=window.source_id,
            text=piece,
        )
        for index, piece in enumerate(pieces)
    ]


def _build_units(
    probe: LoadedProbe,
    members: list[CohortMember],
    windows_by_member: dict[tuple[str, str | None], list[SourceWindow]],
    *,
    config: RunConfig,
    max_chars: int,
) -> list[Unit]:
    """Pack each member's evidence windows without crossing member boundaries.

    ``max_chars`` bounds the source text a unit carries, not the rendered
    prompt: the schema and preamble a probe adds are its own budget.
    """

    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    build_prompt = getattr(probe.claim, "build_prompt", None)
    if build_prompt is None:
        raise AttributeError(f"probe {probe.name!r} must define claim.build_prompt")
    units: list[Unit] = []
    for member in members:
        windows = windows_by_member[(member.author_hash, member.target)]
        batches: list[list[SourceWindow]] = []
        batch: list[SourceWindow] = []
        batch_chars = 0
        for window in windows:
            for part in _split_window(window, max_chars):
                size = len(part.text)
                if batch and batch_chars + size > max_chars:
                    batches.append(batch)
                    batch = []
                    batch_chars = 0
                batch.append(part)
                batch_chars += size
        if batch:
            batches.append(batch)

        for batch_index, batch_windows in enumerate(batches):
            provisional = Unit(
                unit_key="pending",
                author_hash=member.author_hash,
                target=member.target,
                windows=batch_windows,
                character_count=sum(len(window.text) for window in batch_windows),
            )
            # Identity is always the first-attempt prompt: a retry asks the same
            # question, so retry wording must not change what the unit is.
            system, prompt = build_prompt(provisional, variant=0, feedback=None)
            identity = {
                "author_hash": member.author_hash,
                "target": member.target,
                "batch_index": batch_index,
                "windows": [
                    {
                        "source_window_id": window.source_window_id,
                        "source_type": window.source_type,
                        "source_id": window.source_id,
                        "text_sha256": text_sha256(window.text),
                    }
                    for window in batch_windows
                ],
                "system": system,
                "prompt": prompt,
                "request": config.model_dump(mode="json"),
            }
            units.append(
                Unit(
                    unit_key=_sha256(identity),
                    author_hash=member.author_hash,
                    target=member.target,
                    windows=batch_windows,
                    character_count=provisional.character_count,
                )
            )
    return sorted(units, key=lambda unit: unit.unit_key)


def _build_run(
    probe: LoadedProbe,
    members: list[CohortMember],
    units: list[Unit],
    *,
    source_fingerprint: str,
    config: RunConfig,
) -> ProbeRun:
    cohort_hash = _sha256([member.model_dump(mode="json") for member in members])
    unit_set_hash = _sha256([unit.unit_key for unit in units])
    run_id = _sha256(
        {
            "probe_spec": probe.spec_hash,
            "cohort_hash": cohort_hash,
            "source_fingerprint": source_fingerprint,
            "unit_set_hash": unit_set_hash,
            "config": config.model_dump(mode="json"),
        }
    )
    return ProbeRun(
        run_id=run_id,
        probe=probe.name,
        spec_hash=probe.spec_hash,
        cohort_hash=cohort_hash,
        source_fingerprint=source_fingerprint,
        unit_set_hash=unit_set_hash,
        config=config,
        created_at=datetime.now(timezone.utc),
    )


def plan_probe(
    probe_name: str,
    *,
    cohort_db: Path,
    source_db: Path,
    output_db: Path | None = None,
    config: RunConfig,
    max_chars: int = 6_000,
) -> PlanResult:
    """Resolve a cohort and persist a no-provider execution plan."""

    validate_config(config)
    probe = load_probe(probe_name)
    members = resolve_cohort(cohort_db, probe.cohort_sql)
    evidence_config = dict(config.evidence_config)
    windows = _collect_windows(probe, source_db, members, evidence_config)
    units = _build_units(
        probe,
        members,
        windows,
        config=config,
        max_chars=max_chars,
    )
    # Content, not location: moving the source database must not mint a new run
    # identity and orphan the work already done against it.
    source_fingerprint = _sha256(
        {
            "source_sha256": _sha256_file(source_db),
            "windows": {
                f"{author}:{target}": [
                    window.model_dump(mode="json")
                    for window in member_windows
                ]
                for (author, target), member_windows in windows.items()
            },
        }
    )
    run = _build_run(
        probe,
        members,
        units,
        source_fingerprint=source_fingerprint,
        config=config,
    )
    db_path = output_db or ProbeStore.default_path(probe_name)
    with ProbeStore(db_path) as store:
        if store.has_probe_run(run.run_id):
            return PlanResult(run, members, store.load_units(run.run_id), reused=True)
        store.save_probe_run(run)
        store.save_cohort_members(run.run_id, members)
        store.save_units(run.run_id, units)
    return PlanResult(run, members, units)


def _reject_placeholders(value: Any, path: str = "values") -> None:
    """Reject placeholder strings anywhere in a claim's domain payload."""

    if isinstance(value, str):
        if PLACEHOLDER_RE.fullmatch(value):
            raise ValueError(f"{path}: placeholder value is forbidden")
    elif isinstance(value, dict):
        for key, child in value.items():
            _reject_placeholders(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_placeholders(child, f"{path}[{index}]")


def validate_claims(claims: list[Claim], unit: Unit) -> list[Claim]:
    """Apply only probe-agnostic mechanical claim checks."""

    windows = {window.source_window_id for window in unit.windows}
    claim_ids: set[str] = set()
    fingerprints: set[str] = set()
    normalized: list[Claim] = []
    for index, claim in enumerate(claims):
        claim = Claim.model_validate(claim)
        if claim.unit_key != unit.unit_key:
            raise ValueError(f"claims[{index}]: unit_key does not belong to unit")
        if claim.source_window_id not in windows:
            raise ValueError(f"claims[{index}]: source window does not belong to unit")
        if claim.claim_id in claim_ids:
            raise ValueError(f"claims[{index}]: duplicate claim_id")
        claim_ids.add(claim.claim_id)
        _reject_placeholders(claim.values)
        fingerprint = _sha256(claim.model_dump(mode="json"))
        if fingerprint in fingerprints:
            raise ValueError(f"claims[{index}]: duplicate claim")
        fingerprints.add(fingerprint)
        normalized.append(claim)
    return normalized


def _usage(response: Any) -> Usage | None:
    raw = getattr(response, "usage", None)
    if raw is None:
        return None

    def value(*names: str) -> Any:
        for name in names:
            if isinstance(raw, dict) and name in raw:
                return raw[name]
            found = getattr(raw, name, None)
            if found is not None:
                return found
        return None

    details = value("completion_tokens_details", "output_tokens_details")
    reasoning = (
        details.get("reasoning_tokens")
        if isinstance(details, dict)
        else getattr(details, "reasoning_tokens", 0)
        if details is not None
        else 0
    )
    return Usage(
        input_tokens=value("prompt_tokens", "input_tokens") or 0,
        output_tokens=value("completion_tokens", "output_tokens") or 0,
        reasoning_tokens=reasoning or 0,
        provider_cost=value("cost"),
    )


def _request_key(
    config: RunConfig, system: str, prompt: str
) -> str:
    """Hash every request-affecting value, including provider extensions."""

    return _sha256(
        {
            "provider": config.provider,
            "base_url": config.base_url,
            "model": config.model,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "reasoning_effort": config.reasoning_effort,
            "service_tier": config.service_tier,
            "provider_routing": config.provider_routing,
            "system": system,
            "prompt": prompt,
        }
    )


def _requested_extras(config: RunConfig) -> dict[str, Any]:
    """Return only the optional request settings this config actually sets."""

    candidates = {
        "service_tier": config.service_tier,
        "reasoning_effort": config.reasoning_effort,
        "provider_routing": config.provider_routing or None,
    }
    return {name: value for name, value in candidates.items() if value}


def validate_config(config: RunConfig) -> RunConfig:
    """Refuse a config whose settings cannot reach the chosen provider.

    These values are hashed into the run identity and the cache key. Accepting
    one the transport will drop would record a run that never happened.
    """

    supported = PROVIDER_EXTRAS.get(config.provider)
    if supported is None:
        raise ValueError(
            f"unknown provider {config.provider!r}; expected one of "
            f"{sorted(PROVIDER_EXTRAS)}"
        )
    unsupported = sorted(set(_requested_extras(config)) - supported)
    if unsupported:
        raise ValueError(
            f"provider {config.provider!r} cannot send {unsupported}; these "
            "change the answer and must not be dropped silently"
        )
    return config


def _provider_kwargs(config: RunConfig, system: str, prompt: str) -> dict[str, Any]:
    """Build the Anthropic-shaped request, carrying every setting it declares."""

    return {
        "model": config.model,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
        **_requested_extras(validate_config(config)),
    }


def _duration(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


class _Progress:
    """Thread-safe stderr: durable failure lines plus an optional in-place bar.

    Writes to stderr so a run's stdout summary stays pipeable. The bar redraws
    in place only on a terminal; redirected to a file it prints one line per
    unit instead of a single line smeared with carriage returns. Failure lines
    always survive: on a TTY they replace the bar, then the bar is redrawn
    underneath, so a Ctrl-C still leaves the reasons on screen.
    """

    def __init__(self, total: int, *, bar: bool = True, width: int = 30) -> None:
        self._total = total
        self._bar = bar
        self._width = width
        self._done = 0
        self._failed = 0
        self._lock = threading.Lock()
        self._started = time.monotonic()
        self._tty = sys.stderr.isatty()
        self._line = ""

    def tick(self, success: bool) -> None:
        if not self._bar:
            return
        with self._lock:
            self._done += 1
            self._failed += not success
            elapsed = time.monotonic() - self._started
            rate = self._done / elapsed if elapsed else 0.0
            remaining = (self._total - self._done) / rate if rate else 0.0
            filled = self._width * self._done // self._total
            bar = "#" * filled + "." * (self._width - filled)
            self._line = (
                f"[{bar}] {self._done}/{self._total} "
                f"({self._done / self._total:.0%}) "
                f"failed={self._failed} "
                f"{rate * 60:.0f}/min "
                f"elapsed {_duration(elapsed)} eta {_duration(remaining)}"
            )
            finished = self._done >= self._total
            if self._tty:
                print(
                    f"\r{self._line}",
                    end="\n" if finished else "",
                    file=sys.stderr,
                    flush=True,
                )
            else:
                print(self._line, file=sys.stderr, flush=True)

    def note(self, message: str) -> None:
        """Print a durable line without letting the in-place bar eat it."""

        with self._lock:
            if self._bar and self._tty:
                print(f"\r\033[K{message}", file=sys.stderr, flush=True)
                if self._line:
                    print(f"\r{self._line}", end="", file=sys.stderr, flush=True)
            else:
                print(message, file=sys.stderr, flush=True)

    def close(self) -> None:
        """Finish an in-place bar so a later summary starts on its own line."""

        with self._lock:
            if self._bar and self._tty and self._line and self._done < self._total:
                print(file=sys.stderr, flush=True)


def _error_loc(parts: tuple[Any, ...]) -> str:
    path = ""
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}" if path else str(part)
    return path


def _format_error(error: BaseException, *, limit: int = ERROR_LOG_LIMIT) -> str:
    """One readable line: type plus the useful detail, not a schema dump."""

    try:
        from pydantic import ValidationError
    except ImportError:
        ValidationError = ()  # type: ignore[misc, assignment]

    if ValidationError and isinstance(error, ValidationError):
        try:
            details = error.errors(
                include_url=False, include_input=False, include_context=False
            )
        except TypeError:
            details = error.errors()
        parts = []
        for item in details[:3]:
            loc = _error_loc(tuple(item.get("loc", ())))
            msg = str(item.get("msg", "")).strip()
            parts.append(f"{loc}: {msg}" if loc else msg)
        extra = f" (+{len(details) - 3} more)" if len(details) > 3 else ""
        text = f"ValidationError ({len(details)}): {'; '.join(parts)}{extra}"
    else:
        text = f"{type(error).__name__}: {error}"
    text = " ".join(text.split())
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _attempt_fail_line(
    unit_key: str,
    *,
    variant: int,
    kind: str,
    error: BaseException,
    retrying: bool,
    cached: bool = False,
) -> str:
    action = "retry" if retrying else "FAIL"
    cache_mark = " cached" if cached else ""
    return (
        f"{action} unit={unit_key[:UNIT_KEY_LOG_CHARS]} "
        f"attempt={variant + 1}/{MAX_PROVIDER_ATTEMPTS}{cache_mark} "
        f"{kind} {_format_error(error)}"
    )


def _print_failure_summary(failures: list[str]) -> None:
    if not failures:
        return
    ranked = Counter(failures).most_common()
    print(f"failure summary: {len(failures)} units", file=sys.stderr)
    for message, count in ranked:
        print(f"  {count}  {message}", file=sys.stderr, flush=True)


def _is_transient(error: BaseException) -> bool:
    text = f"{type(error).__name__}: {error}".lower()
    return any(token in text for token in ("timeout", "connection", "429", "temporarily"))


def _process_unit(
    store: ProbeStore,
    run_id: str,
    unit: Unit,
    probe: LoadedProbe,
    parser: Any,
    config: RunConfig,
    get_client: Any,
    log: _Progress | None = None,
) -> tuple[bool, int, str | None]:
    """Run one unit's attempt ladder. Returns ``(success, cache_hits, last_error)``.

    Self-contained per unit, so units can be dispatched concurrently: every
    store write below is serialized by ProbeStore's lock, and no attempt state
    is shared between units.
    """

    store.set_unit_status(run_id, unit.unit_key, UnitStatus.RUNNING)
    cache_hits = 0
    success = False
    last_error: str | None = None
    feedback: str | None = None

    def emit_fail(
        error: BaseException,
        *,
        variant: int,
        kind: str,
        retrying: bool,
        cached: bool = False,
    ) -> str:
        formatted = _format_error(error)
        message = _attempt_fail_line(
            unit.unit_key,
            variant=variant,
            kind=kind,
            error=error,
            retrying=retrying,
            cached=cached,
        )
        if log is None:
            print(message, file=sys.stderr, flush=True)
        else:
            log.note(message)
        return formatted

    # This budget is per invocation. ``attempt_no`` is the append-only
    # storage ordinal, so a resumed unit gets a whole retry ladder
    # instead of inheriting an earlier run's exhaustion.
    for variant in range(MAX_PROVIDER_ATTEMPTS):
        system, prompt = probe.claim.build_prompt(
            unit, variant=variant, feedback=feedback
        )
        cache_key = _request_key(config, system, prompt)
        attempt_no = store.next_attempt_number(run_id, unit.unit_key)
        # Read the cache once. A stored body that fails validation fails
        # the same way on reread, and would consume the whole budget.
        cached = store.cached_response(cache_key) if variant == 0 else None
        response = None
        if cached is not None:
            raw = cached
            cache_hits += 1
            attempt = Attempt(
                unit_key=unit.unit_key,
                attempt_no=attempt_no,
                status=AttemptStatus.RECEIVED,
                response_body=raw,
                response_sha256=text_sha256(raw),
                cache_key=cache_key,
                cache_hit=True,
                recorded_at=datetime.now(timezone.utc),
            )
        else:
            client = get_client()
            try:
                response = client.messages.create(
                    **_provider_kwargs(config, system, prompt)
                )
                from patientpunk._utils import response_text

                raw = response_text(response)
                attempt = Attempt(
                    unit_key=unit.unit_key,
                    attempt_no=attempt_no,
                    status=AttemptStatus.RECEIVED,
                    response_body=raw,
                    response_sha256=text_sha256(raw),
                    cache_key=cache_key,
                    usage=_usage(response),
                    recorded_at=datetime.now(timezone.utc),
                )
            except Exception as error:
                error_usage = _usage(error)
                store.record_attempt(
                    run_id,
                    Attempt(
                        unit_key=unit.unit_key,
                        attempt_no=attempt_no,
                        status=AttemptStatus.TRANSPORT_FAILED,
                        cache_key=cache_key,
                        usage=error_usage,
                        billing_uncertain=error_usage is None,
                        error=f"{type(error).__name__}: {error}",
                        recorded_at=datetime.now(timezone.utc),
                    ),
                )
                retrying = _is_transient(error) and variant < MAX_PROVIDER_ATTEMPTS - 1
                last_error = emit_fail(
                    error, variant=variant, kind="transport", retrying=retrying
                )
                if not _is_transient(error):
                    break
                continue

        # Persist the raw response before check_response, JSON parsing,
        # or probe-specific validation can reject it.
        store.record_attempt(run_id, attempt)
        try:
            if response is not None:
                from patientpunk._utils import check_response, response_text

                check_response(response, config.model)
                raw = response_text(response)
            from patientpunk._utils import parse_json_response

            payload = parse_json_response(raw)
            if payload is None:
                raise ValueError("provider response did not contain valid JSON")
            claims = validate_claims(parser(payload, unit), unit)
            for claim in claims:
                store.save_claim(run_id, claim)
            store.update_attempt_status(
                run_id, unit.unit_key, attempt_no, AttemptStatus.ACCEPTED
            )
            store.set_unit_status(run_id, unit.unit_key, UnitStatus.COMPLETE)
            success = True
            last_error = None
            break
        except Exception as error:
            # Hand the failure to the next attempt so the retry differs
            # from the request that just failed.
            feedback = f"{type(error).__name__}: {error}"
            store.update_attempt_status(
                run_id,
                unit.unit_key,
                attempt_no,
                AttemptStatus.VALIDATION_FAILED,
                error=feedback,
            )
            retrying = variant < MAX_PROVIDER_ATTEMPTS - 1
            last_error = emit_fail(
                error,
                variant=variant,
                kind="validation",
                retrying=retrying,
                cached=cached is not None,
            )
    if not success:
        store.set_unit_status(run_id, unit.unit_key, UnitStatus.FAILED)
    return success, cache_hits, last_error


def run_probe(
    probe_name: str,
    *,
    cohort_db: Path | None = None,
    source_db: Path | None = None,
    output_db: Path | None = None,
    config: RunConfig | None = None,
    max_chars: int = 6_000,
    confirm_paid_run: bool = False,
    limit: int | None = None,
    run_id: str | None = None,
    workers: int = 1,
    progress: bool = False,
) -> RunResult:
    """Execute a planned run, resuming incomplete units transactionally.

    ``run_id`` resumes a persisted run directly. The cohort query, the evidence
    sweep, and the source checksum only rediscover an identity already on disk,
    and on a raw corpus that rediscovery is the expensive part of a resume.
    """

    if not confirm_paid_run:
        raise PermissionError("run requires --confirm-paid-run")
    db_path = output_db or ProbeStore.default_path(probe_name)
    if run_id is not None:
        with ProbeStore(db_path) as store:
            run = store.load_probe_run(run_id)
            if run is None:
                raise LookupError(f"no run {run_id!r} in {db_path}")
            units = store.load_units(run_id)
        # The stored config decides prompts and cache keys. A flag must not
        # re-aim a run that is already partly paid for.
        config = run.config
    else:
        if cohort_db is None or source_db is None:
            raise ValueError("run needs --cohort-db and --source-db, or --run-id")
        if config is None:
            raise ValueError("run needs a config")
        plan = plan_probe(
            probe_name,
            cohort_db=cohort_db,
            source_db=source_db,
            output_db=output_db,
            config=config,
            max_chars=max_chars,
        )
        run, units = plan.run, plan.units
    validate_config(config)
    probe = load_probe(probe_name)
    parser = getattr(probe.claim, "parse_claims", None)
    if parser is None:
        raise AttributeError(f"probe {probe_name!r} must define claim.parse_claims")
    if workers < 1:
        raise ValueError(f"workers must be at least 1, got {workers}")

    # Built once and shared: constructing a client per worker would multiply
    # connection pools. Deferred so a fully cached invocation still builds none.
    # Transport follows RunConfig, not env LLM_PROVIDER: extras such as
    # reasoning_effort are validated against config.provider, and a mismatched
    # SDK would reject them (or drop them) after the run identity was recorded.
    client_slot: list[Any] = [None]
    client_lock = threading.Lock()

    def get_client() -> Any:
        with client_lock:
            if client_slot[0] is None:
                from patientpunk._utils import get_llm_client

                client_slot[0] = get_llm_client(
                    provider=config.provider,
                    base_url=config.base_url,
                )
            return client_slot[0]

    completed = failed = cache_hits = 0
    with ProbeStore(db_path) as store:
        pending = [unit for unit in units if unit.status != UnitStatus.COMPLETE]
        if limit is not None:
            pending = pending[:limit]

        failures: list[str] = []
        fail_lock = threading.Lock()
        log = _Progress(len(pending), bar=progress) if pending else None

        def work(unit: Unit) -> tuple[bool, int]:
            outcome = _process_unit(
                store, run.run_id, unit, probe, parser, config, get_client, log
            )
            success, hits, last_error = outcome
            if not success and last_error:
                with fail_lock:
                    failures.append(last_error)
            if log is not None:
                log.tick(success)
            return success, hits

        try:
            if workers > 1 and len(pending) > 1:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    results = list(pool.map(work, pending))
            else:
                results = [work(unit) for unit in pending]
        except BaseException:
            if log is not None:
                log.close()
            _print_failure_summary(failures)
            raise
        _print_failure_summary(failures)

    for success, hits in results:
        completed += success
        failed += not success
        cache_hits += hits
    return RunResult(run.run_id, len(pending), completed, failed, cache_hits)


def _run_config(args: argparse.Namespace) -> RunConfig:
    from patientpunk._utils import resolve_llm_config

    active = resolve_llm_config()
    routing = json.loads(args.provider_routing) if args.provider_routing else {}
    evidence = json.loads(args.evidence_config) if args.evidence_config else {}
    return RunConfig(
        provider=args.provider or active["provider"],
        base_url=args.base_url or active["base_url"],
        model=args.model or active["model_strong"],
        temperature=(
            args.temperature
            if args.temperature is not None
            else active["temperature"]
        ),
        max_tokens=args.max_tokens,
        reasoning_effort=args.reasoning_effort,
        service_tier=args.service_tier or active["service_tier"],
        provider_routing=routing,
        evidence_config=evidence,
    )


def _add_common_arguments(
    parser: argparse.ArgumentParser, *, require_dbs: bool = True
) -> None:
    parser.add_argument("probe")
    parser.add_argument("--cohort-db", type=Path, required=require_dbs)
    parser.add_argument("--source-db", type=Path, required=require_dbs)
    parser.add_argument("--output-db", type=Path)
    parser.add_argument("--max-chars", type=int, default=6_000)
    parser.add_argument("--provider")
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--max-tokens", type=int, default=4_096)
    parser.add_argument("--reasoning-effort")
    parser.add_argument("--service-tier")
    parser.add_argument("--provider-routing")
    parser.add_argument("--evidence-config")


def build_parser() -> argparse.ArgumentParser:
    """Build the small V1 command surface."""

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan_parser = commands.add_parser("plan", help="resolve cohort and units without an LLM")
    _add_common_arguments(plan_parser)
    run_parser = commands.add_parser("run", help="execute a confirmed paid run")
    _add_common_arguments(run_parser, require_dbs=False)
    run_parser.add_argument("--confirm-paid-run", action="store_true")
    run_parser.add_argument("--limit", type=int)
    # Dispatch width only. Deliberately absent from RunConfig: it changes how
    # fast units are sent, never what is sent, so it must not move run_id.
    run_parser.add_argument("--workers", type=int, default=1)
    run_parser.add_argument(
        "--progress",
        action="store_true",
        help="draw a unit progress bar on stderr; failed attempts always log",
    )
    run_parser.add_argument(
        "--run-id", help="resume a persisted run without replanning it"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for ``python -m probes``."""

    args = build_parser().parse_args(argv)
    # A resumed run reads its config from the store, so building one from flags
    # would only invite a mismatch.
    config = None if getattr(args, "run_id", None) else _run_config(args)
    if args.command == "plan":
        result = plan_probe(
            args.probe,
            cohort_db=args.cohort_db,
            source_db=args.source_db,
            output_db=args.output_db,
            config=config,
            max_chars=args.max_chars,
        )
        print(
            f"planned run={result.run.run_id} members={len(result.members)} "
            f"units={len(result.units)} reused={result.reused}"
        )
        return 0
    result = run_probe(
        args.probe,
        cohort_db=args.cohort_db,
        source_db=args.source_db,
        output_db=args.output_db,
        config=config,
        max_chars=args.max_chars,
        confirm_paid_run=args.confirm_paid_run,
        limit=args.limit,
        run_id=args.run_id,
        workers=args.workers,
        progress=args.progress,
    )
    print(
        f"run={result.run_id} attempted={result.attempted_units} "
        f"completed={result.completed_units} failed={result.failed_units} "
        f"cache_hits={result.cache_hits}"
    )
    return 0 if result.failed_units == 0 else 1
