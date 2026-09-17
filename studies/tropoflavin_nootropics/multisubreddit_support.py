"""Validated configuration shared by multisubreddit study stages."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEFAULT_SUBREDDIT_CONFIG = HERE / "subreddit_cohorts.json"


class SubredditSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_]+$")
    source_stem: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_]+$")


class SubredditStudyConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    subreddits: tuple[SubredditSpec, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_subreddits(self) -> SubredditStudyConfig:
        names = [subreddit.name.casefold() for subreddit in self.subreddits]
        stems = [subreddit.source_stem.casefold() for subreddit in self.subreddits]
        if len(names) != len(set(names)):
            raise ValueError("Subreddit names must be unique")
        if len(stems) != len(set(stems)):
            raise ValueError("Subreddit source stems must be unique")
        return self


def load_subreddit_study(
    path: Path = DEFAULT_SUBREDDIT_CONFIG,
) -> SubredditStudyConfig:
    """Load the versioned list of independent subreddit cohorts."""
    return SubredditStudyConfig.model_validate_json(path.read_text(encoding="utf-8"))


def patientpunk_data_root() -> Path:
    """Resolve the external data directory without committing machine paths."""
    configured = os.environ.get("PATIENTPUNK_DATA")
    return Path(configured) if configured else REPO_ROOT.parent / "PatientPunk_data"

