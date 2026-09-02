"""Build one private, author-level corpus for comparator variable extraction."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator
from rich.console import Console

from studies.tropoflavin_nootropics.comparator_support import (
    DEFAULT_COHORT_CONFIG,
    load_comparator_cohort,
    safe_json_dump,
    sha256_file,
)

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


class SourceComment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    comment_id: str
    body: str = ""
    author_hash: str
    created_utc: str
    score: int = 0
    parent_id: str = ""


class SourcePost(BaseModel):
    model_config = ConfigDict(extra="ignore")

    post_id: str
    title: str = ""
    body: str = ""
    author_hash: str
    created_utc: str
    score: int = 0
    num_comments_api: int = 0
    comments: list[SourceComment] = Field(default_factory=list)


class UserPost(BaseModel):
    model_config = ConfigDict(frozen=True)

    post_id: str
    subreddit: str
    title: str
    body: str
    created_utc: int
    score: int
    num_comments: int


class UserComment(BaseModel):
    model_config = ConfigDict(frozen=True)

    comment_id: str
    subreddit: str
    body: str
    created_utc: int
    score: int
    parent_id: str


class UserCorpusRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    author_hash: str = Field(min_length=32, max_length=32)
    account_created_utc: None = None
    total_karma: None = None
    scraped_at: None = None
    posts: tuple[UserPost, ...] = ()
    comments: tuple[UserComment, ...] = ()


class VariableCorpusConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    subreddit: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_]+$")
    source_corpus: Path
    output_directory: Path
    cohort_path: Path = DEFAULT_COHORT_CONFIG
    sentiment_database: Path | None = None

    @model_validator(mode="after")
    def validate_inputs(self) -> VariableCorpusConfig:
        if not self.source_corpus.is_file():
            raise ValueError(f"Comparator corpus not found: {self.source_corpus}")
        if not self.cohort_path.is_file():
            raise ValueError(f"Comparator cohort not found: {self.cohort_path}")
        if self.sentiment_database is not None and not self.sentiment_database.is_file():
            raise ValueError(f"Sentiment database not found: {self.sentiment_database}")
        return self


class VariableCorpusManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_id: str = "tropoflavin_variable_corpus_manifest_v1"
    subreddit: str
    source_corpus_sha256: str
    cohort_schema_id: str
    cohort_sha256: str
    author_hash_algorithm: str = "sha256-128-raw-reddit-username-v1"
    selected_authors: int = Field(ge=0)
    eligible_authors: int = Field(ge=0)
    eligibility_basis: str
    posts: int = Field(ge=0)
    comments: int = Field(ge=0)
    text_segments: int = Field(ge=0)
    created_at: str


def _epoch(value: str) -> int:
    try:
        return int(datetime.fromisoformat(value).timestamp())
    except ValueError:
        return 0


def _load_posts(path: Path) -> list[SourcePost]:
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    return TypeAdapter(list[SourcePost]).validate_python(payload)


def _retained_authors(path: Path) -> set[str]:
    with closing(
        sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    ) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError(f"Sentiment database integrity check failed: {path.name}")
        return {
            str(row[0])
            for row in connection.execute(
                """
                SELECT DISTINCT user_id
                FROM treatment_reports
                WHERE user_id IS NOT NULL AND user_id != 'deleted'
                """
            )
        }


def build_variable_corpus(config: VariableCorpusConfig) -> VariableCorpusManifest:
    """Write one file per nondeleted author who directly names a comparator."""
    cohort = load_comparator_cohort(config.cohort_path)
    posts = _load_posts(config.source_corpus)
    mentioners: set[str] = set()
    for post in posts:
        post_text = f"{post.title} {post.body}".strip()
        if any(compound.matches(post_text) for compound in cohort.compounds):
            mentioners.add(post.author_hash)
        for comment in post.comments:
            if any(compound.matches(comment.body) for compound in cohort.compounds):
                mentioners.add(comment.author_hash)
    mentioners.discard("deleted")
    eligible_authors = (
        _retained_authors(config.sentiment_database)
        if config.sentiment_database is not None
        else mentioners
    )
    mentioners &= eligible_authors

    user_posts: dict[str, list[UserPost]] = {author: [] for author in mentioners}
    user_comments: dict[str, list[UserComment]] = {author: [] for author in mentioners}
    for post in posts:
        if post.author_hash in mentioners:
            user_posts[post.author_hash].append(
                UserPost(
                    post_id=post.post_id,
                    subreddit=config.subreddit,
                    title=post.title,
                    body=post.body,
                    created_utc=_epoch(post.created_utc),
                    score=post.score,
                    num_comments=post.num_comments_api,
                )
            )
        for comment in post.comments:
            if comment.author_hash in mentioners:
                user_comments[comment.author_hash].append(
                    UserComment(
                        comment_id=comment.comment_id,
                        subreddit=config.subreddit,
                        body=comment.body,
                        created_utc=_epoch(comment.created_utc),
                        score=comment.score,
                        parent_id=comment.parent_id,
                    )
                )

    users_directory = config.output_directory / "users"
    users_directory.mkdir(parents=True, exist_ok=True)
    unexpected = {
        path.name for path in users_directory.glob("*.json") if path.stem not in mentioners
    }
    if unexpected:
        raise ValueError(
            "Output directory contains stale user files; use a new run directory: "
            + ", ".join(sorted(unexpected)[:3])
        )

    text_segments = 0
    for author in sorted(mentioners):
        record = UserCorpusRecord(
            author_hash=author,
            posts=tuple(user_posts[author]),
            comments=tuple(user_comments[author]),
        )
        text_segments += sum(bool(post.title) + bool(post.body) for post in record.posts)
        text_segments += sum(bool(comment.body) for comment in record.comments)
        path = users_directory / f"{author}.json"
        path.write_text(record.model_dump_json(), encoding="utf-8")

    manifest = VariableCorpusManifest(
        subreddit=config.subreddit,
        source_corpus_sha256=sha256_file(config.source_corpus),
        cohort_schema_id=cohort.schema_id,
        cohort_sha256=sha256_file(config.cohort_path),
        selected_authors=len(mentioners),
        eligible_authors=len(eligible_authors),
        eligibility_basis=(
            "retained comparator sentiment report"
            if config.sentiment_database is not None
            else "direct comparator alias mention"
        ),
        posts=sum(len(values) for values in user_posts.values()),
        comments=sum(len(values) for values in user_comments.values()),
        text_segments=text_segments,
        created_at=datetime.now(UTC).isoformat(),
    )
    safe_json_dump(manifest, config.output_directory / "variable_corpus.manifest.json")
    console.print(
        f"[green]Wrote[/green] {manifest.selected_authors:,} author files with "
        f"{manifest.text_segments:,} text segments for r/{config.subreddit}"
    )
    return manifest


@app.command()
def main(
    subreddit: str = typer.Option(..., help="Subreddit name without the r/ prefix."),
    source_corpus: Path = typer.Option(..., exists=True, dir_okay=False),
    output_directory: Path = typer.Option(..., file_okay=False),
    cohort: Path = typer.Option(DEFAULT_COHORT_CONFIG, exists=True, dir_okay=False),
    sentiment_database: Path | None = typer.Option(
        None, exists=True, dir_okay=False
    ),
) -> None:
    """Build a private author corpus for Pipeline B."""
    build_variable_corpus(
        VariableCorpusConfig(
            subreddit=subreddit,
            source_corpus=source_corpus,
            output_directory=output_directory,
            cohort_path=cohort,
            sentiment_database=sentiment_database,
        )
    )


if __name__ == "__main__":
    app()
