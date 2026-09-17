"""Shared fixtures: a database built from schema.sql, a row seeder, and a stubbed model call."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SCHEMA_SQL = REPO_ROOT / "schema.sql"


@pytest.fixture
def schema_db(tmp_path: Path) -> Path:
    """Path to an empty on-disk SQLite database created from the repo's schema.sql."""
    path = tmp_path / "schema.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
    return path


@pytest.fixture
def seed_reports() -> Callable[..., None]:
    """Insert users, posts, one treatment, one sentiment run and its reports into a schema database.

    ``posts`` are ``(post_id, parent_id, user_id, title, body)``; ``reports`` are
    ``(post_id, user_id, sentiment)`` and get report_id 1..n in the order given.
    """

    def seed(
        db_path: Path,
        posts: list[tuple],
        reports: list[tuple],
        *,
        drug: str = "7,8-dhf",
        aliases: tuple[str, ...] = ("tropoflavin",),
    ) -> None:
        with sqlite3.connect(db_path) as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO users (user_id, source_subreddit, scraped_at) VALUES (?, 'test', 0)",
                [(user,) for _pid, _parent, user, _title, _body in posts],
            )
            conn.executemany(
                "INSERT INTO posts (post_id, parent_id, user_id, title, body_text, scraped_at) VALUES (?, ?, ?, ?, ?, 0)",
                posts,
            )
            conn.execute("INSERT INTO treatment (id, canonical_name, aliases) VALUES (1, ?, ?)", (drug, json.dumps(list(aliases))))
            conn.execute("INSERT INTO extraction_runs VALUES (1, 0, 'abc', 'treatment_sentiment', '{}')")
            conn.executemany(
                "INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength) VALUES (1, ?, ?, 1, ?, 'strong')",
                reports,
            )

    return seed


class StubLLM:
    """Stands in for ``pipeline.doses.llm_call``; records every request payload.

    ``reply(fn)`` sets the responder: ``fn(items)`` returns the JSON-serialisable reply
    (a list of ``{"item_id", "doses"}`` objects) or a raw string. Default: no doses.
    """

    def __init__(self) -> None:
        self.payloads: list[dict] = []
        self._respond: Callable[[list[dict]], object] = lambda items: [{"item_id": it["item_id"], "doses": []} for it in items]

    def reply(self, respond: Callable[[list[dict]], object]) -> StubLLM:
        self._respond = respond
        return self

    def __call__(self, client, prompt, model=None, system=None, max_tokens=0) -> str:
        payload = json.loads(prompt)
        self.payloads.append(payload)
        out = self._respond(payload["items"])
        return out if isinstance(out, str) else json.dumps(out)


@pytest.fixture
def stub_llm(monkeypatch: pytest.MonkeyPatch) -> StubLLM:
    import pipeline.doses as doses_module

    stub = StubLLM()
    monkeypatch.setattr(doses_module, "llm_call", stub)
    return stub
