"""Extract explicit reasons for 7,8-DHF use into private external artifacts."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

import typer
from pydantic import BaseModel, ConfigDict, Field, model_validator
from rich.console import Console

from studies.tropoflavin_nootropics.analyze_78dhf_predictors import (
    CohortInput,
    ReasonCategory,
    ReasonRecord,
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
DEFAULT_PROMPT = Path(__file__).resolve().parent / "prompts" / "78dhf_reason_v1.txt"
_WRITE_LOCK = Lock()
_AUTHOR_HASH = re.compile(r"^[0-9a-f]{32}$")


class ReasonExtractionConfig(BaseModel):
    """Validated input and external-output configuration."""

    model_config = ConfigDict(frozen=True)

    cohorts: tuple[CohortInput, ...] = Field(min_length=2)
    output_directory: Path
    prompt_path: Path = DEFAULT_PROMPT
    workers: int = Field(default=12, ge=1, le=32)
    batch_size: int = Field(default=6, ge=1, le=12)
    max_text_chars: int = Field(default=6_000, ge=500, le=20_000)
    max_output_tokens: int = Field(default=2_048, ge=512, le=8_192)

    @model_validator(mode="after")
    def validate_paths(self) -> ReasonExtractionConfig:
        if not self.prompt_path.is_file():
            raise ValueError(f"Reason prompt not found: {self.prompt_path}")
        try:
            self.output_directory.resolve().relative_to(REPO_ROOT.resolve())
        except ValueError:
            pass
        else:
            raise ValueError("Reason extraction outputs must remain outside the repo")
        return self


class ReasonItemResult(BaseModel):
    """Validated model response for one opaque batch item."""

    model_config = ConfigDict(frozen=True)

    item_id: int = Field(ge=0)
    explicit_reason_found: bool
    reasons: tuple[ReasonCategory, ...]

    @model_validator(mode="after")
    def validate_reasons(self) -> ReasonItemResult:
        if self.explicit_reason_found != bool(self.reasons):
            raise ValueError("explicit_reason_found must match whether reasons exist")
        if len(self.reasons) != len(set(self.reasons)):
            raise ValueError("Reason categories must be unique")
        return self


class ReasonBatchResponse(BaseModel):
    """Validated response for one request batch."""

    model_config = ConfigDict(frozen=True)

    items: tuple[ReasonItemResult, ...]


class CachedReasonBatch(BaseModel):
    """Private cache entry containing categories but no source text."""

    model_config = ConfigDict(frozen=True)

    schema_id: str = "tropoflavin_78dhf_reason_cache_v1"
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: str
    model: str
    items: tuple[ReasonItemResult, ...]


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


class ReasonExtractionManifest(BaseModel):
    """Privacy-safe provenance for a completed reason extraction."""

    model_config = ConfigDict(frozen=True)

    schema_id: str = "tropoflavin_78dhf_reason_manifest_v1"
    provider: str
    model: str
    code_commit: str
    prompt_file: str
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    max_text_chars: int
    max_output_tokens: int
    batch_size: int
    source_databases: tuple[SourceDatabase, ...]
    source_author_cohorts: int
    completed_author_cohorts: int
    explicit_reason_author_cohorts: int
    missing_author_cohorts: int
    records_file: str
    records_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    usage: UsageSummary
    completed_at: str


@dataclass(frozen=True)
class AuthorContext:
    subreddit: str
    author_hash: str
    reports: tuple[str, ...]


@dataclass(frozen=True)
class BatchItem:
    item_id: int
    context: AuthorContext


def _connect_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _author_contexts(cohort: CohortInput, max_text_chars: int) -> tuple[AuthorContext, ...]:
    rows_by_author: dict[str, list[tuple[int, str, str]]] = {}
    with closing(_connect_readonly(cohort.database)) as connection:
        rows = connection.execute(
            """
            SELECT tr.user_id, tr.post_id, COALESCE(p.post_date, 0) AS post_date,
                   TRIM(COALESCE(p.title, '') || CHAR(10) ||
                        COALESCE(p.body_text, '')) AS report_text
            FROM treatment_reports tr
            JOIN treatment t ON t.id = tr.drug_id
            JOIN posts p ON p.post_id = tr.post_id
            WHERE lower(t.canonical_name) = '7,8-dhf'
              AND tr.user_id GLOB '[0-9a-f]*'
            ORDER BY tr.user_id, post_date DESC, tr.post_id
            """
        ).fetchall()
    for row in rows:
        author_hash = str(row["user_id"] or "").lower()
        text = str(row["report_text"] or "").strip()
        if not _AUTHOR_HASH.fullmatch(author_hash) or not text:
            continue
        entry = (int(row["post_date"] or 0), str(row["post_id"]), text)
        rows_by_author.setdefault(author_hash, []).append(entry)

    contexts: list[AuthorContext] = []
    for author_hash, entries in sorted(rows_by_author.items()):
        reports: list[str] = []
        seen_text: set[str] = set()
        used_chars = 0
        for _, _, text in sorted(entries, reverse=True):
            normalized = " ".join(text.split())
            digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            if digest in seen_text:
                continue
            remaining = max_text_chars - used_chars
            if remaining <= 0:
                break
            selected = normalized[:remaining]
            if selected:
                reports.append(selected)
                used_chars += len(selected)
                seen_text.add(digest)
        if reports:
            contexts.append(
                AuthorContext(
                    subreddit=cohort.subreddit,
                    author_hash=author_hash,
                    reports=tuple(reports),
                )
            )
    return tuple(contexts)


def _request_payload(items: tuple[BatchItem, ...]) -> str:
    payload = {
        "items": [
            {"item_id": item.item_id, "reports": list(item.context.reports)}
            for item in items
        ]
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _parse_response(text: str, expected_ids: tuple[int, ...]) -> ReasonBatchResponse:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```")
        cleaned = cleaned.removesuffix("```").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Model response did not contain a JSON object")
    response = ReasonBatchResponse.model_validate_json(cleaned[start : end + 1])
    actual_ids = tuple(item.item_id for item in response.items)
    if actual_ids != expected_ids:
        raise ValueError("Model response item IDs did not match the request")
    return response


def _cache_path(cache_root: Path, request_sha256: str) -> Path:
    return cache_root / request_sha256[:3] / f"{request_sha256}.json"


def _request_sha256(prompt_sha256: str, model: str, payload: str) -> str:
    material = f"{prompt_sha256}\n{model}\n{payload}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _write_cache(path: Path, cache: CachedReasonBatch) -> None:
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
) -> tuple[ReasonItemResult, ...] | None:
    payload = _request_payload(items)
    request_sha256 = _request_sha256(prompt_sha256, model, payload)
    cache_path = _cache_path(cache_root, request_sha256)
    if not cache_path.is_file():
        return None
    cached = CachedReasonBatch.model_validate_json(
        cache_path.read_text(encoding="utf-8")
    )
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
) -> tuple[ReasonItemResult, ...] | None:
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
        CachedReasonBatch(
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
) -> tuple[ReasonItemResult, ...]:
    payload = _request_payload(items)
    request_sha256 = _request_sha256(prompt_sha256, model, payload)
    cache_path = _cache_path(cache_root, request_sha256)
    cached = _read_cached_batch(items, prompt_sha256, provider, model, cache_root)
    if cached is not None:
        return cached

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
                cache_path,
                CachedReasonBatch(
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
    raise RuntimeError("Reason extraction request failed after retries") from last_error


def _extract_with_split(
    client: Any,
    items: tuple[BatchItem, ...],
    prompt: str,
    prompt_sha256: str,
    provider: str,
    model: str,
    max_output_tokens: int,
    cache_root: Path,
) -> tuple[ReasonItemResult, ...]:
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
            CachedReasonBatch(
                request_sha256=request_sha256,
                prompt_sha256=prompt_sha256,
                provider=provider,
                model=model,
                items=combined,
            ),
        )
        return combined


def _chunks(
    contexts: tuple[AuthorContext, ...], batch_size: int
) -> tuple[tuple[BatchItem, ...], ...]:
    indexed = tuple(
        BatchItem(item_id=index, context=context)
        for index, context in enumerate(contexts)
    )
    return tuple(
        indexed[start : start + batch_size]
        for start in range(0, len(indexed), batch_size)
    )


def run_reason_extraction(config: ReasonExtractionConfig) -> ReasonExtractionManifest:
    """Run or resume the reason extraction and write only private artifacts."""
    provider_config = llm_config()
    provider = str(provider_config["provider"])
    model = str(provider_config["model_fast"])
    if provider != "openrouter":
        raise ValueError("Reason extraction requires LLM_PROVIDER=openrouter")
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
    manifest_path = config.output_directory / "reason_manifest.json"
    previous_usage = UsageSummary(
        requests=0,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
    )
    if manifest_path.is_file():
        previous_manifest = ReasonExtractionManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        if (
            previous_manifest.provider == provider
            and previous_manifest.model == model
            and previous_manifest.prompt_sha256 == prompt_sha256
            and previous_manifest.source_databases == source_databases
        ):
            previous_usage = previous_manifest.usage
    contexts = tuple(
        context
        for cohort in config.cohorts
        for context in _author_contexts(cohort, config.max_text_chars)
    )
    batches = _chunks(contexts, config.batch_size)
    client = get_llm_client()
    cache_root = config.output_directory / "cache"
    results_by_id: dict[int, ReasonItemResult] = {}
    failures: list[int] = []
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
        completed = 0
        for future in as_completed(futures):
            batch = futures[future]
            try:
                results = future.result()
            except Exception:  # noqa: BLE001
                failures.extend(item.item_id for item in batch)
            else:
                results_by_id.update((result.item_id, result) for result in results)
            completed += len(batch)
            if completed % 60 < len(batch) or completed == len(contexts):
                console.print(
                    f"Processed {completed:,}/{len(contexts):,} author cohorts"
                )

    records = []
    for item_id, context in enumerate(contexts):
        result = results_by_id.get(item_id)
        if result is None:
            continue
        records.append(
            ReasonRecord(
                subreddit=context.subreddit,
                author_hash=context.author_hash,
                explicit_reason_found=result.explicit_reason_found,
                reasons=result.reasons,
                source_report_count=len(context.reports),
            )
        )
    config.output_directory.mkdir(parents=True, exist_ok=True)
    records_path = config.output_directory / "reason_records.jsonl"
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
    manifest = ReasonExtractionManifest(
        provider=provider,
        model=model,
        code_commit=_git_commit(),
        prompt_file=config.prompt_path.name,
        prompt_sha256=prompt_sha256,
        max_text_chars=config.max_text_chars,
        max_output_tokens=config.max_output_tokens,
        batch_size=config.batch_size,
        source_databases=source_databases,
        source_author_cohorts=len(contexts),
        completed_author_cohorts=len(records),
        explicit_reason_author_cohorts=sum(
            record.explicit_reason_found for record in records
        ),
        missing_author_cohorts=len(contexts) - len(records),
        records_file=records_path.name,
        records_sha256=sha256_file(records_path),
        usage=usage,
        completed_at=datetime.now(UTC).isoformat(),
    )
    manifest_path.write_text(
        manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    if failures or manifest.missing_author_cohorts:
        raise RuntimeError(
            f"Reason extraction incomplete: {manifest.missing_author_cohorts} missing"
        )
    return manifest


@app.command()
def main(config_path: Path = typer.Option(..., exists=True, dir_okay=False)) -> None:
    """Extract explicit reasons from retained 7,8-DHF reports."""
    config = ReasonExtractionConfig.model_validate_json(
        config_path.read_text(encoding="utf-8")
    )
    manifest = run_reason_extraction(config)
    console.print(
        f"[green]Complete[/green] {manifest.completed_author_cohorts:,} author cohorts, "
        f"{manifest.usage.total_tokens:,} provider-reported tokens"
    )


if __name__ == "__main__":
    app()
