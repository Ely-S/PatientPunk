"""Validated cohort configuration and shared comparator-study contracts."""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from utilities.alias_matching import has_unexcluded_alias

HERE = Path(__file__).resolve().parent
DEFAULT_COHORT_CONFIG = HERE / "comparator_cohort.json"


class ComparatorSpec(BaseModel):
    """One target or comparator and its hand-audited aliases."""

    model_config = ConfigDict(frozen=True)

    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    canonical_name: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    tier: Literal[
        "target",
        "chemical analogue",
        "BDNF/TrkB related",
        "broader neurotrophic",
        "negative control",
    ]
    analysis_role: Literal["target", "primary", "secondary", "exploratory", "control"]
    mechanism_note: str = Field(min_length=1)
    aliases: tuple[str, ...] = Field(min_length=1)
    excluded_aliases: tuple[str, ...] = ()
    prefilter_terms: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_aliases(self) -> ComparatorSpec:
        normalized = [alias.strip().lower() for alias in self.aliases]
        if len(normalized) != len(set(normalized)):
            raise ValueError(f"Duplicate aliases for {self.slug}")
        if self.canonical_name.lower() not in normalized:
            raise ValueError(
                f"Canonical name {self.canonical_name!r} is not an alias for {self.slug}"
            )
        if any(not term.strip() for term in self.prefilter_terms):
            raise ValueError(f"Blank prefilter term for {self.slug}")
        return self

    def matches(self, text: str) -> bool:
        """Return whether text contains a non-excluded mention of this compound."""
        return has_unexcluded_alias(text, self.aliases, self.excluded_aliases)


class ComparatorCohort(BaseModel):
    """Versioned comparator set used for extraction and analysis."""

    model_config = ConfigDict(frozen=True)

    schema_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    target_slug: str
    compounds: tuple[ComparatorSpec, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_cohort(self) -> ComparatorCohort:
        slugs = [compound.slug for compound in self.compounds]
        names = [compound.canonical_name.lower() for compound in self.compounds]
        if len(slugs) != len(set(slugs)):
            raise ValueError("Comparator slugs must be unique")
        if len(names) != len(set(names)):
            raise ValueError("Comparator canonical names must be unique")
        targets = [compound for compound in self.compounds if compound.analysis_role == "target"]
        if len(targets) != 1 or targets[0].slug != self.target_slug:
            raise ValueError("Cohort must have exactly one matching target")
        return self

    @property
    def target(self) -> ComparatorSpec:
        return next(compound for compound in self.compounds if compound.slug == self.target_slug)

    def by_slug(self) -> dict[str, ComparatorSpec]:
        return {compound.slug: compound for compound in self.compounds}


class ComparatorMatchSummary(BaseModel):
    """Privacy-safe mention counts for one comparator."""

    model_config = ConfigDict(frozen=True)

    slug: str
    matching_items: int = Field(ge=0)
    distinct_authors: int = Field(ge=0)
    distinct_threads: int = Field(ge=0)


class ComparatorCorpusManifest(BaseModel):
    """Reproducibility metadata for a generated private corpus."""

    model_config = ConfigDict(frozen=True)

    schema_id: str = "tropoflavin_comparator_corpus_manifest_v1"
    cohort_schema_id: str
    cohort_sha256: str
    comments_path: str
    posts_path: str
    output_path: str
    posts: int = Field(ge=0)
    comments: int = Field(ge=0)
    distinct_authors: int = Field(ge=0)
    orphan_comments: int = Field(ge=0)
    matches: tuple[ComparatorMatchSummary, ...]


def load_comparator_cohort(path: Path = DEFAULT_COHORT_CONFIG) -> ComparatorCohort:
    """Load and validate the versioned comparator cohort."""
    return ComparatorCohort.model_validate_json(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    """Return a full SHA-256 digest without loading a large file into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_author(name: str | None) -> str:
    """Hash a Reddit username before it can enter a generated artifact."""
    if not name or name in {"[deleted]", "[removed]"}:
        return "deleted"
    return hashlib.sha256(name.encode("utf-8")).hexdigest()[:32]


def reddit_id(value: str | None) -> str:
    """Remove Reddit's kind prefix from a base36 identifier."""
    if not value:
        return ""
    return value[3:] if value.startswith(("t1_", "t3_")) else value


def prefilter_hit(raw: bytes, cohort: ComparatorCohort) -> bool:
    """Cheap bytes check before parsing a raw Reddit JSON object."""
    lowered = raw.lower()
    return any(
        term.encode("utf-8").lower() in lowered
        for compound in cohort.compounds
        for term in compound.prefilter_terms
    )


def safe_json_dump(model: BaseModel, path: Path) -> None:
    """Write a validated JSON artifact with a stable newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.model_dump_json(indent=2) + "\n", encoding="utf-8")


def markdown_escape(value: str) -> str:
    """Escape table delimiters in generated Markdown cells."""
    return re.sub(r"\|", r"\\|", value.replace("\n", " "))
