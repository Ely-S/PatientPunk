"""Concurrent dispatch in probes.engine.run_probe.

The engine had no tests before this change. These cover the properties that
concurrency could plausibly break: every unit still gets processed, the work
genuinely overlaps, per-unit state does not leak between threads, and dispatch
width stays out of run identity.
"""

from __future__ import annotations

import sqlite3
import threading
import types
from pathlib import Path

import pytest

from probes import engine
from probes.engine import LoadedProbe
from probes.models import Claim, RunConfig, SourceWindow

COHORT_SQL = "SELECT author_hash, target FROM cohort ORDER BY author_hash"


@pytest.fixture
def cohort_db(tmp_path: Path) -> Path:
    path = tmp_path / "cohort.db"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE cohort (author_hash TEXT, target TEXT)")
    db.executemany(
        "INSERT INTO cohort VALUES (?, ?)",
        [(f"author{i:02d}", "psilocybin") for i in range(12)],
    )
    db.commit()
    db.close()
    return path


@pytest.fixture
def source_db(tmp_path: Path) -> Path:
    path = tmp_path / "source.db"
    sqlite3.connect(path).close()
    return path


def make_probe(package_dir: Path) -> LoadedProbe:
    """A minimal probe: one window per member, one claim per unit."""

    # spec_hash reads these three off disk to build run identity.
    (package_dir / "cohort.sql").write_text(COHORT_SQL)
    (package_dir / "evidence.py").write_text("# stub\n")
    (package_dir / "claim.py").write_text("# stub\n")

    def collect_windows(source_db, members, *, config):
        return {
            (m.author_hash, m.target): [
                SourceWindow(
                    source_window_id=f"w-{m.author_hash}",
                    source_type="comment",
                    source_id=f"c-{m.author_hash}",
                    text=f"text for {m.author_hash}",
                )
            ]
            for m in members
        }

    def build_prompt(unit, *, variant, feedback):
        return "system", f"prompt {unit.author_hash} v{variant} feedback={feedback}"

    def parse_claims(payload, unit):
        return [
            Claim(
                claim_id=f"{unit.unit_key}-0",
                unit_key=unit.unit_key,
                source_window_id=unit.windows[0].source_window_id,
                included=True,
                values={"drug": payload["drug"]},
                evidence=[{"field_path": "drug", "quote": payload["quote"]}],
            )
        ]

    return LoadedProbe(
        name="fake",
        package_dir=package_dir,
        cohort_sql=COHORT_SQL,
        evidence=types.SimpleNamespace(collect_windows=collect_windows),
        claim=types.SimpleNamespace(build_prompt=build_prompt, parse_claims=parse_claims),
    )


class FakeClient:
    """Records concurrency and returns a valid payload per call."""

    def __init__(self, delay: float = 0.02) -> None:
        self.delay = delay
        self.calls = 0
        self.in_flight = 0
        self.max_in_flight = 0
        self._lock = threading.Lock()
        self.messages = types.SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        with self._lock:
            self.calls += 1
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            threading.Event().wait(self.delay)
            return types.SimpleNamespace(
                content=[types.SimpleNamespace(text='{"drug": "psilocybin", "quote": "q"}')],
                usage=types.SimpleNamespace(input_tokens=10, output_tokens=5),
            )
        finally:
            with self._lock:
                self.in_flight -= 1


@pytest.fixture
def patched(monkeypatch, tmp_path):
    """Stub the probe, the provider client, and _utils response helpers."""

    probe = make_probe(tmp_path)
    monkeypatch.setattr(engine, "load_probe", lambda name: probe)

    client = FakeClient()
    utils = types.ModuleType("patientpunk._utils")
    utils.get_llm_client = lambda **kwargs: client
    utils.response_text = lambda r: r.content[0].text
    utils.check_response = lambda r, model: None
    utils.parse_json_response = lambda raw: __import__("json").loads(raw)
    monkeypatch.setitem(__import__("sys").modules, "patientpunk._utils", utils)
    return client


def config() -> RunConfig:
    return RunConfig(
        provider="openai",
        base_url="https://example.invalid/api",
        model="test-model",
        temperature=0.0,
        max_tokens=1024,
    )


def run(tmp_path, cohort_db, source_db, *, workers):
    return engine.run_probe(
        "fake",
        cohort_db=cohort_db,
        source_db=source_db,
        output_db=tmp_path / f"out{workers}.db",
        config=config(),
        confirm_paid_run=True,
        workers=workers,
    )


def test_every_unit_completes_under_concurrency(tmp_path, cohort_db, source_db, patched):
    result = run(tmp_path, cohort_db, source_db, workers=4)
    assert (result.attempted_units, result.completed_units, result.failed_units) == (12, 12, 0)
    assert patched.calls == 12


def test_dispatch_actually_overlaps(tmp_path, cohort_db, source_db, patched):
    run(tmp_path, cohort_db, source_db, workers=4)
    assert patched.max_in_flight > 1, "units were dispatched serially despite workers=4"


def test_serial_dispatch_never_overlaps(tmp_path, cohort_db, source_db, patched):
    run(tmp_path, cohort_db, source_db, workers=1)
    assert patched.max_in_flight == 1


