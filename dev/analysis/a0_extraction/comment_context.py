"""Build and query a context index for the local Reddit comments dataset.

The split JSONL dataset is the canonical raw-ish copy. This module builds a
derived SQLite database that makes reply context cheap to retrieve:

- direct parent comments
- ancestor chains
- previous sibling comments under the same parent
- previous comments in the same thread
- chronological iteration over every comment

The root submissions are not present in the comments JSONL export. Top-level
comments therefore know that they replied to a post, but the post title/body
remain unavailable until a submissions dataset is added.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from dev.analysis.a0_extraction.comment_dataset import DEFAULT_OUTPUT


DEFAULT_DATASET = DEFAULT_OUTPUT
DEFAULT_DB = DEFAULT_DATASET / "derived" / "comments.sqlite"

COMMENT_COLUMNS = [
    "id",
    "name",
    "link_id",
    "post_id",
    "parent_id",
    "parent_kind",
    "parent_comment_id",
    "created_utc",
    "date_utc",
    "author",
    "score",
    "is_submitter",
    "stickied",
    "body",
    "body_length",
    "body_sha256",
    "is_removed_or_deleted",
    "permalink",
    "source_line",
    "source_chunk",
    "has_body",
]


@dataclass(frozen=True)
class ContextDbConfig:
    dataset: Path = DEFAULT_DATASET
    db: Path = DEFAULT_DB
    replace: bool = False
    progress_every: int = 100_000


@dataclass(frozen=True)
class Comment:
    id: str
    name: str
    link_id: str
    post_id: str
    parent_id: str
    parent_kind: str
    parent_comment_id: str | None
    created_utc: int | None
    date_utc: str
    author: str
    score: int | None
    is_submitter: bool
    stickied: bool
    body: str
    body_length: int
    permalink: str
    source_line: int
    source_chunk: str


@dataclass(frozen=True)
class CommentContext:
    target: Comment
    ancestors: list[Comment]
    previous_siblings: list[Comment]
    previous_thread_comments: list[Comment]
    missing: dict[str, str]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_comment_id(value: str) -> str:
    value = value.strip()
    if value.startswith("t1_"):
        return value[3:]
    return value


def strip_thing_prefix(value: str, expected_prefix: str) -> str:
    if value.startswith(expected_prefix):
        return value[len(expected_prefix) :]
    return value


def int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def bool_to_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if value is None:
        return 0
    return 1 if str(value).strip().lower() in {"1", "true", "yes"} else 0


def row_to_comment(row: sqlite3.Row) -> Comment:
    return Comment(
        id=row["id"],
        name=row["name"],
        link_id=row["link_id"],
        post_id=row["post_id"] or "",
        parent_id=row["parent_id"] or "",
        parent_kind=row["parent_kind"],
        parent_comment_id=row["parent_comment_id"],
        created_utc=row["created_utc"],
        date_utc=row["date_utc"] or "",
        author=row["author"] or "",
        score=row["score"],
        is_submitter=bool(row["is_submitter"]),
        stickied=bool(row["stickied"]),
        body=row["body"] or "",
        body_length=row["body_length"] or 0,
        permalink=row["permalink"] or "",
        source_line=row["source_line"],
        source_chunk=row["source_chunk"] or "",
    )


def source_manifest(dataset: Path) -> dict[str, Any]:
    path = dataset / "metadata" / "manifest.json"
    if not path.exists():
        raise SystemExit(f"ERROR: dataset manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def iter_index_rows(dataset: Path) -> Iterator[dict[str, str]]:
    index_dir = dataset / "index"
    files = sorted(index_dir.glob("comments_index_part-*.csv"))
    if not files:
        raise SystemExit(f"ERROR: no index CSV files found under {index_dir}")

    for path in files:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            yield from csv.DictReader(handle)


def iter_chunk_paths(dataset: Path) -> Iterator[Path]:
    chunks_path = dataset / "metadata" / "chunks.csv"
    if not chunks_path.exists():
        raise SystemExit(f"ERROR: chunks metadata not found: {chunks_path}")

    with chunks_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            yield dataset / row["relative_path"]


def parent_fields(link_id: str, parent_id: str) -> tuple[str, str, str | None]:
    post_id = strip_thing_prefix(link_id, "t3_") if link_id else ""
    if parent_id.startswith("t1_"):
        return post_id, "comment", strip_thing_prefix(parent_id, "t1_")
    if parent_id.startswith("t3_"):
        return strip_thing_prefix(parent_id, "t3_"), "post", None
    return post_id, "unknown", None


def body_flags(body: str) -> tuple[int, str, int]:
    normalized = body.strip().lower()
    is_removed = 1 if normalized in {"[removed]", "[deleted]"} else 0
    digest = hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()
    return len(body), digest, is_removed


def connect(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn


def apply_build_pragmas(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;
        PRAGMA temp_store = MEMORY;
        PRAGMA cache_size = -200000;
        """
    )


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE comments (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            link_id TEXT NOT NULL,
            post_id TEXT,
            parent_id TEXT,
            parent_kind TEXT NOT NULL,
            parent_comment_id TEXT,
            created_utc INTEGER,
            date_utc TEXT,
            author TEXT,
            score INTEGER,
            is_submitter INTEGER NOT NULL,
            stickied INTEGER NOT NULL,
            body TEXT,
            body_length INTEGER NOT NULL DEFAULT 0,
            body_sha256 TEXT,
            is_removed_or_deleted INTEGER NOT NULL DEFAULT 0,
            permalink TEXT,
            source_line INTEGER NOT NULL UNIQUE,
            source_chunk TEXT NOT NULL,
            has_body INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE build_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )


