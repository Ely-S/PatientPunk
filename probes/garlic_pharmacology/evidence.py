"""Anchored Reddit evidence retrieval for the garlic probe.

Keyword matching is retrieval only. Speech act, identity, actual use, and
attribution are labelled by the claim model. Do not reintroduce identity regex
gates.

``TARGETS`` is the single source of truth for the FTS query. The cohort builder
imports it so the planned member set and the windows cannot silently diverge.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from probes.engine import read_only_connection
from probes.models import CohortMember, SourceWindow
from probes.psychedelic_pharmacology.evidence import BOT_AUTHORS
from probes.store import text_sha256


PARAGRAPH_RE = re.compile(r"(?:\r?\n){2,}")
BOTLIKE_RE = re.compile(r"\?#\d+:\s*\[|^\s*\|.*\|.*\|", re.IGNORECASE | re.MULTILINE)

# Retrieval only. Do not add bare ``allium`` or the garlic emoji; that recall
# gap is a documented limitation, not an oversight.
TARGETS: dict[str, tuple[str, re.Pattern[str]]] = {
    "garlic": (
        "garlic OR allicin OR kyolic",
        re.compile(
            r"garlic|\ballicin\b|\bkyolic\b|allium\s+sativum",
            re.IGNORECASE,
        ),
    ),
}

# Broader than TARGETS: used only to confirm the two JSON-only rows have no
# garlic-family tokens in source (GATE 1 hallucination check).
HALLUCINATION_TOKEN_RE = re.compile(
    r"garlic|\ballicin\b|\bkyolic\b|\bclove\b|\ballium\b",
    re.IGNORECASE,
)


def author_hash(username: str) -> str:
    """Hash a Reddit username the way the corpus did.

    Verbatim SHA-256 of the username bytes, no case fold, no salt — the same
    one-liner as ``scripts/db_to_corpus.py``. Changing it silently empties the
    cohort or makes GATE 1's JSON overlap a lie.
    """

    return hashlib.sha256(username.encode()).hexdigest()


def _window_id(source_type: str, source_id: str, text: str) -> str:
    payload = f"{source_type}\0{source_id}\0{text_sha256(text)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _dedup_windows(items: list[tuple[int, SourceWindow]]) -> list[SourceWindow]:
    """Keep one window per distinct body for a single author+target.

    Repeat-posts of the same text under different source ids are one evidence
    span. The representative is the earliest ``created_utc``, then
    ``(source_type, source_id)``. Cross-author copies are out of scope: this
    runs inside one ``(author_hash, target)`` bucket.
    """

    best: dict[str, tuple[tuple[int, str, str], SourceWindow]] = {}
    for created_utc, window in items:
        fingerprint = text_sha256(window.text)
        rank = (created_utc, window.source_type, window.source_id)
        current = best.get(fingerprint)
        if current is None or rank < current[0]:
            best[fingerprint] = (rank, window)
    return sorted(
        (window for _rank, window in best.values()),
        key=lambda window: (window.source_type, window.source_id, window.source_window_id),
    )


def _normalize(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()).strip()


def mention_windows(text: str, term: re.Pattern[str]) -> list[str]:
    """Return each matching paragraph with one neighboring paragraph each side."""

    normalized = _normalize(text)
    paragraphs = [part.strip() for part in PARAGRAPH_RE.split(normalized) if part.strip()]
    ranges: list[tuple[int, int]] = []
    for index, paragraph in enumerate(paragraphs):
        if term.search(paragraph):
            ranges.append((max(0, index - 1), min(len(paragraphs), index + 2)))

    merged: list[list[int]] = []
    for start, stop in ranges:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], stop)
        else:
            merged.append([start, stop])
    return ["\n\n".join(paragraphs[start:stop]) for start, stop in merged]


def _source_rows(
    connection: sqlite3.Connection, source_type: str, fts_query: str
) -> list[tuple[Any, ...]]:
    if source_type == "comment":
        return connection.execute(
            """
            SELECT c.id, c.author, c.created_utc, c.body
            FROM comments_fts AS f
            JOIN comments AS c ON c.rowid = f.rowid
            WHERE f.comments_fts MATCH ?
            """,
            (fts_query,),
        ).fetchall()
    return connection.execute(
        """
        SELECT p.id, p.author, p.created_utc,
               COALESCE(p.title, '') || char(10) || COALESCE(p.selftext, '')
        FROM posts_fts AS f
        JOIN posts AS p ON p.rowid = f.rowid
        WHERE f.posts_fts MATCH ?
        """,
        (fts_query,),
    ).fetchall()


def matching_author_hashes(source_db: Path) -> set[str]:
    """Distinct non-bot author hashes matching the TARGETS FTS queries.

    This is the cohort. The builder imports it so GATE 1 and ``collect_windows``
    cannot silently use different recall.
    """

    hashes: set[str] = set()
    connection = read_only_connection(source_db)
    try:
        for _target, (fts_query, _term) in TARGETS.items():
            for source_type in ("comment", "post"):
                for _source_id, author, _created_utc, _text in _source_rows(
                    connection, source_type, fts_query
                ):
                    if not author or author in BOT_AUTHORS:
                        continue
                    hashes.add(author_hash(author))
    finally:
        connection.close()
    return hashes


def collect_windows(
    source_db: Path,
    members: list[CohortMember],
    *,
    config: dict[str, Any] | None = None,
) -> dict[tuple[str, str | None], list[SourceWindow]]:
    """Retrieve anchored windows for each resolved cohort member and target."""

    del config  # The retrieval contract is intentionally deterministic in V1.
    wanted = {(member.author_hash, member.target) for member in members}
    windows: dict[tuple[str, str | None], list[tuple[int, SourceWindow]]] = defaultdict(list)
    connection = read_only_connection(source_db)
    try:
        for target, (fts_query, term) in TARGETS.items():
            for source_type in ("comment", "post"):
                for source_id, author, created_utc, text in _source_rows(
                    connection, source_type, fts_query
                ):
                    if not author or author in BOT_AUTHORS:
                        continue
                    key = (author_hash(author), target)
                    if key not in wanted:
                        continue
                    normalized = _normalize(text or "")
                    if not term.search(normalized) or BOTLIKE_RE.search(normalized):
                        continue
                    for window_text in mention_windows(normalized, term):
                        windows[key].append(
                            (
                                int(created_utc or 0),
                                SourceWindow(
                                    source_window_id=_window_id(
                                        source_type, str(source_id), window_text
                                    ),
                                    source_type=source_type,
                                    source_id=str(source_id),
                                    text=window_text,
                                ),
                            )
                        )
    finally:
        connection.close()

    return {
        key: _dedup_windows(values) for key, values in windows.items()
    }