def test_concurrent_result_matches_serial(tmp_path, cohort_db, source_db, patched):
    serial = run(tmp_path, cohort_db, source_db, workers=1)
    concurrent = run(tmp_path, cohort_db, source_db, workers=6)
    assert serial.run_id == concurrent.run_id, "workers must not move run identity"
    for db, expected in ((tmp_path / "out1.db", 12), (tmp_path / "out6.db", 12)):
        c = sqlite3.connect(db)
        assert c.execute("SELECT COUNT(*) FROM claim").fetchone()[0] == expected
        assert dict(c.execute("SELECT status, COUNT(*) FROM unit GROUP BY 1")) == {
            "complete": expected
        }
        c.close()


def test_one_failing_unit_does_not_poison_its_neighbours(
    tmp_path, cohort_db, source_db, patched, monkeypatch
):
    """A unit that exhausts its ladder is marked failed; the rest still pass.

    Guards the feedback variable, which was a per-unit local in the serial loop
    and would corrupt other units if it were ever hoisted to shared state.
    """

    doomed = {"author00"}
    original = patched.messages.create

    def create(**kwargs):
        if any(a in kwargs.get("messages", [{}])[0].get("content", "") for a in doomed):
            return types.SimpleNamespace(
                content=[types.SimpleNamespace(text="not json at all")],
                usage=types.SimpleNamespace(input_tokens=1, output_tokens=1),
            )
        return original(**kwargs)

    patched.messages.create = create
    result = run(tmp_path, cohort_db, source_db, workers=4)
    assert result.failed_units == 1
    assert result.completed_units == 11

    c = sqlite3.connect(tmp_path / "out4.db")
    failed = [r[0] for r in c.execute("SELECT unit_key FROM unit WHERE status='failed'")]
    assert len(failed) == 1
    # The failed unit burned its whole ladder, and no other unit inherited it.
    assert c.execute(
        "SELECT COUNT(*) FROM attempt WHERE unit_key = ?", (failed[0],)
    ).fetchone()[0] == engine.MAX_PROVIDER_ATTEMPTS
    c.close()


def test_workers_below_one_is_rejected(tmp_path, cohort_db, source_db, patched):
    with pytest.raises(ValueError, match="workers must be at least 1"):
        run(tmp_path, cohort_db, source_db, workers=0)


def test_client_is_built_once_for_all_workers(tmp_path, cohort_db, source_db, monkeypatch):
    probe = make_probe(tmp_path)
    monkeypatch.setattr(engine, "load_probe", lambda name: probe)
    client = FakeClient()
    builds = []
    utils = types.ModuleType("patientpunk._utils")

    def get_llm_client(**kwargs):
        builds.append(kwargs)
        return client

    utils.get_llm_client = get_llm_client
    utils.response_text = lambda r: r.content[0].text
    utils.check_response = lambda r, model: None
    utils.parse_json_response = lambda raw: __import__("json").loads(raw)
    monkeypatch.setitem(__import__("sys").modules, "patientpunk._utils", utils)

    run(tmp_path, cohort_db, source_db, workers=8)
    assert builds == [
        {"provider": "openai", "base_url": "https://example.invalid/api"}
    ]


def test_format_error_compacts_pydantic_dump():
    from pydantic import BaseModel, ValidationError

    class Envelope(BaseModel):
        events: list[dict]

    with pytest.raises(ValidationError) as raised:
        Envelope.model_validate({"events": "not-a-list"})
    text = engine._format_error(raised.value)
    assert text.startswith("ValidationError (")
    assert "events:" in text
    assert "For further information visit" not in text
    assert "\n" not in text


def test_format_error_collapses_and_truncates():
    text = engine._format_error(ValueError("line1\nline2 " + "x" * 1000), limit=80)
    assert "\n" not in text
    assert text.endswith("...")
    assert len(text) == 80


def test_failed_attempts_log_reason_and_summary(
    tmp_path, cohort_db, source_db, patched, capsys
):
    doomed = {"author00"}
    original = patched.messages.create

    def create(**kwargs):
        if any(a in kwargs.get("messages", [{}])[0].get("content", "") for a in doomed):
            return types.SimpleNamespace(
                content=[types.SimpleNamespace(text="not json at all")],
                usage=types.SimpleNamespace(input_tokens=1, output_tokens=1),
            )
        return original(**kwargs)

    patched.messages.create = create
    result = run(tmp_path, cohort_db, source_db, workers=4)
    assert result.failed_units == 1
    err = capsys.readouterr().err
    assert err.count("retry unit=") == engine.MAX_PROVIDER_ATTEMPTS - 1
    assert err.count("FAIL unit=") == 1
    assert "attempt=1/3 validation JSONDecodeError:" in err
    assert "attempt=3/3 validation JSONDecodeError:" in err
    assert "failure summary: 1 units" in err
    assert "JSONDecodeError: Expecting value" in err


def test_non_transient_transport_failure_logs_without_retry(
    tmp_path, cohort_db, source_db, patched, capsys
):
    doomed = {"author00"}
    original = patched.messages.create

    def create(**kwargs):
        if any(a in kwargs.get("messages", [{}])[0].get("content", "") for a in doomed):
            raise RuntimeError("provider rejected the request")
        return original(**kwargs)

    patched.messages.create = create
    result = run(tmp_path, cohort_db, source_db, workers=2)
    assert result.failed_units == 1
    err = capsys.readouterr().err
    assert "retry unit=" not in err
    assert "FAIL unit=" in err
    assert "transport RuntimeError: provider rejected the request" in err
    assert "failure summary: 1 units" in err
