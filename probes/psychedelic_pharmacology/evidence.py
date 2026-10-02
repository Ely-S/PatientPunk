"""Anchored Reddit evidence retrieval for the psychedelic probe.

Keyword matching is retrieval only. Whether a passage describes the author's
own completed use is deliberately left to the claim model and provider.
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
from probes.store import text_sha256


PARAGRAPH_RE = re.compile(r"(?:\r?\n){2,}")
BOTLIKE_RE = re.compile(r"\?#\d+:\s*\[|^\s*\|.*\|.*\|", re.IGNORECASE | re.MULTILINE)
BOT_AUTHORS = frozenset(
    {
        "AutoModerator",
        "[deleted]",
        "sneakpeekbot",
        "RemindMeBot",
        "B0tRank",
        "WikiTextBot",
        "SubredditLinkBot",
        "totesmessenger",
        "None",
    }
)

TARGETS: dict[str, tuple[str, re.Pattern[str]]] = {
    "psilocybin": (
        "psilocybin OR psilocin OR shrooms OR shroom OR mushrooms OR truffles",
        re.compile(
            r"psilocyb|psilocin|magic mushroom|\bshrooms?\b|"
            r"psychedelic mushroom|magic truffle",
            re.IGNORECASE,
        ),
    ),
    "ketamine": (
        "ketamine OR esketamine OR spravato",
        re.compile(r"\bketamine\b|\besketamine\b|\bspravato\b", re.IGNORECASE),
    ),
    "lsd": (
        "lsd OR lysergic",
        re.compile(
            r"\blsd\b|lysergic|\b1c?p-?lsd\b|\bald-?52\b|"
            r"\bacid tabs?\b|\bacid trips?\b",
            re.IGNORECASE,
        ),
    ),
}


def _author_hash(username: str) -> str:
    """Hash a Reddit username the way the corpus did.

    The aggregation step that produced ``treatment_reports.user_id`` hashed the
    username verbatim -- no case folding, no salt -- so raw source text joins
    back to a cohort row on exactly this value. Changing it silently empties
    every cohort.
    """

    return hashlib.sha256(username.encode("utf-8")).hexdigest()


def _window_id(source_type: str, source_id: str, text: str) -> str:
    payload = f"{source_type}\0{source_id}\0{text_sha256(text)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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


def collect_windows(
    source_db: Path,
    members: list[CohortMember],
    *,
    config: dict[str, Any] | None = None,
) -> dict[tuple[str, str | None], list[SourceWindow]]:
    """Retrieve anchored windows for each resolved cohort member and target."""

    del config  # The retrieval contract is intentionally deterministic in V1.
    wanted = {(member.author_hash, member.target) for member in members}
    windows: dict[tuple[str, str | None], list[SourceWindow]] = defaultdict(list)
    connection = read_only_connection(source_db)
    try:
        for target, (fts_query, term) in TARGETS.items():
            for source_type in ("comment", "post"):
                for source_id, author, created_utc, text in _source_rows(
                    connection, source_type, fts_query
                ):
                    if not author or author in BOT_AUTHORS:
                        continue
                    key = (_author_hash(author), target)
                    if key not in wanted:
                        continue
                    normalized = _normalize(text or "")
                    if not term.search(normalized) or BOTLIKE_RE.search(normalized):
                        continue
                    for window_text in mention_windows(normalized, term):
                        windows[key].append(
                            SourceWindow(
                                source_window_id=_window_id(
                                    source_type, str(source_id), window_text
                                ),
                                source_type=source_type,
                                source_id=str(source_id),
                                text=window_text,
                            )
                        )
    finally:
        connection.close()

    for key, values in windows.items():
        unique = {
            (window.source_type, window.source_id, text_sha256(window.text)): window
            for window in values
        }
        windows[key] = sorted(
            unique.values(),
            key=lambda window: (window.source_type, window.source_id, window.source_window_id),
        )
    return dict(windows)
