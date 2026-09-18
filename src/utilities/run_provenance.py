"""Typed provenance for treatment-sentiment pipeline runs."""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from prompts.intervention_config import (
    CANONICALIZE_COMPOUND_PROMPT,
    EXTRACT_PROMPT,
    PREFILTER_PROMPT,
    drug_aliases_prompt,
    system_prompt,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_LOG = logging.getLogger("pipeline")


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GitState(_FrozenModel):
    """Source checkout used for a run."""

    commit: str = Field(min_length=1)
    dirty: bool | None


class LLMSettings(_FrozenModel):
    """Provider settings that affect model output."""

    provider: str = Field(min_length=1)
    fast_model: str = Field(min_length=1)
    strong_model: str = Field(min_length=1)
    reasoning_mode: Literal["enabled", "disabled", "not_applicable"]


class PromptHashes(_FrozenModel):
    """SHA-256 identities for every prompt definition used by the pipeline."""

    extract: str = Field(pattern=_SHA256_PATTERN)
    canonicalize: str = Field(pattern=_SHA256_PATTERN)
    drug_aliases_builder: str = Field(pattern=_SHA256_PATTERN)
    prefilter: str = Field(pattern=_SHA256_PATTERN)
    sentiment_builder: str = Field(pattern=_SHA256_PATTERN)


class PipelineOptions(_FrozenModel):
    """Behavior-affecting options supplied to one pipeline run."""

    limit: int | None
    reclassify: bool
    skip_extract: bool
    skip_canonicalize: bool
    skip_prefilter: bool
    max_upstream_chars: int | None
    max_upstream_depth: int | None
    workers: int = Field(ge=1)
    drug: str | None
    configured_drug_aliases_count: int = Field(ge=0)
    configured_drug_aliases_sha256: str | None = Field(
        default=None,
        pattern=_SHA256_PATTERN,
    )


class RunIdentity(_FrozenModel):
    """All recorded inputs that determine a run fingerprint."""

    schema_id: Literal["treatment_sentiment_run_provenance_v1"] = "treatment_sentiment_run_provenance_v1"
    git: GitState
    llm: LLMSettings
    prompts: PromptHashes
    options: PipelineOptions


class RunProvenance(RunIdentity):
    """Persisted run identity and its deterministic fingerprint."""

    fingerprint: str = Field(pattern=_SHA256_PATTERN)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_aliases(aliases: Iterable[str] | None) -> str | None:
    """Hash aliases after the same case-insensitive normalization used by targeting."""
    if aliases is None:
        return None
    normalized = sorted({alias.strip().casefold() for alias in aliases if alias.strip()})
    return _sha256(json.dumps(normalized, ensure_ascii=False, separators=(",", ":")))


def read_git_state(repo_root: Path = REPO_ROOT) -> GitState:
    """Read the current commit and whether the checkout has local changes."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        _LOG.warning("Git commit is unavailable; run provenance will record unknown.")
        return GitState(commit="unknown", dirty=None)

    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        dirty: bool | None = bool(status.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        dirty = None

    if dirty:
        _LOG.warning(
            "Git checkout is dirty at commit %s; the commit alone cannot reproduce this run.",
            commit[:8],
        )
    return GitState(commit=commit, dirty=dirty)


def current_prompt_hashes() -> PromptHashes:
    """Hash literal prompts and the source of dynamic prompt builders."""
    return PromptHashes(
        extract=_sha256(EXTRACT_PROMPT),
        canonicalize=_sha256(CANONICALIZE_COMPOUND_PROMPT),
        drug_aliases_builder=_sha256(inspect.getsource(drug_aliases_prompt)),
        prefilter=_sha256(PREFILTER_PROMPT),
        sentiment_builder=_sha256(inspect.getsource(system_prompt)),
    )


def build_run_provenance(
    *,
    provider: str,
    fast_model: str,
    strong_model: str,
    reasoning_mode: Literal["enabled", "disabled", "not_applicable"],
    options: PipelineOptions,
) -> RunProvenance:
    """Collect run identity and calculate its canonical SHA-256 fingerprint."""
    identity = RunIdentity(
        git=read_git_state(),
        llm=LLMSettings(
            provider=provider,
            fast_model=fast_model,
            strong_model=strong_model,
            reasoning_mode=reasoning_mode,
        ),
        prompts=current_prompt_hashes(),
        options=options,
    )
    canonical = json.dumps(
        identity.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return RunProvenance(
        **identity.model_dump(),
        fingerprint=_sha256(canonical),
    )
