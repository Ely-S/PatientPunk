"""Build one private r/Nootropics thread corpus for the comparator cohort."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

import typer
from pydantic import BaseModel, ConfigDict, model_validator
from rich.console import Console

from studies.tropoflavin_nootropics.comparator_support import (
    DEFAULT_COHORT_CONFIG,
    ComparatorCorpusManifest,
    ComparatorMatchSummary,
    hash_author,
    load_comparator_cohort,
    prefilter_hit,
    reddit_id,
    safe_json_dump,
    sha256_file,
)

console = Console()
app = typer.Typer(add_completion=False, no_args_is_help=True)


class BuildComparatorCorpusConfig(BaseModel):
    """Validated filesystem boundary for the corpus builder."""

    model_config = ConfigDict(frozen=True)

    comments_path: Path
    posts_path: Path
    cohort_path: Path = DEFAULT_COHORT_CONFIG
    output_path: Path

    @model_validator(mode="after")
    def validate_paths(self) -> BuildComparatorCorpusConfig:
        for label, path in (
            ("comments", self.comments_path),
            ("posts", self.posts_path),
            ("cohort", self.cohort_path),
        ):
            if not path.is_file():
                raise ValueError(f"{label} input does not exist: {path}")
        if self.output_path.resolve() in {
            self.comments_path.resolve(),
            self.posts_path.resolve(),
            self.cohort_path.resolve(),
        }:
            raise ValueError("Output path must not overwrite an input")
        return self


class CorpusComment(TypedDict):
    comment_id: str
    body: str
    author_hash: str
    created_utc: str
    score: int
    parent_id: str


class CorpusPost(TypedDict):
    post_id: str
    title: str
    body: str
    author_hash: str
    created_utc: str
    score: int
    flair: str
    url: str
    num_comments_api: int
    comments_fetched: int
    comments: list[CorpusComment]


def _clean(value: Any) -> str:
    return "" if value in {"[deleted]", "[removed]", None} else str(value)


def _iso(timestamp: Any) -> str:
    return datetime.fromtimestamp(int(timestamp), tz=UTC).isoformat()


def _text(record: dict[str, Any], kind: str) -> str:
    if kind == "comment":
        return _clean(record.get("body"))
    return f"{record.get('title') or ''} {record.get('selftext') or ''}".strip()


def _thread_id(record: dict[str, Any], kind: str) -> str:
    return reddit_id(record.get("link_id")) if kind == "comment" else str(record.get("id") or "")


def _scan_mentions(
    config: BuildComparatorCorpusConfig,
) -> tuple[set[str], dict[str, int], dict[str, set[str]], dict[str, set[str]]]:
    cohort = load_comparator_cohort(config.cohort_path)
    threads: set[str] = set()
    item_counts: dict[str, int] = defaultdict(int)
    author_sets: dict[str, set[str]] = defaultdict(set)
    thread_sets: dict[str, set[str]] = defaultdict(set)

    for path, kind in (
        (config.comments_path, "comment"),
        (config.posts_path, "post"),
    ):
        with path.open("rb") as handle:
            for raw in handle:
                if not prefilter_hit(raw, cohort):
                    continue
                try:
                    record = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                text = _text(record, kind)
                thread_id = _thread_id(record, kind)
                if not thread_id:
                    continue
                matched = [compound for compound in cohort.compounds if compound.matches(text)]
                if not matched:
                    continue
                threads.add(thread_id)
                author = hash_author(record.get("author"))
                for compound in matched:
                    item_counts[compound.slug] += 1
                    thread_sets[compound.slug].add(thread_id)
                    if author != "deleted":
                        author_sets[compound.slug].add(author)
        console.print(
            f"[cyan]{path.name}[/cyan]: {sum(item_counts.values()):,} cumulative comparator matches"
        )

    return threads, item_counts, author_sets, thread_sets


def _collect_threads(
    config: BuildComparatorCorpusConfig,
    threads: set[str],
) -> tuple[list[CorpusPost], int]:
    posts_out: dict[str, CorpusPost] = {}
    with config.posts_path.open("rb") as handle:
        for raw in handle:
            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                continue
            post_id = str(record.get("id") or "")
            if post_id not in threads:
                continue
            posts_out[post_id] = {
                "post_id": post_id,
                "title": str(record.get("title") or ""),
                "body": _clean(record.get("selftext")),
                "author_hash": hash_author(record.get("author")),
                "created_utc": _iso(record["created_utc"]),
                "score": int(record.get("score") or 0),
                "flair": str(record.get("link_flair_text") or ""),
                "url": (
                    f"https://www.reddit.com"
                    f"{record.get('permalink', '') or f'/r/Nootropics/comments/{post_id}/'}"
                ),
                "num_comments_api": int(record.get("num_comments") or 0),
                "comments_fetched": 0,
                "comments": [],
            }

    orphan_comments = 0
    with config.comments_path.open("rb") as handle:
        for raw in handle:
            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                continue
            thread_id = reddit_id(record.get("link_id"))
            if thread_id not in threads:
                continue
            post = posts_out.get(thread_id)
            if post is None:
                orphan_comments += 1
                continue
            post["comments"].append(
                {
                    "comment_id": str(record["id"]),
                    "body": _clean(record.get("body")),
                    "author_hash": hash_author(record.get("author")),
                    "created_utc": _iso(record["created_utc"]),
                    "score": int(record.get("score") or 0),
                    "parent_id": str(record.get("parent_id") or ""),
                }
            )

    for post in posts_out.values():
        post["comments"].sort(key=lambda comment: comment["created_utc"])
        post["comments_fetched"] = len(post["comments"])
    return sorted(posts_out.values(), key=lambda post: post["created_utc"]), orphan_comments


def build_comparator_corpus(
    config: BuildComparatorCorpusConfig,
) -> ComparatorCorpusManifest:
    """Build the union of every thread containing a configured comparator."""
    cohort = load_comparator_cohort(config.cohort_path)
    threads, item_counts, author_sets, thread_sets = _scan_mentions(config)
    console.print(f"[bold]{len(threads):,}[/bold] distinct threads selected")
    posts, orphan_comments = _collect_threads(config, threads)

    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_path.write_text(json.dumps(posts), encoding="utf-8")
    comment_count = sum(len(post["comments"]) for post in posts)
    distinct_authors = {
        post["author_hash"] for post in posts if post["author_hash"] != "deleted"
    } | {
        comment["author_hash"]
        for post in posts
        for comment in post["comments"]
        if comment["author_hash"] != "deleted"
    }
    manifest = ComparatorCorpusManifest(
        cohort_schema_id=cohort.schema_id,
        cohort_sha256=sha256_file(config.cohort_path),
        comments_path=str(config.comments_path.resolve()),
        posts_path=str(config.posts_path.resolve()),
        output_path=str(config.output_path.resolve()),
        posts=len(posts),
        comments=comment_count,
        distinct_authors=len(distinct_authors),
        orphan_comments=orphan_comments,
        matches=tuple(
            ComparatorMatchSummary(
                slug=compound.slug,
                matching_items=item_counts[compound.slug],
                distinct_authors=len(author_sets[compound.slug]),
                distinct_threads=len(thread_sets[compound.slug]),
            )
            for compound in cohort.compounds
        ),
    )
    manifest_path = config.output_path.with_suffix(".manifest.json")
    safe_json_dump(manifest, manifest_path)
    console.print(
        f"[green]Wrote[/green] {len(posts):,} posts and {comment_count:,} comments "
        f"to {config.output_path}"
    )
    console.print(f"[green]Manifest[/green] {manifest_path}")
    return manifest


@app.command()
def main(
    comments: Path = typer.Option(..., exists=True, dir_okay=False),
    posts: Path = typer.Option(..., exists=True, dir_okay=False),
    output: Path = typer.Option(..., dir_okay=False),
    cohort: Path = typer.Option(DEFAULT_COHORT_CONFIG, exists=True, dir_okay=False),
) -> None:
    """Build the private union corpus and a privacy-safe count manifest."""
    try:
        build_comparator_corpus(
            BuildComparatorCorpusConfig(
                comments_path=comments,
                posts_path=posts,
                cohort_path=cohort,
                output_path=output,
            )
        )
    except (OSError, ValueError) as exc:
        console.print(f"[red]Comparator corpus build failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
