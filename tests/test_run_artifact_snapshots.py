"""Each run must keep its own copy of the decisions it made.

tagged_mentions.json, prefilter_results.json and aliases_*.json keep fixed names on purpose —
the pipeline reads them back to resume without re-paying for extraction or the prefilter. The
cost of that is every run overwriting the previous one's record, and the database cannot stand
in: it holds only what survived the writer gate, so once prefilter_results.json is gone there is
nothing left saying which pairs were dropped before classify ever saw them.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from run_sentiment_pipeline import _snapshot_run_artifacts
from utilities import PipelineConfig


def _config(tmp_path) -> PipelineConfig:
    return PipelineConfig(client=None, output_dir=tmp_path, db_path=tmp_path / "t.db")


def test_a_later_run_cannot_overwrite_an_earlier_runs_record(tmp_path):
    config = _config(tmp_path)
    (tmp_path / "prefilter_results.json").write_text(json.dumps({"a|ldn": True}), encoding="utf-8")
    (tmp_path / "tagged_mentions.json").write_text(json.dumps([{"id": "a"}]), encoding="utf-8")
    (tmp_path / "aliases_ldn.json").write_text(json.dumps(["ldn"]), encoding="utf-8")

    first, kept = _snapshot_run_artifacts(config, run_id=1)
    assert {"prefilter_results.json", "tagged_mentions.json", "aliases_ldn.json"} <= set(kept)

    # a second run reaches a different prefilter verdict for the same pair
    (tmp_path / "prefilter_results.json").write_text(json.dumps({"a|ldn": False}), encoding="utf-8")
    second, _ = _snapshot_run_artifacts(config, run_id=2)

    assert first != second
    assert json.loads((first / "prefilter_results.json").read_text(encoding="utf-8")) == {"a|ldn": True}
    assert json.loads((second / "prefilter_results.json").read_text(encoding="utf-8")) == {"a|ldn": False}


def test_the_working_files_stay_put_so_resume_still_works(tmp_path):
    """Snapshotting must copy, not move — a rename would force a re-run to re-pay for the prefilter."""
    config = _config(tmp_path)
    live = tmp_path / "prefilter_results.json"
    live.write_text(json.dumps({"a|ldn": True}), encoding="utf-8")
    _snapshot_run_artifacts(config, run_id=1)
    assert live.exists(), "working cache was moved instead of copied"


def test_snapshotting_a_run_with_no_artifacts_is_not_an_error(tmp_path):
    run_dir, kept = _snapshot_run_artifacts(_config(tmp_path), run_id=7)
    assert kept == []
    assert run_dir.is_dir()
