"""Resume checkpoint writes must be atomic.

Regression for Airwhale review on #63: open(..., \"w\") + json.dump truncates
immediately, so an interrupt mid-write destroyed the previous good checkpoint
and broke --resume (JSONDecodeError on the next run).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from patientpunk.llm_extract import _write_json_atomic


def test_write_json_atomic_roundtrip(tmp_path):
    path = tmp_path / "llm_records_schema.json"
    payload = [{"id": "p1", "fields": {"age": [34]}}]

    _write_json_atomic(path, payload)

    assert json.loads(path.read_text(encoding="utf-8")) == payload
    assert list(tmp_path.glob("*.tmp")) == []


def test_write_json_atomic_preserves_existing_on_write_failure(tmp_path, monkeypatch):
    """If the tmp write fails, the previous checkpoint must remain intact."""
    path = tmp_path / "llm_records_schema.json"
    previous = [{"id": "p0", "fields": {"age": [20]}}]
    path.write_text(json.dumps(previous), encoding="utf-8")

    real_write_text = Path.write_text

    def boom(self, data, *args, **kwargs):
        if str(self).endswith(".tmp"):
            raise OSError("simulated interrupt during checkpoint write")
        return real_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", boom)

    with pytest.raises(OSError, match="simulated interrupt"):
        _write_json_atomic(path, [{"id": "p1", "fields": {"age": [99]}}])

    assert json.loads(path.read_text(encoding="utf-8")) == previous
    assert list(tmp_path.glob("*.tmp")) == []


def test_write_json_atomic_preserves_existing_on_replace_failure(tmp_path, monkeypatch):
    """If replace fails after tmp is written, the live checkpoint must stay readable."""
    path = tmp_path / "llm_records_schema.json"
    previous = [{"id": "p0"}]
    path.write_text(json.dumps(previous), encoding="utf-8")

    def boom(self, target):
        raise OSError("simulated interrupt during replace")

    monkeypatch.setattr(Path, "replace", boom)

    with pytest.raises(OSError, match="simulated interrupt"):
        _write_json_atomic(path, [{"id": "p1"}])

    assert json.loads(path.read_text(encoding="utf-8")) == previous
    # tmp may remain after a failed replace; that is fine — live file is intact
    assert path.exists()
