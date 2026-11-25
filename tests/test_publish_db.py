"""Test for scripts/publish_db.py: publish one database and rebuild the catalog. S3 is faked; no network."""

import sqlite3
import sys
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import publish_db  # noqa: E402

WHEN = datetime(2026, 11, 5, tzinfo=UTC)


class FakeS3:
    """Just enough of publish_db.S3: one versioned bucket, held in a dict of key -> (bytes, metadata)."""

    def __init__(self, files):
        self.files = {k: (v, {}) for k, v in files.items()}

    def versioning_enabled(self):
        return True

    def head(self, key):
        if key not in self.files:
            return None
        data, meta = self.files[key]
        return {"ContentLength": len(data), "Metadata": meta, "LastModified": WHEN, "VersionId": "v1"}

    def upload(self, path, key, sha256):
        self.files[key] = (Path(path).read_bytes(), {"sha256": sha256})

    def get_text(self, key):
        return self.files[key][0].decode()

    def put_text(self, key, text, if_none_match=False):
        if if_none_match and key in self.files:
            return False
        self.files[key] = (text.encode(), {})
        return True

    def list_keys(self):
        return [{"Key": k, "Size": len(v), "LastModified": WHEN} for k, (v, _) in self.files.items()]


def example_db(folder: Path) -> Path:
    """A finished one-run database, as the pipeline leaves it."""
    folder.mkdir(exist_ok=True)
    db = folder / "example.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE extraction_runs (run_id INTEGER PRIMARY KEY, run_at INTEGER, commit_hash TEXT, "
                 "extraction_type TEXT, config TEXT, finished_at INTEGER)")
    conn.execute("INSERT INTO extraction_runs VALUES (1, 1793000000, 'abc123', 'treatment_sentiment', "
                 "'{\"model\": \"m\", \"git_dirty\": false}', 1793003600)")
    conn.commit()
    conn.close()
    return db


def publish_args(db: Path, **changes) -> Namespace:
    return Namespace(**{"db": db, "s3_uri": "s3://patientpunk/runs/example.db", "label": "test",
                        "purpose": "a test database", "input": ["data:posts.db"],
                        "command": ["uv run python src/run_sentiment_pipeline.py"],
                        "supersedes": None, "record_only": False} | changes)


def test_publish_builds_the_record_from_the_database_and_rebuilds_the_index(tmp_path):
    db = example_db(tmp_path)
    # An older database already in the bucket, with only a catalog copy to give its label.
    s3 = FakeS3({"old/a.db": b"x" * 10,
                 "database_catalog/by-upload-date/uploaded-2026-06-13/multi-treatment/old/a.db": b"x" * 10})
    args = publish_args(db)

    publish_db.cmd_publish(args, s3=s3)

    record = yaml.safe_load(s3.get_text("runs/example_provenance.yaml"))
    assert s3.files["runs/example.db"][0] == db.read_bytes()
    assert record["publication"]["status"] == "published"
    assert record["code"] == {"repository": publish_db.REPOSITORY, "commit_shas": ["abc123"], "working_tree": "clean"}
    assert record["database"]["completed_utc"] == "2026-10-26T08:33:20Z"
    index = s3.get_text("INDEX.md")
    assert "| `s3://patientpunk/runs/example.db` | none | test |" in index
    assert "| `s3://patientpunk/old/a.db` | `s3://patientpunk/database_catalog/" in index and "| multi-treatment |" in index
    assert [r["gap"] for r in publish_db.audit(s3)] == ["no provenance YAML", None]
    with pytest.raises(publish_db.PublishError, match="never overwritten"):
        publish_db.cmd_publish(args, s3=s3)


def test_publish_finishes_an_interrupted_upload_and_refuses_a_different_database(tmp_path):
    # The database reached its key with its SHA-256, then the run stopped before the YAML.
    db = example_db(tmp_path / "resume")
    s3 = FakeS3({})
    s3.files["runs/example.db"] = (db.read_bytes(), {"sha256": publish_db.sha256_file(db), "first": "upload"})
    publish_db.cmd_publish(publish_args(db), s3=s3)
    assert yaml.safe_load(s3.get_text("runs/example_provenance.yaml"))["publication"]["status"] == "published"
    assert s3.files["runs/example.db"][1]["first"] == "upload"  # finished, not uploaded again

    # A different database already at the key is refused and left as it was.
    db = example_db(tmp_path / "different")
    s3 = FakeS3({})
    s3.files["runs/example.db"] = (b"another database", {"sha256": "0" * 64})
    with pytest.raises(publish_db.PublishError, match="published snapshots are never overwritten"):
        publish_db.cmd_publish(publish_args(db), s3=s3)
    assert s3.files["runs/example.db"][0] == b"another database"
    assert "runs/example_provenance.yaml" not in s3.files


def test_publish_takes_supersedes_from_the_local_yaml_and_requires_an_input(tmp_path):
    db = example_db(tmp_path / "rerun")
    publish_db.provenance_path(db).write_text("database:\n  supersedes: s3://patientpunk/old/a.db\n",
                                              encoding="utf-8")
    s3 = FakeS3({"old/a.db": b"x" * 10})
    with pytest.raises(publish_db.PublishError, match="--input is required"):
        publish_db.cmd_publish(publish_args(db, input=None), s3=s3)
    assert "runs/example.db" not in s3.files  # refused before anything was uploaded

    publish_db.cmd_publish(publish_args(db), s3=s3)  # no --supersedes: the local YAML's is used
    record = yaml.safe_load(s3.get_text("runs/example_provenance.yaml"))
    assert record["database"]["supersedes"] == "s3://patientpunk/old/a.db"
    assert "superseded by `s3://patientpunk/runs/example.db`" in s3.get_text("INDEX.md")

    # A retrospective record needs no --input: an old database's inputs may be unknown.
    db = example_db(tmp_path / "retrospective")
    s3 = FakeS3({"runs/example.db": db.read_bytes()})
    publish_db.cmd_publish(publish_args(db, input=None, command=None, record_only=True), s3=s3)
    assert yaml.safe_load(s3.get_text("runs/example_provenance.yaml"))["inputs"] == []
