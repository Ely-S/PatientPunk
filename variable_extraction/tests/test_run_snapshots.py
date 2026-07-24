"""Variable coding runs must keep a copy of what it produced."""
import json
from pathlib import Path

import pytest

from patientpunk.pipeline import Pipeline, PipelineConfig, PipelineResult

SCHEMA = Path(__file__).resolve().parent.parent / "schemas" / "base_schema.json"


def _pipeline(tmp_path) -> Pipeline:
    config = PipelineConfig(schema_path=SCHEMA, input_dir=tmp_path)
    pipe = Pipeline(config)
    pipe._temp_dir.mkdir(parents=True, exist_ok=True)
    return pipe


def _write_run_outputs(pipe, marker: str) -> None:
    (pipe.config.input_dir / "records.csv").write_text(f"author_hash,age\nu1,{marker}\n", encoding="utf-8")
    (pipe.config.input_dir / "llm_provenance.json").write_text(json.dumps({"run": marker}), encoding="utf-8")
    (pipe._temp_dir / "phase1_candidates.json").write_text(json.dumps([marker]), encoding="utf-8")


def test_each_run_gets_its_own_directory_and_earlier_ones_survive(tmp_path):
    pipe = _pipeline(tmp_path)
    _write_run_outputs(pipe, "first")
    first = pipe._snapshot_run(PipelineResult())

    _write_run_outputs(pipe, "second")     # a second run overwrites the working files
    second = pipe._snapshot_run(PipelineResult())

    assert first != second
    assert "first" in (first / "records.csv").read_text(encoding="utf-8")
    assert "second" in (second / "records.csv").read_text(encoding="utf-8")


def test_temp_artifacts_are_saved_before_the_next_run_deletes_them(tmp_path):
    """phase1_candidates.json is the discovery judgement's output and _clean_temp removes it."""
    pipe = _pipeline(tmp_path)
    _write_run_outputs(pipe, "first")
    run_dir = pipe._snapshot_run(PipelineResult())

    pipe._clean_temp()   # what the next full run does first
    assert not (pipe._temp_dir / "phase1_candidates.json").exists()
    assert json.loads((run_dir / "phase1_candidates.json").read_text(encoding="utf-8")) == ["first"]


def test_working_files_are_copied_not_moved(tmp_path):
    """Downstream commands resolve output/records.csv by that exact name."""
    pipe = _pipeline(tmp_path)
    _write_run_outputs(pipe, "first")
    pipe._snapshot_run(PipelineResult())
    assert (pipe.config.input_dir / "records.csv").exists()


def test_a_snapshot_records_a_manifest(tmp_path):
    pipe = _pipeline(tmp_path)
    _write_run_outputs(pipe, "first")
    run_dir = pipe._snapshot_run(PipelineResult())
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert "records.csv" in manifest["artifacts"]
    assert manifest["schema_id"]


def test_an_already_claimed_run_number_is_skipped_not_overwritten(tmp_path):
    """Each run takes the next unused run number; an existing run directory is not overwritten."""
    pipe = _pipeline(tmp_path)
    squatter = tmp_path / "runs" / "run_1"
    squatter.mkdir(parents=True)
    (squatter / "records.csv").write_text("someone else's run", encoding="utf-8")

    _write_run_outputs(pipe, "mine")
    run_dir = pipe._snapshot_run(PipelineResult())

    assert run_dir != squatter
    assert (squatter / "records.csv").read_text(encoding="utf-8") == "someone else's run"
    assert "mine" in (run_dir / "records.csv").read_text(encoding="utf-8")


def test_a_snapshot_failure_never_fails_a_finished_run(tmp_path, monkeypatch):
    """Hours of API time must not be discarded by a failed best-effort copy."""
    pipe = _pipeline(tmp_path)
    monkeypatch.setattr(Pipeline, "_run_phases", lambda self: PipelineResult(total_elapsed=1.0))
    monkeypatch.setattr(Pipeline, "_snapshot_run",
                        lambda self, result: (_ for _ in ()).throw(TypeError("not serialisable")))
    assert pipe.run().total_elapsed == 1.0
