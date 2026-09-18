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

from pydantic import BaseModel, ConfigDict, Field, computed_field

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
    configured_drug_aliases_sha256: str | None = Field(
        default=None,
        pattern=_SHA256_PATTERN,
    )


class RunProvenance(_FrozenModel):
    """Persisted inputs and deterministic identity for one sentiment run."""

    schema_id: Literal["treatment_sentiment_run_provenance_v1"] = "treatment_sentiment_run_provenance_v1"
    git_commit: str = Field(min_length=1)
    git_dirty: bool | None
    provider: str = Field(min_length=1)
    fast_model: str = Field(min_length=1)
    strong_model: str = Field(min_length=1)
    reasoning_mode: Literal["enabled", "disabled", "not_applicable"]
    prompt_bundle_sha256: str = Field(pattern=_SHA256_PATTERN)
    options: PipelineOptions

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fingerprint(self) -> str:
        """SHA-256 of the canonical record, excluding this computed field."""
        canonical = json.dumps(
            self.model_dump(mode="json", exclude={"fingerprint"}),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return _sha256(canonical)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_aliases(aliases: Iterable[str] | None) -> str | None:
    """Hash aliases after the same case-insensitive normalization used by targeting."""
    if aliases is None:
        return None
    normalized = sorted({alias.strip().casefold() for alias in aliases if alias.strip()})
    return _sha256(json.dumps(normalized, ensure_ascii=False, separators=(",", ":")))


def read_git_state(repo_root: Path = REPO_ROOT) -> tuple[str, bool | None]:
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
        return "unknown", None

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
    return commit, dirty


def prompt_bundle_hash() -> str:
    """Hash every literal prompt and dynamic prompt builder as one bundle."""
    definitions = (
        EXTRACT_PROMPT,
        CANONICALIZE_COMPOUND_PROMPT,
        inspect.getsource(drug_aliases_prompt),
        PREFILTER_PROMPT,
        inspect.getsource(system_prompt),
    )
    return _sha256(json.dumps(definitions, ensure_ascii=False, separators=(",", ":")))


def build_run_provenance(
    *,
    provider: str,
    fast_model: str,
    strong_model: str,
    reasoning_mode: Literal["enabled", "disabled", "not_applicable"],
    options: PipelineOptions,
) -> RunProvenance:
    """Collect run identity and calculate its canonical SHA-256 fingerprint."""
    git_commit, git_dirty = read_git_state()
    return RunProvenance(
        git_commit=git_commit,
        git_dirty=git_dirty,
        provider=provider,
        fast_model=fast_model,
        strong_model=strong_model,
        reasoning_mode=reasoning_mode,
        prompt_bundle_sha256=prompt_bundle_hash(),
        options=options,
    )
