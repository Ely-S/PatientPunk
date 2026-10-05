"""Contract tests for read-only, resumable dual-judge auditing."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from pipeline.audit import (
    ROOT, AuditTask, CliJudge, DoseValue, JudgeUnavailableError, NoRowValue, Source, Verdict,
    _subscription_environment, adjudicate, load_tasks, run_audit,
)


class SequenceJudge:
    def __init__(self, *verdicts: Verdict):
        self.verdicts = iter(verdicts)
        self.prompts: list[str] = []

    def review(self, prompt: str) -> Verdict:
        self.prompts.append(prompt)
        return next(self.verdicts)


def verdict(judgment: str, issue_code: str = "none") -> Verdict:
    return Verdict(judgment=judgment, issue_code=issue_code,
                   evidence_quote="I took 25 mg myself" if judgment != "unclear" else None,
                   rationale="The author's report directly supports this interpretation.")


@pytest.fixture
def pipeline_db(tmp_path: Path) -> Path:
    path = tmp_path / "pipeline.sqlite"
    with sqlite3.connect(path) as conn:
        conn.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))
        conn.execute("INSERT INTO users VALUES ('u1','Nootropics',1)")
        conn.execute("INSERT INTO posts (post_id,user_id,body_text,scraped_at) VALUES "
                     "('p1','u1','I took 25 mg myself and slept poorly.',1)")
        conn.execute("INSERT INTO treatment (id,canonical_name,aliases) VALUES "
                     "(1,'7,8-DHF','[\"tropoflavin\"]')")
        for run_id, kind in ((1, "treatment_sentiment"), (2, "report_doses"),
                             (3, "report_effects")):
            conn.execute("INSERT INTO extraction_runs VALUES (?,?,?,?,?,?)",
                         (run_id, 1, "test", kind,
                          json.dumps({"drug_excluded_compounds": ["4-DMA"]}), 2))
        conn.execute("INSERT INTO treatment_reports VALUES "
                     "(1,1,'p1','u1',1,'positive','strong','[\"insomnia\"]')")
        conn.executemany("INSERT INTO report_runs VALUES (?,1)", [(2,), (3,)])
        conn.execute("INSERT INTO report_doses VALUES "
                     "(1,1,2,0,25,25,'mg',NULL,NULL,'I took 25 mg myself')")
        conn.execute("INSERT INTO report_effects VALUES "
                     "(1,1,3,0,'sleep','insomnia','worsened',NULL,'target',"
                     "'I took 25 mg myself and slept poorly.',1)")
    return path


def test_loads_three_latest_decisions_with_source_and_dose_link(pipeline_db: Path) -> None:
    tasks = load_tasks(pipeline_db, "7,8-DHF")
    assert [task.value.kind for task in tasks] == ["sentiment", "dose", "effect"]
    assert tasks[0].source.excluded_compounds == ["4-DMA"]
    assert tasks[2].value.linked_dose.low == 25


def test_no_rows_are_audited_as_explicit_decisions(pipeline_db: Path) -> None:
    with sqlite3.connect(pipeline_db) as conn:
        conn.execute("DELETE FROM report_effects")
    tasks = load_tasks(pipeline_db, kinds={"effect"})
    assert len(tasks) == 1
    assert isinstance(tasks[0].value, NoRowValue)
    assert tasks[0].value.kind == "no_effect"


def test_independent_then_discussion_until_convergence() -> None:
    task = AuditTask(decision_id="d", report_id=1, run_id=2, record_id=3,
                     source=Source(post_id="p", report="I took 25 mg myself",
                                   treatment="7,8-DHF"),
                     value=DoseValue(low=25, high=25, unit="mg"))
    opus = SequenceJudge(verdict("unsupported", "wrong_compound"), verdict("supported"))
    codex = SequenceJudge(verdict("supported"), verdict("supported"))
    result = adjudicate(task, opus, codex)
    assert result.status == "supported"
    assert len(result.rounds) == 2
    assert "Prior rounds JSON" not in opus.prompts[0]
    assert "Prior rounds JSON" in opus.prompts[1]


def test_ten_round_disagreement_is_unresolved() -> None:
    task = AuditTask(decision_id="d", report_id=1, run_id=2, record_id=3,
                     source=Source(post_id="p", report="I took 25 mg myself",
                                   treatment="7,8-DHF"),
                     value=DoseValue(low=25, high=25, unit="mg"))
    result = adjudicate(task, SequenceJudge(*[verdict("supported") for _ in range(10)]),
                        SequenceJudge(*[verdict("unsupported", "wrong_compound")
                                        for _ in range(10)]))
    assert result.status == "unresolved"
    assert len(result.rounds) == 10


def test_cli_failure_pauses_instead_of_recording_a_verdict() -> None:
    class FailedJudge:
        def review(self, prompt: str) -> Verdict:
            raise JudgeUnavailableError("subscription expired")

    task = AuditTask(decision_id="d", report_id=1, run_id=2, record_id=3,
                     source=Source(post_id="p", report="I took 25 mg myself",
                                   treatment="7,8-DHF"),
                     value=DoseValue(low=25, high=25, unit="mg"))
    with pytest.raises(JudgeUnavailableError, match="subscription expired"):
        adjudicate(task, FailedJudge(), SequenceJudge(verdict("supported")))


def test_bad_evidence_is_unresolved_without_database_change(pipeline_db: Path,
                                                            tmp_path: Path) -> None:
    bad = Verdict(judgment="unsupported", issue_code="wrong_dose",
                  evidence_quote="Not in this report", rationale="Wrong dose attributed here.")
    output = tmp_path / "audit.sqlite"
    counts = run_audit(pipeline_db, output, kinds={"dose"}, check_auth=False,
                       opus=SequenceJudge(bad), codex=SequenceJudge(verdict("supported")))
    assert counts.unresolved == 1
    assert counts.supported == 0
    with sqlite3.connect(pipeline_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM report_doses").fetchone()[0] == 1
    with sqlite3.connect(output) as conn:
        stored = json.loads(conn.execute("SELECT result_json FROM audit_results").fetchone()[0])
    assert stored["status"] == "unresolved"


def test_resume_skips_completed_decision(pipeline_db: Path, tmp_path: Path) -> None:
    output = tmp_path / "audit.sqlite"
    first = run_audit(pipeline_db, output, kinds={"dose"}, check_auth=False,
                      opus=SequenceJudge(verdict("supported")),
                      codex=SequenceJudge(verdict("supported")))
    second = run_audit(pipeline_db, output, kinds={"dose"}, check_auth=False,
                       opus=SequenceJudge(), codex=SequenceJudge())
    assert first.supported == 1
    assert second.skipped == 1


def test_limit_counts_new_decisions_on_resume(pipeline_db: Path, tmp_path: Path) -> None:
    output = tmp_path / "audit.sqlite"
    first = run_audit(pipeline_db, output, check_auth=False, limit=1,
                      opus=SequenceJudge(verdict("supported")),
                      codex=SequenceJudge(verdict("supported")))
    second = run_audit(pipeline_db, output, check_auth=False, limit=1,
                       opus=SequenceJudge(verdict("supported")),
                       codex=SequenceJudge(verdict("supported")))
    assert first.supported == 1
    assert second.supported == 1
    assert second.skipped == 1


def test_subscription_environment_removes_payg_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    clean = _subscription_environment()
    assert all(key not in clean for key in
               ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"))


def test_cli_model_configuration_is_explicit() -> None:
    assert CliJudge("opus", "claude-opus-5-5").model == "claude-opus-5-5"
