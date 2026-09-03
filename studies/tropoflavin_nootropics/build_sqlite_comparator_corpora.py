"""Build private comparator corpora from an existing Reddit SQLite database."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

import typer
from pydantic import BaseModel, ConfigDict, Field, model_validator
from rich.console import Console

from studies.tropoflavin_nootropics.comparator_support import (
    DEFAULT_COHORT_CONFIG,
    ComparatorMatchSummary,
    hash_author,
    load_comparator_cohort,
    reddit_id,
    sha256_file,
)

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


class SqliteCorpusConfig(BaseModel):
    """Validated inputs for a read-only multi-community corpus build."""

    model_config = ConfigDict(frozen=True)

    source_database: Path
    output_directory: Path
    communities: tuple[str, ...] = Field(min_length=1)
    cohort_path: Path = DEFAULT_COHORT_CONFIG

    @model_validator(mode="after")
    def validate_inputs(self) -> SqliteCorpusConfig:
        if not self.source_database.is_file():
            raise ValueError(f"Source database not found: {self.source_database}")
        if not self.cohort_path.is_file():
            raise ValueError(f"Comparator cohort not found: {self.cohort_path}")
        if len(self.communities) != len(set(self.communities)):
            raise ValueError("Communities must be unique")
        return self


class CommunityCorpusSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    community: str
    posts: int = Field(ge=0)
    comments: int = Field(ge=0)
    distinct_authors: int = Field(ge=0)
    matches: tuple[ComparatorMatchSummary, ...]


class SqliteCorpusManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_id: str = "tropoflavin_sqlite_comparator_corpora_v1"
    source_database_name: str
    cohort_schema_id: str
    cohort_sha256: str
    generated_at: str
    communities: tuple[CommunityCorpusSummary, ...]


class MatchStats(TypedDict):
    items: int
    authors: set[str]
    threads: set[str]


def _clean(value: object) -> str:
    return "" if value in {None, "[deleted]", "[removed]"} else str(value)


def _iso(value: int | float | str | None) -> str:
    if value is None:
        return ""
    return datetime.fromtimestamp(int(value), tz=UTC).isoformat()


def _readonly_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _candidate_clause(needles: tuple[str, ...], column: str) -> tuple[str, list[str]]:
    clause = " OR ".join(f"lower({column}) LIKE ?" for _ in needles)
    return clause, [f"%{needle.lower()}%" for needle in needles]


def _matched_rows(
    connection: sqlite3.Connection,
    config: SqliteCorpusConfig,
) -> tuple[
    dict[str, sqlite3.Row],
    dict[str, sqlite3.Row],
    dict[str, MatchStats],
]:
    cohort = load_comparator_cohort(config.cohort_path)
    needles = tuple(
        sorted(
            {term for compound in cohort.compounds for term in compound.prefilter_terms},
            key=str.casefold,
        )
    )
    placeholders = ", ".join("?" for _ in config.communities)
    post_clause, post_params = _candidate_clause(
        needles, "coalesce(title, '') || ' ' || coalesce(selftext, '')"
    )
    comment_clause, comment_params = _candidate_clause(needles, "coalesce(body, '')")
    posts: dict[str, sqlite3.Row] = {}
    comments: dict[str, sqlite3.Row] = {}
    stats: dict[str, MatchStats] = defaultdict(
        lambda: {"items": 0, "authors": set(), "threads": set()}
    )

    post_sql = f"""
        SELECT id, subreddit, created_utc, score, num_comments, title, selftext,
               author, permalink
        FROM posts
        WHERE subreddit IN ({placeholders}) AND ({post_clause})
    """
    for row in connection.execute(
        post_sql, [*config.communities, *post_params]
    ):
        text = f"{row['title'] or ''} {row['selftext'] or ''}"
        matched = [compound for compound in cohort.compounds if compound.matches(text)]
        if not matched:
            continue
        post_id = str(row["id"])
        posts[post_id] = row
        author = hash_author(row["author"])
        for compound in matched:
            key = f"{row['subreddit']}\0{compound.slug}"
            stats[key]["items"] += 1
            stats[key]["threads"].add(post_id)
            if author != "deleted":
                stats[key]["authors"].add(author)

    comment_sql = f"""
        SELECT id, subreddit, created_utc, score, body, author, link_id, parent_id
        FROM comments
        WHERE subreddit IN ({placeholders}) AND ({comment_clause})
    """
    for row in connection.execute(
        comment_sql, [*config.communities, *comment_params]
    ):
        text = row["body"] or ""
        matched = [compound for compound in cohort.compounds if compound.matches(text)]
        if not matched:
            continue
        comment_id = str(row["id"])
        thread_id = reddit_id(row["link_id"]) or ""
        comments[comment_id] = row
        author = hash_author(row["author"])
        for compound in matched:
            key = f"{row['subreddit']}\0{compound.slug}"
            stats[key]["items"] += 1
            stats[key]["threads"].add(thread_id)
            if author != "deleted":
                stats[key]["authors"].add(author)

    return posts, comments, stats


def _add_context(
    connection: sqlite3.Connection,
    posts: dict[str, sqlite3.Row],
    comments: dict[str, sqlite3.Row],
) -> None:
    pending = list(comments.values())
    while pending:
        row = pending.pop()
        thread_id = reddit_id(row["link_id"])
        if thread_id and thread_id not in posts:
            post = connection.execute(
                """
                SELECT id, subreddit, created_utc, score, num_comments, title,
                       selftext, author, permalink
                FROM posts WHERE id = ?
                """,
                (thread_id,),
            ).fetchone()
            if post is not None:
                posts[thread_id] = post

        parent_id = reddit_id(row["parent_id"])
        if not parent_id or parent_id == thread_id or parent_id in comments:
            continue
        parent = connection.execute(
            """
            SELECT id, subreddit, created_utc, score, body, author, link_id, parent_id
            FROM comments WHERE id = ?
            """,
            (parent_id,),
        ).fetchone()
        if parent is not None:
            comments[parent_id] = parent
            pending.append(parent)


def _write_community(
    config: SqliteCorpusConfig,
    community: str,
    posts: dict[str, sqlite3.Row],
    comments: dict[str, sqlite3.Row],
    stats: dict[str, MatchStats],
) -> CommunityCorpusSummary:
    cohort = load_comparator_cohort(config.cohort_path)
    comments_by_thread: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in comments.values():
        if row["subreddit"] == community:
            comments_by_thread[reddit_id(row["link_id"]) or ""].append(row)

    payload: list[dict[str, object]] = []
    authors: set[str] = set()
    comment_count = 0
    for post_id, post in sorted(
        posts.items(), key=lambda item: int(item[1]["created_utc"] or 0)
    ):
        if post["subreddit"] != community:
            continue
        thread_comments = sorted(
            comments_by_thread.get(post_id, []),
            key=lambda row: int(row["created_utc"] or 0),
        )
        post_author = hash_author(post["author"])
        if post_author != "deleted":
            authors.add(post_author)
        encoded_comments: list[dict[str, object]] = []
        for comment in thread_comments:
            comment_author = hash_author(comment["author"])
            if comment_author != "deleted":
                authors.add(comment_author)
            encoded_comments.append(
                {
                    "comment_id": str(comment["id"]),
                    "body": _clean(comment["body"]),
                    "author_hash": comment_author,
                    "created_utc": _iso(comment["created_utc"]),
                    "score": int(comment["score"] or 0),
                    "parent_id": str(comment["parent_id"] or ""),
                }
            )
        payload.append(
            {
                "post_id": post_id,
                "title": str(post["title"] or ""),
                "body": _clean(post["selftext"]),
                "author_hash": post_author,
                "created_utc": _iso(post["created_utc"]),
                "score": int(post["score"] or 0),
                "flair": "",
                "url": f"https://www.reddit.com{post['permalink'] or ''}",
                "num_comments_api": int(post["num_comments"] or 0),
                "comments_fetched": len(encoded_comments),
                "comments": encoded_comments,
                "subreddit": community,
            }
        )
        comment_count += len(encoded_comments)

    community_dir = config.output_directory / community
    community_dir.mkdir(parents=True, exist_ok=True)
    output = community_dir / "comparator_corpus.json"
    output.write_text(json.dumps(payload), encoding="utf-8")
    return CommunityCorpusSummary(
        community=community,
        posts=len(payload),
        comments=comment_count,
        distinct_authors=len(authors),
        matches=tuple(
            ComparatorMatchSummary(
                slug=compound.slug,
                matching_items=stats[f"{community}\0{compound.slug}"]["items"],
                distinct_authors=len(
                    stats[f"{community}\0{compound.slug}"]["authors"]
                ),
                distinct_threads=len(
                    stats[f"{community}\0{compound.slug}"]["threads"]
                ),
            )
            for compound in cohort.compounds
        ),
    )


def build_sqlite_comparator_corpora(
    config: SqliteCorpusConfig,
) -> SqliteCorpusManifest:
    """Scan once, retain matching entries plus their ancestor context, and write corpora."""
    cohort = load_comparator_cohort(config.cohort_path)
    with closing(_readonly_connection(config.source_database)) as connection:
        posts, comments, stats = _matched_rows(connection, config)
        _add_context(connection, posts, comments)
        summaries = tuple(
            _write_community(config, community, posts, comments, stats)
            for community in config.communities
        )
    manifest = SqliteCorpusManifest(
        source_database_name=config.source_database.name,
        cohort_schema_id=cohort.schema_id,
        cohort_sha256=sha256_file(config.cohort_path),
        generated_at=datetime.now(UTC).isoformat(),
        communities=summaries,
    )
    manifest_path = config.output_directory / "patient_corpus_manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return manifest


@app.command()
def main(
    source_db: Path = typer.Option(..., exists=True, dir_okay=False),
    output_dir: Path = typer.Option(..., file_okay=False),
    community: list[str] = typer.Option(..., help="Repeat for each subreddit."),
    cohort: Path = typer.Option(DEFAULT_COHORT_CONFIG, exists=True, dir_okay=False),
) -> None:
    """Build one private corpus per selected community."""
    config = SqliteCorpusConfig(
        source_database=source_db,
        output_directory=output_dir,
        communities=tuple(community),
        cohort_path=cohort,
    )
    manifest = build_sqlite_comparator_corpora(config)
    for summary in manifest.communities:
        console.print(
            f"[green]{summary.community}[/green]: {summary.posts:,} threads, "
            f"{summary.comments:,} retained comments"
        )


if __name__ == "__main__":
    app()
