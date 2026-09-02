"""Extract same-post 7,8-DHF exposure fields into private external artifacts."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Literal

import typer
from pydantic import BaseModel, ConfigDict, Field, model_validator
from rich.console import Console

from studies.tropoflavin_nootropics.analyze_78dhf_predictors import (
    CohortInput,
    ReasonCategory,
)
from studies.tropoflavin_nootropics.comparator_support import sha256_file

REPO_ROOT = Path(__file__).resolve().parents[2]
VARIABLE_ROOT = REPO_ROOT / "variable_extraction"
if str(VARIABLE_ROOT) not in sys.path:
    sys.path.insert(0, str(VARIABLE_ROOT))

from patientpunk._utils import (  # noqa: E402
    check_response,
    get_llm_client,
    get_llm_usage_snapshot,
    llm_config,
    record_response_usage,
    response_text,
)
from patientpunk.pipeline import _git_commit  # noqa: E402

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()
DEFAULT_PROMPT = Path(__file__).resolve().parent / "prompts" / "78dhf_episode_v1.txt"
_WRITE_LOCK = Lock()
_AUTHOR_HASH = re.compile(r"^[0-9a-f]{32}$")
_SENTIMENTS = frozenset({"negative", "mixed", "neutral", "positive"})

DoseStatus = Literal["single", "multiple", "non_quantitative", "not_reported"]
DoseUnit = Literal["mcg", "mg", "g"]
RouteStatus = Literal["single", "multiple", "not_reported"]
RouteCategory = Literal[
    "oral mucosal",
    "swallowed oral",
    "nasal mucosal",
    "injection",
    "other explicit route",
]


class EpisodeExtractionConfig(BaseModel):
    """Validated input and private-output configuration."""

    model_config = ConfigDict(frozen=True)

    cohorts: tuple[CohortInput, ...] = Field(min_length=2)
    output_directory: Path
    prompt_path: Path = DEFAULT_PROMPT
    workers: int = Field(default=12, ge=1, le=32)
    batch_size: int = Field(default=8, ge=1, le=12)
    max_text_chars: int = Field(default=6_000, ge=500, le=20_000)
    max_output_tokens: int = Field(default=4_096, ge=512, le=8_192)

    @model_validator(mode="after")
    def validate_paths(self) -> EpisodeExtractionConfig:
        if not self.prompt_path.is_file():
            raise ValueError(f"Episode prompt not found: {self.prompt_path}")
        try:
            self.output_directory.resolve().relative_to(REPO_ROOT.resolve())
        except ValueError:
            pass
        else:
            raise ValueError("Episode extraction outputs must remain outside the repo")
        return self


class DoseValue(BaseModel):
    """One explicit per-administration mass or mass range."""

    model_config = ConfigDict(frozen=True)

    low: float = Field(gt=0)
    high: float = Field(gt=0)
    unit: DoseUnit

    @model_validator(mode="after")
    def validate_range(self) -> DoseValue:
        if self.high < self.low:
            raise ValueError("Dose high must be greater than or equal to dose low")
        return self

    @property
    def midpoint_mg(self) -> float:
        multiplier = {"mcg": 0.001, "mg": 1.0, "g": 1_000.0}[self.unit]
        return ((self.low + self.high) / 2) * multiplier


class EpisodeItemResult(BaseModel):
    """Validated model response for one opaque same-post episode."""

    model_config = ConfigDict(frozen=True)

    item_id: int = Field(ge=0)
    explicit_personal_use: bool
    dose_status: DoseStatus
    doses: tuple[DoseValue, ...]
    route_status: RouteStatus
    routes: tuple[RouteCategory, ...]
    reasons: tuple[ReasonCategory, ...]

    @model_validator(mode="after")
    def validate_fields(self) -> EpisodeItemResult:
        expected_doses = {
            "single": len(self.doses) == 1,
            "multiple": len(self.doses) >= 2,
            "non_quantitative": len(self.doses) == 0,
            "not_reported": len(self.doses) == 0,
        }[self.dose_status]
        if not expected_doses:
            raise ValueError("Dose status does not match extracted dose count")
        expected_routes = {
            "single": len(self.routes) == 1,
            "multiple": len(self.routes) >= 2,
            "not_reported": len(self.routes) == 0,
        }[self.route_status]
        if not expected_routes:
            raise ValueError("Route status does not match extracted route count")
        if len(self.routes) != len(set(self.routes)):
            raise ValueError("Route categories must be unique")
        if len(self.reasons) != len(set(self.reasons)):
            raise ValueError("Reason categories must be unique")
        dose_keys = {(dose.low, dose.high, dose.unit) for dose in self.doses}
        if len(dose_keys) != len(self.doses):
            raise ValueError("Dose values must be unique")
        if not self.explicit_personal_use and (
            self.dose_status != "not_reported"
            or self.route_status != "not_reported"
            or self.doses
            or self.routes
            or self.reasons
        ):
            raise ValueError("Non-personal reports cannot contain exposure fields")
        return self


class EpisodeBatchResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[EpisodeItemResult, ...]


class CachedEpisodeBatch(BaseModel):
    """Private response cache without source report text."""

    model_config = ConfigDict(frozen=True)

    schema_id: str = "tropoflavin_78dhf_episode_cache_v1"
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: str
    model: str
    items: tuple[EpisodeItemResult, ...]


class EpisodeRecord(BaseModel):
    """Private same-post extraction record."""

    model_config = ConfigDict(frozen=True)

    schema_id: str = "tropoflavin_78dhf_episode_record_v1"
    subreddit: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_]+$")
    author_hash: str = Field(pattern=r"^[0-9a-f]{32}$")
    post_id: str = Field(min_length=1)
    report_id: int = Field(ge=1)
    explicit_personal_use: bool
    dose_status: DoseStatus
    doses: tuple[DoseValue, ...]
    route_status: RouteStatus
    routes: tuple[RouteCategory, ...]
    reasons: tuple[ReasonCategory, ...]

    @model_validator(mode="after")
    def validate_extraction(self) -> EpisodeRecord:
        EpisodeItemResult(
            item_id=0,
            explicit_personal_use=self.explicit_personal_use,
            dose_status=self.dose_status,
            doses=self.doses,
            route_status=self.route_status,
            routes=self.routes,
            reasons=self.reasons,
        )
        return self


class UsageSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    requests: int = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class SourceDatabase(BaseModel):
    model_config = ConfigDict(frozen=True)

    subreddit: str
    database: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class EpisodeExtractionManifest(BaseModel):
    """Privacy-safe provenance for a completed same-post extraction."""

    model_config = ConfigDict(frozen=True)

    schema_id: str = "tropoflavin_78dhf_episode_manifest_v1"
    provider: str
    model: str
    code_commit: str
    prompt_file: str
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    max_text_chars: int
    max_output_tokens: int
    batch_size: int
    batch_sizes_used: tuple[int, ...] = ()
    source_databases: tuple[SourceDatabase, ...]
    source_episodes: int
    completed_episodes: int
    personal_use_episodes: int
    single_dose_episodes: int
    single_route_episodes: int
    missing_episodes: int
    failure_types: dict[str, int] = Field(default_factory=dict)
    records_file: str
    records_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    usage: UsageSummary
    completed_at: str


@dataclass(frozen=True)
class EpisodeContext:
    subreddit: str
    author_hash: str
    post_id: str
    report_id: int
    report_text: str


@dataclass(frozen=True)
class BatchItem:
    item_id: int
    context: EpisodeContext


def _connect_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _episode_contexts(
    cohort: CohortInput, max_text_chars: int
) -> tuple[EpisodeContext, ...]:
    with closing(_connect_readonly(cohort.database)) as connection:
        rows = connection.execute(
            """
            SELECT tr.report_id, tr.run_id, tr.post_id, tr.user_id, tr.sentiment,
                   TRIM(COALESCE(p.title, '') || CHAR(10) ||
                        COALESCE(p.body_text, '')) AS report_text
            FROM treatment_reports tr
            JOIN treatment t ON t.id = tr.drug_id
            JOIN posts p ON p.post_id = tr.post_id
            WHERE lower(t.canonical_name) = '7,8-dhf'
            ORDER BY tr.user_id, tr.post_id, tr.run_id, tr.report_id
            """
        ).fetchall()
    latest: dict[tuple[str, str], sqlite3.Row] = {}
    for row in rows:
        author = str(row["user_id"] or "").strip().lower()
        sentiment = str(row["sentiment"] or "")
        text = " ".join(str(row["report_text"] or "").split())
        if not _AUTHOR_HASH.fullmatch(author) or sentiment not in _SENTIMENTS or not text:
            continue
        key = (author, str(row["post_id"]))
        rank = (int(row["run_id"]), int(row["report_id"]))
        previous = latest.get(key)
        previous_rank = (
            (int(previous["run_id"]), int(previous["report_id"]))
            if previous is not None
            else None
        )
        if previous_rank is None or rank > previous_rank:
            latest[key] = row
    return tuple(
        EpisodeContext(
            subreddit=cohort.subreddit,
            author_hash=author,
            post_id=post_id,
            report_id=int(row["report_id"]),
            report_text=" ".join(str(row["report_text"] or "").split())[
                :max_text_chars
            ],
        )
        for (author, post_id), row in sorted(latest.items())
    )


def _request_payload(items: tuple[BatchItem, ...]) -> str:
    payload = {
        "items": [
            {"item_id": item.item_id, "report": item.context.report_text}
            for item in items
        ]
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _parse_response(text: str, expected_ids: tuple[int, ...]) -> EpisodeBatchResponse:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```")
        cleaned = cleaned.removesuffix("```").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Model response did not contain a JSON object")
    response = EpisodeBatchResponse.model_validate_json(cleaned[start : end + 1])
    actual_ids = tuple(item.item_id for item in response.items)
    if actual_ids != expected_ids:
        raise ValueError("Model response item IDs did not match the request")
    return response


def _cache_path(cache_root: Path, request_sha256: str) -> Path:
    return cache_root / request_sha256[:3] / f"{request_sha256}.json"


def _request_sha256(prompt_sha256: str, model: str, payload: str) -> str:
    material = f"{prompt_sha256}\n{model}\n{payload}".encode()
    return hashlib.sha256(material).hexdigest()


def _write_cache(path: Path, cache: CachedEpisodeBatch) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with _WRITE_LOCK:
        temporary.write_text(cache.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)


def _read_cached_batch(
    items: tuple[BatchItem, ...],
    prompt_sha256: str,
    provider: str,
    model: str,
    cache_root: Path,
) -> tuple[EpisodeItemResult, ...] | None:
    payload = _request_payload(items)
    request_sha256 = _request_sha256(prompt_sha256, model, payload)
    path = _cache_path(cache_root, request_sha256)
    if not path.is_file():
        return None
    cached = CachedEpisodeBatch.model_validate_json(path.read_text(encoding="utf-8"))
    expected_ids = tuple(item.item_id for item in items)
    actual_ids = tuple(item.item_id for item in cached.items)
    if (
        cached.request_sha256 != request_sha256
        or cached.prompt_sha256 != prompt_sha256
        or cached.provider != provider
        or cached.model != model
        or actual_ids != expected_ids
    ):
        return None
    return cached.items


def _read_cached_tree(
    items: tuple[BatchItem, ...],
    prompt_sha256: str,
    provider: str,
    model: str,
    cache_root: Path,
) -> tuple[EpisodeItemResult, ...] | None:
    cached = _read_cached_batch(items, prompt_sha256, provider, model, cache_root)
    if cached is not None or len(items) == 1:
        return cached
    midpoint = len(items) // 2
    left = _read_cached_tree(
        items[:midpoint], prompt_sha256, provider, model, cache_root
    )
    if left is None:
        return None
    right = _read_cached_tree(
        items[midpoint:], prompt_sha256, provider, model, cache_root
    )
    if right is None:
        return None
    combined = left + right
    payload = _request_payload(items)
    request_sha256 = _request_sha256(prompt_sha256, model, payload)
    _write_cache(
        _cache_path(cache_root, request_sha256),
        CachedEpisodeBatch(
            request_sha256=request_sha256,
            prompt_sha256=prompt_sha256,
            provider=provider,
            model=model,
            items=combined,
        ),
    )
    return combined


def _call_batch(
    client: Any,
    items: tuple[BatchItem, ...],
    prompt: str,
    prompt_sha256: str,
    provider: str,
    model: str,
    max_output_tokens: int,
    cache_root: Path,
) -> tuple[EpisodeItemResult, ...]:
    cached = _read_cached_batch(items, prompt_sha256, provider, model, cache_root)
    if cached is not None:
        return cached
    payload = _request_payload(items)
    request_sha256 = _request_sha256(prompt_sha256, model, payload)
    expected_ids = tuple(item.item_id for item in items)
    last_error: Exception | None = None
    for attempt, delay in enumerate((0, 2, 8), 1):
        if delay:
            time.sleep(delay)
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_output_tokens,
                temperature=0.0,
                system=prompt,
                messages=[{"role": "user", "content": payload}],
            )
            checked = check_response(response, model=model)
            record_response_usage(checked)
            parsed = _parse_response(response_text(checked), expected_ids)
            _write_cache(
                _cache_path(cache_root, request_sha256),
                CachedEpisodeBatch(
                    request_sha256=request_sha256,
                    prompt_sha256=prompt_sha256,
                    provider=provider,
                    model=model,
                    items=parsed.items,
                ),
            )
            return parsed.items
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt == 3:
                break
    raise RuntimeError("Episode extraction request failed after retries") from last_error


def _extract_with_split(
    client: Any,
    items: tuple[BatchItem, ...],
    prompt: str,
    prompt_sha256: str,
    provider: str,
    model: str,
    max_output_tokens: int,
    cache_root: Path,
) -> tuple[EpisodeItemResult, ...]:
    cached = _read_cached_tree(items, prompt_sha256, provider, model, cache_root)
    if cached is not None:
        return cached
    try:
        return _call_batch(
            client,
            items,
            prompt,
            prompt_sha256,
            provider,
            model,
            max_output_tokens,
            cache_root,
        )
    except RuntimeError:
        if len(items) == 1:
            raise
        midpoint = len(items) // 2
        combined = _extract_with_split(
            client,
            items[:midpoint],
            prompt,
            prompt_sha256,
            provider,
            model,
            max_output_tokens,
            cache_root,
        ) + _extract_with_split(
            client,
            items[midpoint:],
            prompt,
            prompt_sha256,
            provider,
            model,
            max_output_tokens,
            cache_root,
        )
        payload = _request_payload(items)
        request_sha256 = _request_sha256(prompt_sha256, model, payload)
        _write_cache(
            _cache_path(cache_root, request_sha256),
            CachedEpisodeBatch(
                request_sha256=request_sha256,
                prompt_sha256=prompt_sha256,
                provider=provider,
                model=model,
                items=combined,
            ),
        )
        return combined


def _chunks(
    items: tuple[BatchItem, ...], batch_size: int
) -> tuple[tuple[BatchItem, ...], ...]:
    return tuple(
        items[start : start + batch_size]
        for start in range(0, len(items), batch_size)
    )


def _resume_results(
    records_path: Path,
    manifest: EpisodeExtractionManifest,
    contexts: tuple[EpisodeContext, ...],
) -> dict[int, EpisodeItemResult]:
    if not records_path.is_file() or sha256_file(records_path) != manifest.records_sha256:
        return {}
    records_by_key: dict[tuple[str, str, str, int], EpisodeRecord] = {}
    for line in records_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parsed_record = EpisodeRecord.model_validate_json(line)
        key = (
            parsed_record.subreddit.casefold(),
            parsed_record.author_hash,
            parsed_record.post_id,
            parsed_record.report_id,
        )
        if key in records_by_key:
            raise ValueError("Prior episode records contain a duplicate source key")
        records_by_key[key] = parsed_record
    resumed: dict[int, EpisodeItemResult] = {}
    for item_id, context in enumerate(contexts):
        key = (
            context.subreddit.casefold(),
            context.author_hash,
            context.post_id,
            context.report_id,
        )
        resumed_record = records_by_key.get(key)
        if resumed_record is None:
            continue
        resumed[item_id] = EpisodeItemResult(
            item_id=item_id,
            explicit_personal_use=resumed_record.explicit_personal_use,
            dose_status=resumed_record.dose_status,
            doses=resumed_record.doses,
            route_status=resumed_record.route_status,
            routes=resumed_record.routes,
            reasons=resumed_record.reasons,
        )
    if len(resumed) != manifest.completed_episodes:
        raise ValueError("Prior episode manifest count does not match resumable records")
    return resumed


def run_episode_extraction(
    config: EpisodeExtractionConfig,
) -> EpisodeExtractionManifest:
    """Run or resume same-post extraction and write only private artifacts."""
    provider_config = llm_config()
    provider = str(provider_config["provider"])
    model = str(provider_config["model_fast"])
    if provider != "openrouter":
        raise ValueError("Episode extraction requires LLM_PROVIDER=openrouter")
    prompt = config.prompt_path.read_text(encoding="utf-8")
    prompt_sha256 = sha256_file(config.prompt_path)
    source_databases = tuple(
        SourceDatabase(
            subreddit=cohort.subreddit,
            database=cohort.database.name,
            sha256=sha256_file(cohort.database),
        )
        for cohort in config.cohorts
    )
    manifest_path = config.output_directory / "episode_manifest.json"
    previous_usage = UsageSummary(
        requests=0, prompt_tokens=0, completion_tokens=0, total_tokens=0
    )
    previous_manifest: EpisodeExtractionManifest | None = None
    if manifest_path.is_file():
        previous = EpisodeExtractionManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        if (
            previous.provider == provider
            and previous.model == model
            and previous.prompt_sha256 == prompt_sha256
            and previous.source_databases == source_databases
        ):
            previous_usage = previous.usage
            previous_manifest = previous

    contexts = tuple(
        context
        for cohort in config.cohorts
        for context in _episode_contexts(cohort, config.max_text_chars)
    )
    if len({(context.author_hash, context.post_id) for context in contexts}) != len(
        contexts
    ):
        raise ValueError("Source cohorts contain duplicate global author-post episodes")
    records_path = config.output_directory / "episode_records.jsonl"
    results_by_id = (
        _resume_results(records_path, previous_manifest, contexts)
        if previous_manifest is not None
        else {}
    )
    pending = tuple(
        BatchItem(item_id=item_id, context=context)
        for item_id, context in enumerate(contexts)
        if item_id not in results_by_id
    )
    effective_batch_size = 1 if results_by_id else config.batch_size
    batches = _chunks(pending, effective_batch_size)
    client = get_llm_client()
    cache_root = config.output_directory / "cache"
    failures: list[int] = []
    failure_types: Counter[str] = Counter()
    with ThreadPoolExecutor(max_workers=config.workers) as executor:
        futures = {
            executor.submit(
                _extract_with_split,
                client,
                batch,
                prompt,
                prompt_sha256,
                provider,
                model,
                config.max_output_tokens,
                cache_root,
            ): batch
            for batch in batches
        }
        completed = len(results_by_id)
        for future in as_completed(futures):
            batch = futures[future]
            try:
                results = future.result()
            except Exception as exc:  # noqa: BLE001
                failures.extend(item.item_id for item in batch)
                root = exc
                while root.__cause__ is not None:
                    root = root.__cause__
                failure_types[type(root).__name__] += len(batch)
            else:
                results_by_id.update((result.item_id, result) for result in results)
            completed += len(batch)
            if completed % 80 < len(batch) or completed == len(contexts):
                console.print(f"Processed {completed:,}/{len(contexts):,} episodes")

    records: list[EpisodeRecord] = []
    for item_id, context in enumerate(contexts):
        result = results_by_id.get(item_id)
        if result is None:
            continue
        records.append(
            EpisodeRecord(
                subreddit=context.subreddit,
                author_hash=context.author_hash,
                post_id=context.post_id,
                report_id=context.report_id,
                explicit_personal_use=result.explicit_personal_use,
                dose_status=result.dose_status,
                doses=result.doses,
                route_status=result.route_status,
                routes=result.routes,
                reasons=result.reasons,
            )
        )
    config.output_directory.mkdir(parents=True, exist_ok=True)
    records_path.write_text(
        "".join(record.model_dump_json() + "\n" for record in records),
        encoding="utf-8",
    )
    current_usage = UsageSummary.model_validate(get_llm_usage_snapshot())
    usage = UsageSummary(
        requests=previous_usage.requests + current_usage.requests,
        prompt_tokens=previous_usage.prompt_tokens + current_usage.prompt_tokens,
        completion_tokens=(
            previous_usage.completion_tokens + current_usage.completion_tokens
        ),
        total_tokens=previous_usage.total_tokens + current_usage.total_tokens,
    )
    prior_batch_sizes = (
        previous_manifest.batch_sizes_used
        if previous_manifest and previous_manifest.batch_sizes_used
        else ((previous_manifest.batch_size,) if previous_manifest else ())
    )
    manifest = EpisodeExtractionManifest(
        provider=provider,
        model=model,
        code_commit=_git_commit(),
        prompt_file=config.prompt_path.name,
        prompt_sha256=prompt_sha256,
        max_text_chars=config.max_text_chars,
        max_output_tokens=config.max_output_tokens,
        batch_size=config.batch_size,
        batch_sizes_used=tuple(dict.fromkeys((*prior_batch_sizes, effective_batch_size))),
        source_databases=source_databases,
        source_episodes=len(contexts),
        completed_episodes=len(records),
        personal_use_episodes=sum(record.explicit_personal_use for record in records),
        single_dose_episodes=sum(
            record.dose_status == "single" for record in records
        ),
        single_route_episodes=sum(
            record.route_status == "single" for record in records
        ),
        missing_episodes=len(contexts) - len(records),
        failure_types=dict(sorted(failure_types.items())),
        records_file=records_path.name,
        records_sha256=sha256_file(records_path),
        usage=usage,
        completed_at=datetime.now(UTC).isoformat(),
    )
    manifest_path.write_text(
        manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    if failures or manifest.missing_episodes:
        raise RuntimeError(
            f"Episode extraction incomplete: {manifest.missing_episodes} missing; "
            f"failure types: {manifest.failure_types}"
        )
    return manifest


@app.command()
def main(config_path: Path = typer.Option(..., exists=True, dir_okay=False)) -> None:
    """Extract same-post 7,8-DHF episode fields."""
    config = EpisodeExtractionConfig.model_validate_json(
        config_path.read_text(encoding="utf-8")
    )
    manifest = run_episode_extraction(config)
    console.print(
        f"[green]Complete[/green] {manifest.completed_episodes:,} episodes, "
        f"{manifest.usage.total_tokens:,} provider-reported tokens"
    )


if __name__ == "__main__":
    app()
