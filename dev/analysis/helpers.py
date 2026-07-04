"""Small public helpers for analysis notebooks and scripts.

Most analysis code should start here instead of importing the lower-level
SQLite implementation directly.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from dev.analysis.a0_extraction.comment_context import (
    DEFAULT_DB,
    Comment,
    CommentContext,
    CommentStore,
)


def comments(
    *,
    comment_id: str | None = None,
    source_line: int | None = None,
    with_context: bool = True,
    ancestor_depth: int = 2,
    previous_sibling_limit: int = 0,
    previous_thread_limit: int = 0,
    limit: int | None = None,
    where_sql: str = "",
    params: tuple[Any, ...] = (),
    order: str = "created_utc, id",
    db: str | Path = DEFAULT_DB,
) -> Comment | CommentContext | Iterator[Comment | CommentContext]:
    """Get one comment or iterate comments from the local context database.

    Use `source_line` or `comment_id` to fetch one item:

    ```python
    item = comments(source_line=11)
    print(item.target.body)
    ```

    Omit both to iterate:

    ```python
    for item in comments(limit=100):
        print(item.target.body)
    ```

    By default this returns `CommentContext` objects. Set
    `with_context=False` to return bare `Comment` objects.
    """
    if comment_id is not None and source_line is not None:
        raise ValueError("Pass either comment_id or source_line, not both.")

    db_path = Path(db)
    if comment_id is not None or source_line is not None:
        return _get_one_comment(
            db_path=db_path,
            comment_id=comment_id,
            source_line=source_line,
            with_context=with_context,
            ancestor_depth=ancestor_depth,
            previous_sibling_limit=previous_sibling_limit,
            previous_thread_limit=previous_thread_limit,
        )

    return _iter_comments(
        db_path=db_path,
        with_context=with_context,
        ancestor_depth=ancestor_depth,
        previous_sibling_limit=previous_sibling_limit,
        previous_thread_limit=previous_thread_limit,
        limit=limit,
        where_sql=where_sql,
        params=params,
        order=order,
    )


def _get_one_comment(
    *,
    db_path: Path,
    comment_id: str | None,
    source_line: int | None,
    with_context: bool,
    ancestor_depth: int,
    previous_sibling_limit: int,
    previous_thread_limit: int,
) -> Comment | CommentContext:
    with CommentStore(db_path) as store:
        if source_line is not None:
            comment = store.get_comment_by_source_line(source_line)
            missing = f"source_line={source_line}"
        else:
            assert comment_id is not None
            comment = store.get_comment(comment_id)
            missing = f"comment_id={comment_id}"

        if comment is None:
            raise KeyError(f"Comment not found: {missing}")

        if not with_context:
            return comment

        return store.get_context(
            comment,
            ancestor_depth=ancestor_depth,
            previous_sibling_limit=previous_sibling_limit,
            previous_thread_limit=previous_thread_limit,
        )


def _iter_comments(
    *,
    db_path: Path,
    with_context: bool,
    ancestor_depth: int,
    previous_sibling_limit: int,
    previous_thread_limit: int,
    limit: int | None,
    where_sql: str,
    params: tuple[Any, ...],
    order: str,
) -> Iterator[Comment | CommentContext]:
    with CommentStore(db_path) as store:
        if with_context:
            yield from store.iter_comments_with_context(
                ancestor_depth=ancestor_depth,
                previous_sibling_limit=previous_sibling_limit,
                previous_thread_limit=previous_thread_limit,
                limit=limit,
                where_sql=where_sql,
                params=params,
                order=order,
            )
        else:
            yield from store.iter_comments(
                limit=limit,
                where_sql=where_sql,
                params=params,
                order=order,
            )


__all__ = ["comments"]
