"""Shared fixtures: a database built from schema.sql and a stubbed model call."""

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