def create_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE INDEX idx_comments_link_created ON comments(link_id, created_utc, id);
        CREATE INDEX idx_comments_parent_created ON comments(parent_id, created_utc, id);
        CREATE INDEX idx_comments_parent_comment ON comments(parent_comment_id);
        CREATE INDEX idx_comments_created ON comments(created_utc, id);
        CREATE INDEX idx_comments_author_created ON comments(author, created_utc, id);
        CREATE INDEX idx_comments_source_chunk ON comments(source_chunk);
        CREATE INDEX idx_comments_removed ON comments(is_removed_or_deleted);
        """
    )


def insert_metadata(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO build_metadata(key, value) VALUES (?, ?)",
        (key, json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)),
    )


def index_insert_tuple(row: dict[str, str]) -> tuple[Any, ...]:
    comment_id = row["id"]
    name = row["name"] or f"t1_{comment_id}"
    link_id = row["link_id"]
    parent_id = row["parent_id"]
    post_id, parent_kind, parent_comment_id = parent_fields(link_id, parent_id)

    return (
        comment_id,
        name,
        link_id,
        post_id,
        parent_id,
        parent_kind,
        parent_comment_id,
        int_or_none(row["created_utc"]),
        row["date_utc"],
        row["author"],
        int_or_none(row["score"]),
        bool_to_int(row["is_submitter"]),
        bool_to_int(row["stickied"]),
        None,
        0,
        None,
        0,
        row["permalink"],
        int(row["source_line"]),
        row["chunk_file"],
        0,
    )


def import_index(conn: sqlite3.Connection, dataset: Path, progress_every: int) -> int:
    sql = f"""
        INSERT INTO comments({", ".join(COMMENT_COLUMNS)})
        VALUES ({", ".join("?" for _ in COMMENT_COLUMNS)})
    """
    batch = []
    count = 0

    with conn:
        for row in iter_index_rows(dataset):
            batch.append(index_insert_tuple(row))
            count += 1
            if len(batch) >= 10_000:
                conn.executemany(sql, batch)
                batch.clear()
            if progress_every and count % progress_every == 0:
                print(f"indexed metadata rows={count:,}", flush=True)
        if batch:
            conn.executemany(sql, batch)

    return count


def update_body_tuple(record: dict[str, Any]) -> tuple[Any, ...]:
    body = record.get("body") or ""
    length, digest, is_removed = body_flags(body)
    return body, length, digest, is_removed, record.get("id", "")


def import_bodies(conn: sqlite3.Connection, dataset: Path, progress_every: int) -> int:
    sql = """
        UPDATE comments
        SET body = ?,
            body_length = ?,
            body_sha256 = ?,
            is_removed_or_deleted = ?,
            has_body = 1
        WHERE id = ?
    """
    batch = []
    count = 0

    with conn:
        for path in iter_chunk_paths(dataset):
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    record = json.loads(line)
                    batch.append(update_body_tuple(record))
                    count += 1
                    if len(batch) >= 10_000:
                        conn.executemany(sql, batch)
                        batch.clear()
                    if progress_every and count % progress_every == 0:
                        print(f"loaded bodies={count:,}", flush=True)
        if batch:
            conn.executemany(sql, batch)

    return count


def scalar(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    return conn.execute(sql, params).fetchone()[0]


def compute_context_stats(conn: sqlite3.Connection) -> dict[str, int]:
    reply_comments = scalar(conn, "SELECT COUNT(*) FROM comments WHERE parent_kind = 'comment'")
    top_level_comments = scalar(conn, "SELECT COUNT(*) FROM comments WHERE parent_kind = 'post'")
    unknown_parent_comments = scalar(conn, "SELECT COUNT(*) FROM comments WHERE parent_kind = 'unknown'")
    missing_parent_comments = scalar(
        conn,
        """
        SELECT COUNT(*)
        FROM comments child
        LEFT JOIN comments parent ON parent.id = child.parent_comment_id
        WHERE child.parent_kind = 'comment'
          AND parent.id IS NULL
        """,
    )
    removed_or_deleted = scalar(conn, "SELECT COUNT(*) FROM comments WHERE is_removed_or_deleted = 1")
    return {
        "reply_comments": reply_comments,
        "top_level_comments": top_level_comments,
        "unknown_parent_comments": unknown_parent_comments,
        "reply_comments_with_missing_parent": missing_parent_comments,
        "reply_comments_with_available_parent": reply_comments - missing_parent_comments,
        "removed_or_deleted_comments": removed_or_deleted,
    }


def safe_unlink_db(path: Path) -> None:
    resolved = path.resolve()
    dataset_root = DEFAULT_DATASET.parent.resolve()
    if dataset_root not in resolved.parents:
        raise RuntimeError(f"Refusing to remove DB outside dataset/: {resolved}")
    if path.exists():
        path.unlink()


def build_context_db(config: ContextDbConfig) -> Path:
    dataset = config.dataset.resolve()
    db = config.db.resolve()
    manifest = source_manifest(dataset)
    expected = int(manifest["valid_records"])

    db.parent.mkdir(parents=True, exist_ok=True)
    tmp_db = db.with_suffix(db.suffix + ".tmp")
    if db.exists():
        if not config.replace:
            raise SystemExit(f"ERROR: context DB already exists, use --replace to rebuild: {db}")
        safe_unlink_db(db)
    if tmp_db.exists():
        if not config.replace:
            raise SystemExit(f"ERROR: temp DB already exists, use --replace to rebuild: {tmp_db}")
        safe_unlink_db(tmp_db)

    conn = connect(tmp_db)
    try:
        apply_build_pragmas(conn)
        create_schema(conn)
        insert_metadata(conn, "built_at_utc", utc_now_iso())
        insert_metadata(conn, "dataset_root", str(dataset))
        insert_metadata(conn, "source_manifest", manifest)

        indexed_rows = import_index(conn, dataset, config.progress_every)
        if indexed_rows != expected:
            raise RuntimeError(f"Indexed {indexed_rows:,} rows, expected {expected:,}")

        body_rows = import_bodies(conn, dataset, config.progress_every)
        if body_rows != expected:
            raise RuntimeError(f"Loaded {body_rows:,} bodies, expected {expected:,}")

        missing_bodies = scalar(conn, "SELECT COUNT(*) FROM comments WHERE has_body = 0")
        if missing_bodies:
            raise RuntimeError(f"{missing_bodies:,} indexed comments never received a body")

        print("creating SQLite indexes", flush=True)
        create_indexes(conn)

        stats = compute_context_stats(conn)
        insert_metadata(conn, "comment_count", expected)
        insert_metadata(conn, "context_stats", stats)
        conn.commit()
    finally:
        conn.close()

    tmp_db.rename(db)
    print(f"built context DB: {db}", flush=True)
    return db


def verify_context_db(dataset: Path = DEFAULT_DATASET, db: Path = DEFAULT_DB) -> bool:
    dataset = dataset.resolve()
    db = db.resolve()
    manifest = source_manifest(dataset)
    expected = int(manifest["valid_records"])
    problems = []

    if not db.exists():
        raise SystemExit(f"ERROR: context DB not found: {db}")

    conn = connect(db)
    try:
        row_count = scalar(conn, "SELECT COUNT(*) FROM comments")
        has_body_count = scalar(conn, "SELECT COUNT(*) FROM comments WHERE has_body = 1")
        distinct_source_lines = scalar(conn, "SELECT COUNT(DISTINCT source_line) FROM comments")
        min_created = scalar(conn, "SELECT MIN(created_utc) FROM comments")
        max_created = scalar(conn, "SELECT MAX(created_utc) FROM comments")
        duplicate_names = scalar(
            conn,
            "SELECT COUNT(*) FROM (SELECT name FROM comments GROUP BY name HAVING COUNT(*) > 1)",
        )
        stats = compute_context_stats(conn)

        if row_count != expected:
            problems.append(f"row count mismatch: manifest={expected}, db={row_count}")
        if has_body_count != expected:
            problems.append(f"body load mismatch: manifest={expected}, has_body={has_body_count}")
        if distinct_source_lines != expected:
            problems.append(
                f"source_line uniqueness mismatch: manifest={expected}, distinct={distinct_source_lines}"
            )
        if min_created != int(manifest["min_created_utc"]):
            problems.append(f"min_created_utc mismatch: manifest={manifest['min_created_utc']}, db={min_created}")
        if max_created != int(manifest["max_created_utc"]):
            problems.append(f"max_created_utc mismatch: manifest={manifest['max_created_utc']}, db={max_created}")
        if duplicate_names:
            problems.append(f"duplicate comment names found: {duplicate_names}")

        print(f"comments: {row_count:,}", flush=True)
        print(f"comments with body: {has_body_count:,}", flush=True)
        print(f"distinct source lines: {distinct_source_lines:,}", flush=True)
        print(f"top-level comments: {stats['top_level_comments']:,}", flush=True)
        print(f"reply comments: {stats['reply_comments']:,}", flush=True)
        print(f"reply comments with available parent: {stats['reply_comments_with_available_parent']:,}", flush=True)
        print(f"reply comments with missing parent: {stats['reply_comments_with_missing_parent']:,}", flush=True)
        print(f"removed/deleted comments: {stats['removed_or_deleted_comments']:,}", flush=True)
    finally:
        conn.close()

    if problems:
        print("verification failed:", flush=True)
        for problem in problems:
            print(f"- {problem}", flush=True)
        return False

    print("verification passed", flush=True)
    return True


class CommentStore:
    def __init__(self, db: Path = DEFAULT_DB) -> None:
        self.db = db.resolve()
        self.conn = connect(self.db)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "CommentStore":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def get_comment(self, comment_id: str) -> Comment | None:
        normalized = normalize_comment_id(comment_id)
        row = self.conn.execute(
            f"SELECT {', '.join(COMMENT_COLUMNS)} FROM comments WHERE id = ? OR name = ?",
            (normalized, comment_id),
        ).fetchone()
        return row_to_comment(row) if row else None

    def get_comment_by_source_line(self, source_line: int) -> Comment | None:
        row = self.conn.execute(
            f"SELECT {', '.join(COMMENT_COLUMNS)} FROM comments WHERE source_line = ?",
            (source_line,),
        ).fetchone()
        return row_to_comment(row) if row else None

    def get_parent(self, comment: Comment | str) -> Comment | None:
        target = self._as_comment(comment)
        if target is None or target.parent_kind != "comment" or not target.parent_comment_id:
            return None
        return self.get_comment(target.parent_comment_id)

    def get_ancestors(self, comment: Comment | str, limit: int = 2) -> list[Comment]:
        target = self._as_comment(comment)
        if target is None or limit <= 0:
            return []

        ancestors = []
        current = target
        seen = {target.id}
        for _ in range(limit):
            parent = self.get_parent(current)
            if parent is None or parent.id in seen:
                break
            ancestors.append(parent)
            seen.add(parent.id)
            current = parent
        return ancestors

    def get_children(self, comment: Comment | str, limit: int = 50) -> list[Comment]:
        target = self._as_comment(comment)
        if target is None or limit <= 0:
            return []
        rows = self.conn.execute(
            f"""
            SELECT {", ".join(COMMENT_COLUMNS)}
            FROM comments
            WHERE parent_comment_id = ?
            ORDER BY created_utc, id
            LIMIT ?
            """,
            (target.id, limit),
        ).fetchall()
        return [row_to_comment(row) for row in rows]

    def get_previous_siblings(self, comment: Comment | str, limit: int = 3) -> list[Comment]:
        target = self._as_comment(comment)
        if target is None or limit <= 0:
            return []

        rows = self.conn.execute(
            f"""
            SELECT {", ".join(COMMENT_COLUMNS)}
            FROM comments
            WHERE parent_id = ?
              AND (created_utc < ? OR (created_utc = ? AND id < ?))
              AND id != ?
            ORDER BY created_utc DESC, id DESC
            LIMIT ?
            """,
            (
                target.parent_id,
                target.created_utc,
                target.created_utc,
                target.id,
                target.id,
                limit,
            ),
        ).fetchall()
        return [row_to_comment(row) for row in reversed(rows)]

    def get_previous_thread_comments(self, comment: Comment | str, limit: int = 20) -> list[Comment]:
        target = self._as_comment(comment)
        if target is None or limit <= 0:
            return []

        rows = self.conn.execute(
            f"""
            SELECT {", ".join(COMMENT_COLUMNS)}
            FROM comments
            WHERE link_id = ?
              AND (created_utc < ? OR (created_utc = ? AND id < ?))
              AND id != ?
            ORDER BY created_utc DESC, id DESC
            LIMIT ?
            """,
            (
                target.link_id,
                target.created_utc,
                target.created_utc,
                target.id,
                target.id,
                limit,
            ),
        ).fetchall()
        return [row_to_comment(row) for row in reversed(rows)]

    def get_context(
        self,
        comment: Comment | str,
        ancestor_depth: int = 2,
        previous_sibling_limit: int = 0,
        previous_thread_limit: int = 0,
    ) -> CommentContext:
        target = self._as_comment(comment)
        if target is None:
            raise KeyError(f"Comment not found: {comment}")

        ancestors = self.get_ancestors(target, ancestor_depth)
        previous_siblings = self.get_previous_siblings(target, previous_sibling_limit)
        previous_thread_comments = self.get_previous_thread_comments(target, previous_thread_limit)
        already_in_context = {target.id}
        already_in_context.update(comment.id for comment in ancestors)
        already_in_context.update(comment.id for comment in previous_siblings)
        previous_thread_comments = [
            comment for comment in previous_thread_comments if comment.id not in already_in_context
        ]
        missing = self._missing_context(target, ancestors)
        return CommentContext(
            target=target,
            ancestors=ancestors,
            previous_siblings=previous_siblings,
            previous_thread_comments=previous_thread_comments,
            missing=missing,
        )

    def iter_comments(
        self,
        limit: int | None = None,
        where_sql: str = "",
        params: tuple[Any, ...] = (),
        order: str = "created_utc, id",
    ) -> Iterator[Comment]:
        if order not in {"created_utc, id", "source_line", "score DESC, created_utc, id"}:
            raise ValueError(f"Unsupported order: {order}")

        sql = f"SELECT {', '.join(COMMENT_COLUMNS)} FROM comments"
        if where_sql:
            sql += f" WHERE {where_sql}"
        sql += f" ORDER BY {order}"
        if limit is not None:
            sql += " LIMIT ?"
            params = (*params, limit)

        for row in self.conn.execute(sql, params):
            yield row_to_comment(row)

    def iter_comments_with_context(
        self,
        ancestor_depth: int = 2,
        previous_sibling_limit: int = 0,
        previous_thread_limit: int = 0,
        limit: int | None = None,
        where_sql: str = "",
        params: tuple[Any, ...] = (),
        order: str = "created_utc, id",
    ) -> Iterator[CommentContext]:
        for comment in self.iter_comments(limit=limit, where_sql=where_sql, params=params, order=order):
            yield self.get_context(
                comment,
                ancestor_depth=ancestor_depth,
                previous_sibling_limit=previous_sibling_limit,
                previous_thread_limit=previous_thread_limit,
            )

    def _as_comment(self, comment: Comment | str) -> Comment | None:
        if isinstance(comment, Comment):
            return comment
        return self.get_comment(comment)

    def _missing_context(self, target: Comment, ancestors: list[Comment]) -> dict[str, str]:
        missing = {}
        if target.parent_kind == "post":
            missing["root_post"] = "not_available_in_comments_jsonl"
        elif target.parent_kind == "comment" and target.parent_comment_id and not ancestors:
            missing["parent_comment"] = "missing_from_comments_dataset"
        elif target.parent_kind == "unknown":
            missing["parent"] = "unknown_parent_id_format"
        return missing


def truncate_for_render(text: str, max_chars: int) -> str:
    text = text.replace("\r", " ").strip()
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip() + "..."


def render_comment(label: str, comment: Comment, max_body_chars: int) -> str:
    header = f"[{label} | {comment.date_utc} | score={comment.score} | author={comment.author}]"
    body = truncate_for_render(comment.body, max_body_chars)
    return f"{header}\n{body}"


def render_context(context: CommentContext, max_body_chars: int = 900) -> str:
    parts = [
        f"THREAD {context.target.link_id}",
        f"TARGET {context.target.id} source_line={context.target.source_line}",
        "",
    ]

    for depth, ancestor in reversed(list(enumerate(context.ancestors, start=1))):
        label = "parent" if depth == 1 else f"ancestor-{depth}"
        parts.append(render_comment(label, ancestor, max_body_chars))
        parts.append("")

    for i, sibling in enumerate(context.previous_siblings, start=1):
        parts.append(render_comment(f"previous-sibling-{i}", sibling, max_body_chars))
        parts.append("")

    for i, prior in enumerate(context.previous_thread_comments, start=1):
        parts.append(render_comment(f"previous-thread-{i}", prior, max_body_chars))
        parts.append("")

    parts.append(render_comment("target", context.target, max_body_chars))

    if context.missing:
        parts.append("")
        parts.append("MISSING CONTEXT")
        for key, value in sorted(context.missing.items()):
            parts.append(f"- {key}: {value}")

    return "\n".join(parts)


def sample_context(
    db: Path,
    comment_id: str | None,
    source_line: int | None,
    ancestor_depth: int,
    previous_sibling_limit: int,
    previous_thread_limit: int,
) -> str:
    with CommentStore(db) as store:
        if source_line is not None:
            comment = store.get_comment_by_source_line(source_line)
            if comment is None:
                raise SystemExit(f"ERROR: no comment found for source line {source_line}")
        elif comment_id:
            comment = store.get_comment(comment_id)
            if comment is None:
                raise SystemExit(f"ERROR: no comment found for id {comment_id}")
        else:
            comment = next(
                store.iter_comments(
                    limit=1,
                    where_sql="parent_kind = 'comment' AND has_body = 1",
                    order="created_utc, id",
                ),
                None,
            )
            if comment is None:
                raise SystemExit("ERROR: no comment with parent context found")

        return render_context(
            store.get_context(
                comment,
                ancestor_depth=ancestor_depth,
                previous_sibling_limit=previous_sibling_limit,
                previous_thread_limit=previous_thread_limit,
            )
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and query a SQLite reply-context database for the comments dataset.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--replace", action="store_true", help="Replace an existing context DB.")
    parser.add_argument("--verify-only", action="store_true", help="Only verify an existing context DB.")
    parser.add_argument("--sample-id", help="Render context for a comment id or t1_ name.")
    parser.add_argument("--sample-source-line", type=int, help="Render context for a source line.")
    parser.add_argument("--ancestor-depth", type=int, default=2)
    parser.add_argument("--previous-sibling-limit", type=int, default=3)
    parser.add_argument("--previous-thread-limit", type=int, default=0)
    parser.add_argument("--progress-every", type=int, default=100_000)
    return parser


def config_from_args(args: argparse.Namespace) -> ContextDbConfig:
    return ContextDbConfig(
        dataset=args.dataset,
        db=args.db,
        replace=args.replace,
        progress_every=args.progress_every,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.verify_only:
        return 0 if verify_context_db(args.dataset, args.db) else 1

    if args.sample_id or args.sample_source_line is not None:
        print(
            sample_context(
                args.db,
                args.sample_id,
                args.sample_source_line,
                args.ancestor_depth,
                args.previous_sibling_limit,
                args.previous_thread_limit,
            )
        )
        return 0

    db = build_context_db(config_from_args(args))
    return 0 if verify_context_db(args.dataset, db) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
