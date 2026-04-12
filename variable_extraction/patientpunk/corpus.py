"""
patientpunk.corpus
~~~~~~~~~~~~~~~~~~
Corpus loading utilities.

The PatientPunk corpus lives in a directory that may contain:

* ``subreddit_posts.json``  -- list of post objects scraped from a subreddit.
* ``users/``                -- directory of per-user history JSON files.

This module provides a :class:`CorpusLoader` that abstracts over both sources
and yields :class:`CorpusRecord` objects suitable for extraction.

Example
-------
>>> loader = CorpusLoader(Path("../data"))
>>> for record in loader.iter_records(limit=5):
...     print(record.source, record.author_hash[:8], len(record.texts))
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class CorpusRecord(BaseModel):
    """A single unit of text ready for extraction."""

    author_hash: str
    source: str
    post_id: str | None
    texts: list[str]
    raw: dict[str, Any] = Field(default_factory=dict, repr=False)

    @property
    def full_text(self) -> str:
        """All texts joined with double newlines."""
        return "\n\n".join(self.texts)

    def __repr__(self) -> str:
        return (
            f"CorpusRecord(source={self.source!r}, "
            f"author_hash={self.author_hash[:10]!r}..., "
            f"texts={len(self.texts)})"
        )


# ---------------------------------------------------------------------------
# CorpusLoader
# ---------------------------------------------------------------------------

class CorpusLoader:
    """
    Load a PatientPunk corpus from a directory.

    The loader handles both subreddit post files and per-user history
    directories.  It yields :class:`CorpusRecord` objects in a consistent
    format regardless of the underlying source.

    Parameters
    ----------
    input_dir:
        Directory containing ``subreddit_posts.json`` and/or ``users/``.
    """

    def __init__(self, input_dir: Path) -> None:
        self.input_dir = Path(input_dir)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def iter_records(
        self,
        limit: int | None = None,
        include_posts: bool = True,
        include_users: bool = True,
    ) -> Iterator[CorpusRecord]:
        """
        Lazily yield :class:`CorpusRecord` objects.

        Parameters
        ----------
        limit:
            Stop after yielding this many records.
        include_posts:
            Whether to include subreddit post records.
        include_users:
            Whether to include user history records.
        """
        count = 0

        if include_posts:
            for record in self._iter_posts():
                if limit is not None and count >= limit:
                    return
                yield record
                count += 1

        if include_users:
            for record in self._iter_users():
                if limit is not None and count >= limit:
                    return
                yield record
                count += 1

    def load_all(
        self,
        limit: int | None = None,
        include_posts: bool = True,
        include_users: bool = True,
    ) -> list[CorpusRecord]:
        """Load all records into memory and return as a list."""
        return list(
            self.iter_records(
                limit=limit,
                include_posts=include_posts,
                include_users=include_users,
            )
        )

    @property
    def record_count(self) -> int:
        """Total number of records available (no limit applied)."""
        return sum(1 for _ in self.iter_records())

    @property
    def post_count(self) -> int:
        """Number of subreddit post records available."""
        return sum(1 for _ in self._iter_posts())

    @property
    def user_count(self) -> int:
        """Number of user history records available."""
        users_dir = self.input_dir / "users"
        if not users_dir.exists():
            return 0
        return sum(1 for _ in users_dir.glob("*.json"))

    # ------------------------------------------------------------------
    # Internal iterators
    # ------------------------------------------------------------------

    def _iter_posts(self) -> Iterator[CorpusRecord]:
        posts_file = self.input_dir / "subreddit_posts.json"
        if not posts_file.exists():
            return
        try:
            posts = json.loads(posts_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            import sys
            print(
                f"Warning: skipping {posts_file.name}: {exc}",
                file=sys.stderr,
            )
            return
        for post in posts:
            texts = self._texts_from_post(post)
            yield CorpusRecord(
                author_hash=post.get("author_hash") or "",
                source="subreddit_post",
                post_id=post.get("post_id"),
                texts=texts,
                raw=post,
            )

    def _iter_users(self) -> Iterator[CorpusRecord]:
        users_dir = self.input_dir / "users"
        if not users_dir.exists():
            return
        for user_file in sorted(users_dir.glob("*.json")):
            try:
                user = json.loads(user_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                # Log corrupted / unreadable files so data-integrity problems
                # are visible, but don't halt the entire corpus load.
                import sys
                print(
                    f"Warning: skipping {user_file.name}: {exc}",
                    file=sys.stderr,
                )
                continue
            texts = self._texts_from_user(user)
            yield CorpusRecord(
                author_hash=user.get("author_hash") or user_file.stem,
                source="user_history",
                post_id=None,
                texts=texts,
                raw=user,
            )

    # ------------------------------------------------------------------
    # Text extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _texts_from_post(post: dict) -> list[str]:
        """Extract non-empty text segments from a subreddit post dict."""
        texts: list[str] = []
        title = (post.get("title") or "").strip()
        body = (post.get("body") or "").strip()
        if title:
            texts.append(title)
        if body and body not in ("[removed]", "[deleted]"):
            texts.append(body)
        for comment in post.get("comments", []):
            comment_body = (comment.get("body") or "").strip()
            if comment_body and comment_body not in ("[removed]", "[deleted]"):
                texts.append(comment_body)
        return texts

    @staticmethod
    def _texts_from_user(user: dict) -> list[str]:
        """Extract non-empty text segments from a user history dict."""
        texts: list[str] = []
        for post in user.get("posts", []):
            title = (post.get("title") or "").strip()
            body = (post.get("body") or "").strip()
            if title:
                texts.append(title)
            if body and body not in ("[removed]", "[deleted]"):
                texts.append(body)
        for comment in user.get("comments", []):
            comment_body = (comment.get("body") or "").strip()
            if comment_body and comment_body not in ("[removed]", "[deleted]"):
                texts.append(comment_body)
        return texts
